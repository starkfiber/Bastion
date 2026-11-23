"""Qualify 0.4 checks against actual Bastion kernel source and a deliberate regression."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ENGINE=(Path.home() / '.codex/plugins/cache/rf2-harness-local/local-ai-harness/0.3.0/bin/rf2-harness')
TESTS='''import unittest
from bastion.core import BastionError, decide, execute_pure, validate_workflow
class KernelTests(unittest.TestCase):
    def test_checked_sum(self):
        self.assertEqual(execute_pure('math.sum_u32',{'values':[1,2,3]}),6)
    def test_overflow(self):
        with self.assertRaises(BastionError): execute_pure('math.sum_u32',{'values':[4294967295,1]})
    def test_approval_boundary(self):
        self.assertFalse(decide('approved','start',False,True,True,True)[0])
    def test_unknown_effect(self):
        with self.assertRaises(BastionError):
            validate_workflow({'schema':'bastion.workflow.v1','title':'Reject shell','nodes':[{'id':'x','capability':'shell.execute','params':{}}]})
'''


def main():
    output=ROOT/'evidence/check-edition-qualification.json'
    if output.exists(): raise SystemExit('Preserve existing qualification before an intentional rerun')
    workspace=Path(tempfile.mkdtemp(prefix='check-edition-',dir=str(ROOT/'evidence')))
    (workspace/'bastion').mkdir()
    for name in ('__init__.py','core.py'):
        (workspace/'bastion'/name).write_bytes((ROOT/'bastion'/name).read_bytes())
    (workspace/'test_kernel.py').write_text(TESTS)
    manifest={'name':'Actual Bastion kernel regression checks','files':['bastion/__init__.py','bastion/core.py','test_kernel.py'],
        'testModules':['test_kernel'],'minTests':4,'trust':'reviewed-local-code; not-os-sandboxed',
        'budgets':{'wallSeconds':10,'cpuSeconds':5,'outputBytes':65536,'stateBytes':64*1024*1024}}
    (workspace/'check.json').write_text(json.dumps(manifest,indent=2)+'\n')

    def cli(*args):
        r=subprocess.run([sys.executable,'-m','bastion','--workspace',str(workspace),*args],cwd=str(ROOT),capture_output=True,text=True,timeout=30)
        if r.returncode: raise RuntimeError(r.stderr)
        return json.loads(r.stdout)

    native=cli('native-configure',str(ENGINE),hashlib.sha256(ENGINE.read_bytes()).hexdigest())
    def execute_case():
        p=cli('check','plan','check.json')
        cli('check','approve',p['check'],p['digest'])
        result=cli('check','run',p['check'],p['digest'])
        verified=cli('check','verify',p['check'])
        if result['receiptDigest']!=verified['receiptDigest']: raise RuntimeError('receipt changed')
        return {'plan':p,'verification':verified}
    good=execute_case()
    if not good['verification']['passed']: raise RuntimeError('original kernel did not pass')
    source=(workspace/'bastion/core.py').read_text()
    if source.count('return total\n')!=1: raise RuntimeError('regression injection anchor changed')
    (workspace/'bastion/core.py').write_text(source.replace('return total\n','return total + 1\n'))
    regression=execute_case()
    if regression['verification']['passed'] or regression['verification']['receipt']['tests']['failures']!=1:
        raise RuntimeError('deliberate regression was not detected')
    repeated=cli('check','run',regression['plan']['check'],regression['plan']['digest'])
    if repeated['receiptDigest']!=regression['verification']['receiptDigest']: raise RuntimeError('failed job reran')
    report={'schema':'bastion.check-edition-qualification.v1','version':cli('init')['version'],'workspace':str(workspace),
        'native':native,'originalKernel':good,'regressedKernel':regression,'repeatReceiptReused':True,
        'scope':'actual pinned kernel source; reviewed local unittest jobs in copied worktrees',
        'isolation':{'osSandboxQualified':False,'probeExit':71,'reason':'sandbox-exec sandbox_apply: Operation not permitted'},
        'limits':['not hostile-code isolation','no external effect control','no automatic code-job retries','not mission-integrated','no live planner or host scheduling']}
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(output),'version':report['version'],'testsPerCase':4,
        'originalPassed':True,'regressionDetected':True,'repeatReceiptReused':True,'osSandboxQualified':False}))


if __name__=='__main__': main()
