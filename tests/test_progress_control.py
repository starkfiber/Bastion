import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from bastion import checks,missions
from bastion.core import BastionError
from bastion.progress import changes
from bastion.runtime import Runtime
from bastion.store import Store


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.runtime=Runtime(Store(self.temp.name))

    def event(self,payload):
        with self.runtime.store.connect(write=True) as db: self.runtime.store.event(db,'fixture','probe',payload)

    def test_pagination_restart_and_empty_delta(self):
        for i in range(7): self.event({'index':i})
        cursor=None;seen=[]
        for _ in range(4):
            data=changes(Runtime(Store(self.temp.name)),cursor,2);seen.extend(e['payload']['index'] for e in data['events']);cursor=data['cursor']
        self.assertEqual(seen,list(range(7)))
        self.assertFalse(data['hasMore']);self.assertEqual(changes(self.runtime,cursor)['events'],[])
        self.event({'index':7});self.assertEqual(changes(self.runtime,cursor)['events'][0]['payload']['index'],7)

    def test_foreign_malformed_and_tampered_chain_refused(self):
        self.event({'index':1});token=changes(self.runtime)['cursor']
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(BastionError,'foreign'): changes(Runtime(Store(other)),token)
        for invalid in ('bad%%%','[]','A'*1025):
            with self.assertRaises(BastionError): changes(self.runtime,invalid)
        with self.runtime.store.connect(write=True) as db: db.execute("UPDATE events SET payload='{}'")
        with self.assertRaisesRegex(BastionError,'chain mismatch'): changes(self.runtime)

    def test_payload_cap_and_page_limit(self):
        self.event({'text':'x'*100000});data=changes(self.runtime)
        self.assertTrue(data['events'][0]['payload']['omitted']);self.assertLess(data['payloadBytes'],262144)
        for invalid in (0,101,True):
            with self.assertRaises(BastionError): changes(self.runtime,limit=invalid)


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runtime=Runtime(Store(self.root))

    def workflow(self):
        return self.runtime.plan({'schema':'bastion.workflow.v1','title':'downstream must not execute','nodes':[{'id':'value','capability':'data.value','params':{'value':6}}]})

    def spec(self,jobs):
        return {'goal':'controlled cancellation fixture','jobs':jobs,'notBefore':0,'deadline':time.time()+90,
            'budgets':{'maxJobs':3,'maxAttempts':2,'maxWallSeconds':60,'maxOutputBytes':65536,'maxStateBytes':64*1024*1024}}

    def test_pending_cancel_is_durable_and_never_starts_work(self):
        run=self.workflow();p=missions.plan(self.runtime,self.spec([{'kind':'workflow','run':run['run'],'digest':run['digest']}]))
        with self.assertRaisesRegex(BastionError,'digest mismatch'): missions.cancel(self.runtime,p['mission'],'0'*64,'stop')
        missions.cancel(self.runtime,p['mission'],p['digest'],'operator changed objective')
        result=missions.work(Runtime(Store(self.root)),p['mission'],p['digest'])
        self.assertEqual(result['state'],'cancelled');self.assertEqual(self.runtime.inspect(run['run'])['state'],'draft')
        self.assertEqual(missions.work(self.runtime,p['mission'],p['digest'])['state'],'cancelled')
        with self.assertRaises(BastionError): missions.approve(self.runtime,p['mission'],p['digest'])

    def test_active_code_cancel_keeps_unknown_outcome_and_downstream_unexecuted(self):
        (self.root/'test_slow.py').write_text('import unittest,time\nclass Tests(unittest.TestCase):\n def test_wait(self): time.sleep(20)\n')
        check=checks.plan(self.runtime,{'name':'reviewed sleep fixture','files':['test_slow.py'],'testModules':['test_slow'],'minTests':1,
            'trust':'reviewed-local-code; not-os-sandboxed','budgets':{'wallSeconds':30,'cpuSeconds':5,'outputBytes':65536,'stateBytes':64*1024*1024}})
        tail=self.workflow();p=missions.plan(self.runtime,self.spec([{'kind':'check','run':check['check'],'digest':check['digest']},{'kind':'workflow','run':tail['run'],'digest':tail['digest']}]))
        missions.approve(self.runtime,p['mission'],p['digest'])
        child=subprocess.Popen([sys.executable,'-m','bastion','--workspace',str(self.root),'mission','work',p['mission'],p['digest']],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+8
            while checks.inspect(self.runtime,check['check'])['state']!='running':
                if child.poll() is not None: self.fail('controller ended before running check')
                if time.monotonic()>deadline: self.fail('check did not start')
                time.sleep(.02)
            missions.cancel(self.runtime,p['mission'],p['digest'],'stop controlled sleep; no external actions')
            output,error=child.communicate(timeout=8)
            self.assertEqual(child.returncode,0,error.decode())
            result=json.loads(output);self.assertEqual(result['state'],'cancelled')
            self.assertEqual(result['jobs'][0]['state'],'interrupted')
            self.assertIsNone(checks.inspect(self.runtime,check['check'])['receipt'])
            self.assertEqual(self.runtime.inspect(tail['run'])['state'],'approved')
            # Wait for the nested watchdog to release its execution lock, never rerun it.
            deadline=time.monotonic()+3
            while True:
                try:
                    with self.runtime.store.execution_lock('check-'+check['check']): break
                except BastionError:
                    if time.monotonic()>deadline: raise
                    time.sleep(.02)
            with self.assertRaisesRegex(BastionError,'reconciliation'): checks.run(self.runtime,check['check'],check['digest'])
        finally:
            if child.poll() is None: child.kill();child.communicate()
