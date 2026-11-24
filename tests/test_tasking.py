import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bastion import checks,tasking
from bastion.core import BastionError,digest
from bastion.metrics import summary
from bastion.mcp import invoke,listing
from bastion.native import NativeEngine
from bastion.runtime import Runtime
from bastion.store import Store


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runtime=Runtime(Store(self.root))
        (self.root/'qa').mkdir();(self.root/'qa/__init__.py').write_text('')
        (self.root/'qa/test_repo.py').write_text('import unittest\nclass Tests(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+3,5)\n')

    def spec(self):
        return {'recipe':'python-unittest','name':'Repository quality gate','files':['qa/__init__.py','qa/test_repo.py'],
            'testModules':['qa.test_repo'],'minTests':1,'trust':'reviewed-local-code; not-os-sandboxed',
            'budgets':{'wallSeconds':10,'cpuSeconds':5,'outputBytes':65536,'stateBytes':64*1024*1024}}

    def done(self):
        p=tasking.plan(self.runtime,self.spec());checks.approve(self.runtime,p['task'],p['digest'])
        return p,tasking.run(self.runtime,p['task'],p['digest'])

    def test_repository_task_report_export_and_reuse(self):
        p,result=self.done();self.assertTrue(result['passed']);self.assertFalse(result['reused'])
        self.assertEqual(result['receipt']['tests']['testsRun'],1)
        self.assertGreater(result['receipt']['metrics']['executionMs'],0)
        self.assertIsNone(result['receipt']['metrics']['native'])
        self.assertTrue(tasking.run(self.runtime,p['task'],p['digest'])['reused'])
        value=tasking.report(self.runtime,p['task']);self.assertIn('| Outcome | PASS |',tasking.markdown(value))
        exported=tasking.export(self.runtime,p['task'],result['receiptDigest'],'quality.md')
        self.assertEqual(exported['sha256'],hashlib.sha256((self.root/'quality.md').read_bytes()).hexdigest())
        metrics=summary(self.runtime)
        self.assertEqual(metrics['sample']['verifiedReceipts'],1)
        self.assertEqual(metrics['sample']['measuredExecutions'],1)
        self.assertEqual(metrics['receiptReuseEvents'],1)
        self.assertEqual(metrics['reportExportEvents'],1)
        self.assertEqual(metrics['sample']['observedTests'],1)

    def test_html_report_escapes_content_and_exports_without_network_assets(self):
        p,result=self.done()
        value=tasking.report(self.runtime,p['task']);value['name']='<script>alert(1)</script>'
        rendered=tasking.html_report(value)
        self.assertIn('&lt;script&gt;',rendered);self.assertNotIn('<script>',rendered)
        self.assertNotIn('src=',rendered);self.assertNotIn('href=',rendered)
        tasking.export(self.runtime,p['task'],result['receiptDigest'],'report.html','html')
        self.assertTrue((self.root/'report.html').read_text().startswith('<!doctype html>'))

    def test_failed_task_has_report_and_nonzero_cli_status(self):
        (self.root/'qa/test_repo.py').write_text('import unittest\nclass Tests(unittest.TestCase):\n def test_bad(self): self.fail("deliberate")\n')
        p=tasking.plan(self.runtime,self.spec());checks.approve(self.runtime,p['task'],p['digest'])
        child=subprocess.run([sys.executable,'-m','bastion','--workspace',str(self.root),'task','run',p['task'],p['digest']],capture_output=True,text=True,timeout=15)
        self.assertEqual(child.returncode,1,child.stderr)
        result=json.loads(child.stdout);self.assertFalse(result['passed'])
        self.assertIn('| Outcome | FAIL |',tasking.markdown(tasking.report(self.runtime,p['task'])))
        self.assertEqual(summary(self.runtime)['sample']['failed'],1)

    def test_no_implicit_approval_stale_source_or_package_shadowing(self):
        spec=self.spec();spec['files'].remove('qa/__init__.py')
        with self.assertRaisesRegex(BastionError,'pinned __init__'): tasking.plan(self.runtime,spec)
        spec=self.spec();spec['recipe']='shell'
        with self.assertRaisesRegex(BastionError,'supported task recipe'): tasking.plan(self.runtime,spec)
        p=tasking.plan(self.runtime,self.spec())
        with self.assertRaisesRegex(BastionError,'unapproved'): tasking.run(self.runtime,p['task'],p['digest'])
        checks.approve(self.runtime,p['task'],p['digest']);(self.root/'qa/test_repo.py').write_text('changed')
        with self.assertRaisesRegex(BastionError,'source changed'): tasking.run(self.runtime,p['task'],p['digest'])

    def test_export_refuses_overwrite_escape_symlink_and_wrong_digest(self):
        p,result=self.done();(self.root/'existing.md').write_text('keep')
        (self.root/'linked').symlink_to(self.root,target_is_directory=True)
        for path in ('../escape.md','.bastion/report.md','existing.md','linked/report.md','missing/report.md'):
            with self.subTest(path=path),self.assertRaises(BastionError): tasking.export(self.runtime,p['task'],result['receiptDigest'],path)
        with self.assertRaisesRegex(BastionError,'digest mismatch'): tasking.export(self.runtime,p['task'],'0'*64,'new.md')
        self.assertEqual((self.root/'existing.md').read_text(),'keep')
        self.assertFalse((self.root/'new.md').exists())

    def test_metric_sample_limit_and_legacy_unknowns(self):
        p,result=self.done()
        # Controlled migration fixture: a historically committed receipt lacking metrics.
        receipt=copy.deepcopy(result['receipt']);receipt.pop('metrics')
        with self.runtime.store.connect(write=True) as db:
            db.execute('UPDATE checks SET receipt=?,receipt_digest=? WHERE id=?',(json.dumps(receipt),digest(receipt),p['task']))
            self.runtime.store.event(db,p['task'],'check-finished',{'receiptDigest':digest(receipt),'passed':True})
        value=summary(self.runtime,1)
        self.assertIsNone(value['sample']['executionMs'])
        self.assertEqual(value['sample']['unmeasuredLegacyReceipts'],1)
        for bad in (0,101,True):
            with self.assertRaises(BastionError): summary(self.runtime,bad)

    def test_tampered_receipt_cannot_be_reported_or_counted_verified(self):
        p,result=self.done()
        with self.runtime.store.connect(write=True) as db: db.execute("UPDATE checks SET receipt_digest=? WHERE id=?",('0'*64,p['task']))
        for operation in (lambda:summary(self.runtime),lambda:tasking.report(self.runtime,p['task'])):
            with self.assertRaises(BastionError): operation()

    def test_mcp_metrics_and_reports_have_no_new_execution_authority(self):
        p,result=self.done()
        tools={t['name']:t for t in listing()['tools']}
        for name in ('bastion_metrics','bastion_task_report'): self.assertTrue(tools[name]['annotations']['readOnlyHint'])
        self.assertNotIn('bastion_task_run',tools)
        self.assertTrue(invoke(self.runtime,'bastion_task_report',{'id':p['task']})['passed'])
        self.assertEqual(invoke(self.runtime,'bastion_metrics',{})['sample']['verifiedReceipts'],1)


class NativeBoundTests(unittest.TestCase):
    def engine(self,code):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        p=Path(temp.name)/'engine';p.write_text('#!'+sys.executable+'\n'+code+'\n');p.chmod(0o700)
        return NativeEngine(str(p),hashlib.sha256(p.read_bytes()).hexdigest())

    def test_native_output_stream_is_bounded_before_buffering(self):
        engine=self.engine('import sys\nsys.stderr.write("x"*100000);sys.stderr.flush()')
        with self.assertRaisesRegex(BastionError,'exceeds contract'): engine.call()
        self.assertEqual(engine.stats['invocations'],1)
        self.assertLessEqual(engine.stats['outputBytes'],12288)

    def test_non_object_sum_response_is_rejected(self):
        engine=self.engine('print("[]")')
        with self.assertRaisesRegex(BastionError,'independent verification'): engine.sum([1,2,3])
        self.assertEqual(engine.stats['invocations'],1)
        self.assertGreater(engine.stats['elapsedMs'],0)
