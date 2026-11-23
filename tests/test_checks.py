import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bastion import checks
from bastion.core import BastionError, digest
from bastion.mcp import invoke, listing
from bastion.runtime import Runtime
from bastion.store import Store


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=Store(self.root)
        self.runtime=Runtime(self.store)
        (self.root/'calc.py').write_text('def add(a,b):\n    return a+b\n')
        self._write_test('self.assertEqual(add(2,3),5)')

    def _write_test(self, body):
        (self.root/'test_calc.py').write_text('import unittest\nfrom calc import add\nclass Tests(unittest.TestCase):\n    def test_add(self):\n        '+body+'\n')

    def manifest(self):
        return {'name':'Reviewed calculator check','files':['calc.py','test_calc.py'],'testModules':['test_calc'],'minTests':1,
            'trust':'reviewed-local-code; not-os-sandboxed',
            'budgets':{'wallSeconds':10,'cpuSeconds':5,'outputBytes':65536,'stateBytes':64*1024*1024}}

    def approved(self, manifest=None):
        p=checks.plan(self.runtime,manifest or self.manifest())
        checks.approve(self.runtime,p['check'],p['digest'])
        return p

    def test_pass_snapshot_receipt_reuse_and_fresh_process_verification(self):
        p=self.approved()
        result=checks.run(self.runtime,p['check'],p['digest'])
        self.assertTrue(result['passed'])
        self.assertEqual(result['receipt']['tests']['testsRun'],1)
        self.assertEqual(checks.run(self.runtime,p['check'],p['digest'])['receiptDigest'],result['receiptDigest'])
        child=subprocess.run([sys.executable,'-m','bastion','--workspace',str(self.root),'check','verify',p['check']],capture_output=True,text=True,timeout=10)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertTrue(json.loads(child.stdout)['passed'])
        self.assertFalse((self.root/'__pycache__').exists())

    def test_failure_is_retained_and_integrity_is_not_success(self):
        self._write_test('self.assertEqual(add(2,3),999)')
        p=self.approved()
        result=checks.run(self.runtime,p['check'],p['digest'])
        self.assertFalse(result['passed'])
        self.assertTrue(result['integrityVerified'])
        self.assertEqual(result['state'],'failed')
        self.assertEqual(result['receipt']['tests']['failures'],1)

    def test_no_tests_and_all_skipped_cannot_pass(self):
        for source in ['import unittest\n','import unittest\n@unittest.skip("fixture")\nclass Tests(unittest.TestCase):\n def test_skip(self): pass\n']:
            (self.root/'test_calc.py').write_text(source)
            p=self.approved()
            self.assertFalse(checks.run(self.runtime,p['check'],p['digest'])['passed'])

    def test_approval_and_current_source_required(self):
        p=checks.plan(self.runtime,self.manifest())
        with self.assertRaisesRegex(BastionError,'unapproved'):
            checks.run(self.runtime,p['check'],p['digest'])
        checks.approve(self.runtime,p['check'],p['digest'])
        (self.root/'calc.py').write_text('changed')
        with self.assertRaisesRegex(BastionError,'source changed'):
            checks.run(self.runtime,p['check'],p['digest'])

    def test_invalid_trust_modules_paths_and_budgets(self):
        for key,value in [('trust','sandboxed'),('files',['../escape.py']),('testModules',['os.system']),('minTests',0),('files',['calc.py','calc.py'])]:
            manifest=self.manifest(); manifest[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(BastionError): checks.plan(self.runtime,manifest)
        manifest=self.manifest(); manifest['budgets']['wallSeconds']=True
        with self.assertRaises(BastionError): checks.plan(self.runtime,manifest)

    def test_output_budget_and_wall_timeout_fail_with_receipts(self):
        self._write_test('print("x"*100000,flush=True)')
        manifest=self.manifest(); manifest['budgets']['outputBytes']=1024
        p=self.approved(manifest)
        result=checks.run(self.runtime,p['check'],p['digest'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['receipt']['stopReason'],'output budget exhausted')
        self.assertLessEqual(result['receipt']['outputBytes'],1024)
        self._write_test('__import__("time").sleep(3)')
        manifest=self.manifest(); manifest['budgets']['wallSeconds']=1
        p=self.approved(manifest)
        self.assertFalse(checks.run(self.runtime,p['check'],p['digest'])['passed'])

    def test_declared_source_mutation_is_a_failed_check(self):
        self._write_test('__import__("pathlib").Path("calc.py").write_text("mutated")')
        p=self.approved()
        result=checks.run(self.runtime,p['check'],p['digest'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['receipt']['sourceUnchanged'])
        self.assertIn('return a+b',(self.root/'calc.py').read_text())

    def test_log_and_recomputed_receipt_tampering_refused(self):
        p=self.approved(); result=checks.run(self.runtime,p['check'],p['digest'])
        root=self.store.root/'checks'/p['check']
        log=(root/'output.log').read_bytes(); (root/'output.log').write_text('tampered')
        with self.assertRaisesRegex(BastionError,'log integrity'): checks.verify(self.runtime,p['check'])
        (root/'output.log').write_bytes(log)
        receipt=copy.deepcopy(result['receipt']); receipt['scope']='tampered'
        with self.store.connect(write=True) as db:
            db.execute('UPDATE checks SET receipt=?,receipt_digest=? WHERE id=?',(json.dumps(receipt),digest(receipt),p['check']))
        with self.assertRaisesRegex(BastionError,'completion event'): checks.verify(self.runtime,p['check'])

    def test_interrupted_and_active_checks_never_retry_implicitly(self):
        p=self.approved()
        with self.store.execution_lock('check-'+p['check']):
            with self.assertRaisesRegex(BastionError,'active worker'): checks.run(self.runtime,p['check'],p['digest'])
        with self.store.connect(write=True) as db: db.execute("UPDATE checks SET state='running' WHERE id=?",(p['check'],))
        with self.assertRaisesRegex(BastionError,'reconciliation'): checks.run(self.runtime,p['check'],p['digest'])

    def test_mcp_is_proposal_and_inspection_only(self):
        p=invoke(self.runtime,'bastion_check_plan',{'manifest':self.manifest()})
        self.assertEqual(p['state'],'draft')
        names={t['name'] for t in listing()['tools']}
        self.assertNotIn('bastion_check_run',names)
        self.assertNotIn('bastion_check_approve',names)
