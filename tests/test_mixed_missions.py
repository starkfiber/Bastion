import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from bastion import checks, missions, readiness
from bastion.core import BastionError
from bastion.runtime import Runtime
from bastion.store import Store


class MixedMissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.store=Store(self.root); self.runtime=Runtime(self.store)

    def _workflow(self):
        p=self.runtime.plan({'schema':'bastion.workflow.v1','title':'Mixed mission prefix','nodes':[{'id':'value','capability':'data.value','params':{'value':7}}]})
        return {'kind':'workflow','run':p['run'],'digest':p['digest']}

    def _check(self, body='self.assertEqual(2+3,5)'):
        (self.root/'test_job.py').write_text('import unittest\nclass Tests(unittest.TestCase):\n def test_job(self):\n  '+body+'\n')
        manifest={'name':'Reviewed mission check','files':['test_job.py'],'testModules':['test_job'],'minTests':1,
            'trust':'reviewed-local-code; not-os-sandboxed','budgets':{'wallSeconds':10,'cpuSeconds':5,'outputBytes':65536,'stateBytes':64*1024*1024}}
        p=checks.plan(self.runtime,manifest)
        return {'kind':'check','run':p['check'],'digest':p['digest']}

    def _plan(self,jobs):
        return missions.plan(self.runtime,{'goal':'Run reviewed typed jobs','jobs':jobs,'notBefore':0,'deadline':time.time()+120,
            'budgets':{'maxJobs':10,'maxAttempts':2,'maxWallSeconds':60,'maxOutputBytes':65536,'maxStateBytes':64*1024*1024}})

    def _approve(self,p): missions.approve(self.runtime,p['mission'],p['digest'])

    def test_mixed_pipeline_passes_and_preserves_typed_receipts(self):
        jobs=[self._workflow(),self._check(),self._workflow()]
        p=self._plan(jobs); self.assertEqual(p['plan']['schema'],'bastion.mission.v2')
        self.assertFalse(p['plan']['effects'][1]['OSIsolation'])
        self.assertFalse(p['plan']['effects'][1]['externalEffectsControlled'])
        self.assertIn('test_job.py',p['plan']['effects'][1]['sources'])
        self._approve(p)
        result=missions.work(self.runtime,p['mission'],p['digest'])
        self.assertEqual(result['state'],'complete')
        self.assertEqual([j['kind'] for j in result['jobs']],['workflow','check','workflow'])
        self.assertEqual([j['attempts'] for j in result['jobs']],[1,1,1])
        repeated=missions.work(Runtime(Store(self.root)),p['mission'],p['digest'])
        self.assertEqual(result['jobs'],repeated['jobs'])

    def test_failure_blocks_downstream_and_never_retries_code(self):
        jobs=[self._workflow(),self._check('self.fail("intentional fixture")'),self._workflow()]
        p=self._plan(jobs); self._approve(p)
        with self.assertRaisesRegex(BastionError,'check failed'): missions.work(self.runtime,p['mission'],p['digest'])
        receipt=checks.verify(self.runtime,jobs[1]['run'])['receiptDigest']
        self.assertEqual(self.runtime.inspect(jobs[2]['run'])['state'],'approved')
        with self.assertRaisesRegex(BastionError,'reconciliation'): missions.work(self.runtime,p['mission'],p['digest'])
        self.assertEqual(missions.inspect(self.runtime,p['mission'])['jobs'][1]['attempts'],1)
        self.assertEqual(checks.verify(self.runtime,jobs[1]['run'])['receiptDigest'],receipt)

    def test_receipt_committed_before_mission_crash_is_adopted_without_rerun(self):
        ref=self._check(); p=self._plan([ref]); self._approve(p)
        receipt=checks.run(self.runtime,ref['run'],ref['digest'])
        with self.store.connect(write=True) as db:
            db.execute("UPDATE missions SET state='running' WHERE id=?",(p['mission'],))
            db.execute("UPDATE mission_jobs SET state='running',attempts=1 WHERE mission=?",(p['mission'],))
        result=missions.work(self.runtime,p['mission'],p['digest'])
        self.assertEqual(result['state'],'complete'); self.assertEqual(result['jobs'][0]['attempts'],1)
        self.assertEqual(result['jobs'][0]['receipt'],receipt['receiptDigest'])

    def test_replacement_is_a_new_unapproved_mission_with_original_deadline(self):
        prefix=self._workflow(); bad=self._check('self.fail("known failure")')
        p=self._plan([prefix,bad]); self._approve(p)
        with self.assertRaises(BastionError): missions.work(self.runtime,p['mission'],p['digest'])
        old_receipt=self.runtime.verify(prefix['run'])['receiptDigest']
        fresh=self._check()
        new=missions.replace_check(self.runtime,p['mission'],p['digest'],1,fresh['run'],fresh['digest'],'Reviewed fixture correction; no external effects occurred')
        self.assertEqual(new['state'],'draft'); self.assertEqual(new['plan']['deadline'],p['plan']['deadline'])
        self.assertLessEqual(new['plan']['budgets']['maxWallSeconds'],p['plan']['budgets']['maxWallSeconds'])
        self.assertEqual(new['plan']['supersedes']['mission'],p['mission'])
        self.assertFalse(new['plan']['supersedes']['externalReconciliationProven'])
        with self.assertRaisesRegex(BastionError,'not approved'): missions.work(self.runtime,new['mission'],new['digest'])
        self._approve(new)
        self.assertEqual(missions.work(self.runtime,new['mission'],new['digest'])['state'],'complete')
        self.assertEqual(missions.inspect(self.runtime,p['mission'])['state'],'blocked')
        self.assertEqual(self.runtime.verify(prefix['run'])['receiptDigest'],old_receipt)

    def test_replacement_cannot_reset_exhausted_wall_budget(self):
        bad=self._check('self.fail("known failure")'); p=self._plan([bad]); self._approve(p)
        with self.assertRaises(BastionError): missions.work(self.runtime,p['mission'],p['digest'])
        with self.store.connect(write=True) as db: db.execute('UPDATE missions SET started=? WHERE id=?',(time.time()-70,p['mission']))
        fresh=self._check()
        with self.assertRaisesRegex(BastionError,'cannot reset'): missions.replace_check(self.runtime,p['mission'],p['digest'],0,fresh['run'],fresh['digest'],'operator review')

    def test_waiting_to_approve_a_replacement_does_not_extend_original_wall_deadline(self):
        bad=self._check('self.fail("known failure")'); p=self._plan([bad]); self._approve(p)
        with self.assertRaises(BastionError): missions.work(self.runtime,p['mission'],p['digest'])
        fresh=self._check()
        new=missions.replace_check(self.runtime,p['mission'],p['digest'],0,fresh['run'],fresh['digest'],'operator review')
        self._approve(new)
        with patch('bastion.missions.time.time',return_value=new['plan']['supersedes']['wallDeadline']+1):
            with self.assertRaisesRegex(BastionError,'wall-time'): missions.work(self.runtime,new['mission'],new['digest'])

    def test_typed_job_tampering_is_refused(self):
        p=self._plan([self._check()])
        with self.store.connect(write=True) as db: db.execute("UPDATE mission_jobs SET kind='workflow' WHERE mission=?",(p['mission'],))
        with self.assertRaisesRegex(BastionError,'identity'): missions.inspect(self.runtime,p['mission'])

    def test_real_parent_death_leaves_code_uncertain_and_does_not_rerun(self):
        ref=self._check('__import__("time").sleep(5)'); p=self._plan([ref]); self._approve(p)
        child=subprocess.Popen([sys.executable,'-m','bastion','--workspace',str(self.root),'mission','work',p['mission'],p['digest']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+5
            while checks.inspect(self.runtime,ref['run'])['state']!='running':
                if child.poll() is not None or time.monotonic()>deadline: self.fail('check did not start')
                time.sleep(0.01)
            child.kill(); child.wait(timeout=5)
            deadline=time.monotonic()+5
            while True:
                try:
                    with self.store.execution_lock('check-'+ref['run']): pass
                    break
                except BastionError:
                    if time.monotonic()>deadline: self.fail('check worker did not release its lock')
                    time.sleep(0.05)
            with self.assertRaisesRegex(BastionError,'reconciliation'): missions.work(self.runtime,p['mission'],p['digest'])
            self.assertEqual(missions.inspect(self.runtime,p['mission'])['jobs'][0]['attempts'],1)
        finally:
            if child.poll() is None: child.kill(); child.wait()

    def test_legacy_schema_migration_defaults_existing_jobs_to_workflow(self):
        with tempfile.TemporaryDirectory() as other:
            root=Path(other)/'.bastion'; root.mkdir(mode=0o700)
            database=root/'state.sqlite3'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE mission_jobs(mission TEXT,position INTEGER,run TEXT,digest TEXT,state TEXT,attempts INTEGER,receipt TEXT,output_bytes INTEGER,error TEXT,PRIMARY KEY(mission,position))')
                db.execute("INSERT INTO mission_jobs VALUES('old',0,'job','digest','pending',0,NULL,NULL,NULL)")
            database.chmod(0o600)
            migrated=Store(other)
            with migrated.connect() as db:
                row=db.execute('SELECT * FROM mission_jobs').fetchone()
                self.assertEqual(row['kind'],'workflow'); self.assertEqual(row['digest'],'digest')

    def test_readiness_never_equates_availability_with_worker_isolation(self):
        result=readiness.inspect()
        self.assertFalse(result['checkWorkerEnforcesOSIsolation'])
        self.assertFalse(result['livePlannerQualified'])
        self.assertIn('boundariesMeasured',result['isolationProbe'])

    def test_concurrent_startup_migration_keeps_existing_jobs(self):
        with tempfile.TemporaryDirectory() as other:
            root=Path(other)/'.bastion'; root.mkdir(mode=0o700); database=root/'state.sqlite3'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE mission_jobs(mission TEXT,position INTEGER,run TEXT,digest TEXT,state TEXT,attempts INTEGER,receipt TEXT,output_bytes INTEGER,error TEXT,PRIMARY KEY(mission,position))')
                db.execute("INSERT INTO mission_jobs VALUES('old',0,'job','digest','pending',0,NULL,NULL,NULL)")
            database.chmod(0o600)
            with ThreadPoolExecutor(max_workers=8) as pool:
                stores=list(pool.map(lambda _:Store(other),range(8)))
            with stores[0].connect() as db:
                self.assertEqual(db.execute('SELECT kind FROM mission_jobs').fetchone()[0],'workflow')
                self.assertEqual(db.execute('SELECT count(*) FROM mission_jobs').fetchone()[0],1)
