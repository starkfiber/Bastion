"""Retain native-backed mixed missions, regression blocking and explicit correction approval."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.native_fixture import require_native_fixture


def main():
    engine = require_native_fixture()
    output=ROOT/'evidence/mixed-mission-qualification.json'
    if output.exists(): raise SystemExit('Preserve existing mixed-mission qualification before rerunning')
    workspace=Path(tempfile.mkdtemp(prefix='mixed-mission-',dir=str(ROOT/'evidence')))
    (workspace/'bastion').mkdir()
    for name in ('__init__.py','core.py'): (workspace/'bastion'/name).write_bytes((ROOT/'bastion'/name).read_bytes())
    original=(workspace/'bastion/core.py').read_text()
    tests=runpy.run_path(str(ROOT/'tools/qualify_checks.py'))['TESTS']
    (workspace/'test_kernel.py').write_text(tests)
    manifest={'name':'Reviewed kernel tests inside a mission','files':['bastion/__init__.py','bastion/core.py','test_kernel.py'],
        'testModules':['test_kernel'],'minTests':4,'trust':'reviewed-local-code; not-os-sandboxed',
        'budgets':{'wallSeconds':10,'cpuSeconds':5,'outputBytes':65536,'stateBytes':64*1024*1024}}
    (workspace/'check.json').write_text(json.dumps(manifest,indent=2)+'\n')
    def cli(*args,expect_failure=False):
        result=subprocess.run([sys.executable,'-m','bastion','--workspace',str(workspace),*args],cwd=str(ROOT),capture_output=True,text=True,timeout=60)
        if expect_failure:
            if result.returncode==0: raise RuntimeError('expected a blocked operation')
            return json.loads(result.stderr)
        if result.returncode: raise RuntimeError(result.stderr)
        return json.loads(result.stdout)
    native=cli('native-configure',str(engine.path),engine.sha256)
    def wf():
        value={'schema':'bastion.workflow.v1','title':'Native local workflow','nodes':[{'id':'sum','capability':'math.sum_u32','params':{'values':[1,2,3]}}]}
        (workspace/'workflow.json').write_text(json.dumps(value))
        result=cli('plan','workflow.json')
        return {'kind':'workflow','run':result['run'],'digest':result['digest']}
    def check():
        result=cli('check','plan','check.json')
        return {'kind':'check','run':result['check'],'digest':result['digest']}
    def mission(jobs):
        spec={'goal':'Native workflow, reviewed kernel checks, then downstream workflow','jobs':jobs,
            'notBefore':0,'deadline':time.time()+120,'budgets':{'maxJobs':3,'maxAttempts':2,'maxWallSeconds':60,'maxOutputBytes':65536,'maxStateBytes':64*1024*1024}}
        (workspace/'mission.json').write_text(json.dumps(spec,indent=2))
        result=cli('mission','plan','mission.json')
        cli('mission','approve',result['mission'],result['digest'])
        return result
    passed=mission([wf(),check(),wf()])
    first=cli('mission','work',passed['mission'],passed['digest'])
    if first['state']!='complete': raise RuntimeError('mixed mission did not pass')
    (workspace/'bastion/core.py').write_text(original.replace('return total\n','return total + 1\n'))
    prefix,bad,downstream=wf(),check(),wf()
    blocked=mission([prefix,bad,downstream])
    blocked_error=cli('mission','work',blocked['mission'],blocked['digest'],expect_failure=True)
    before=cli('mission','inspect',blocked['mission'])
    failed_receipt=cli('check','verify',bad['run'])
    retry_error=cli('mission','work',blocked['mission'],blocked['digest'],expect_failure=True)
    if cli('mission','inspect',blocked['mission'])['jobs'][1]['attempts']!=1: raise RuntimeError('failed code retried implicitly')
    if cli('inspect',downstream['run'])['state']!='approved': raise RuntimeError('downstream workflow executed despite failure')
    prefix_receipt=cli('verify',prefix['run'])['receiptDigest']
    (workspace/'bastion/core.py').write_text(original)
    replacement=check()
    corrected=cli('mission','replace-check',blocked['mission'],blocked['digest'],'1',replacement['run'],replacement['digest'],
        '--reason','Controlled synthetic kernel regression corrected and reviewed; no external fixture effects requested')
    approval_error=cli('mission','work',corrected['mission'],corrected['digest'],expect_failure=True)
    cli('mission','approve',corrected['mission'],corrected['digest'])
    after=cli('mission','work',corrected['mission'],corrected['digest'])
    if after['state']!='complete' or cli('verify',prefix['run'])['receiptDigest']!=prefix_receipt: raise RuntimeError('corrected mission/prefix reuse failed')
    report={'schema':'bastion.mixed-mission-qualification.v1','version':cli('init')['version'],'workspace':str(workspace),
        'native':native,'passingMission':passed,'passingResult':first,'blockedMission':blocked,'blockedResult':before,
        'blockedError':blocked_error,'failedCheck':failed_receipt,'implicitRetryRefusal':retry_error,
        'replacementMission':corrected,'newApprovalRequired':approval_error,'correctedResult':after,'prefixReceiptReused':True,
        'readiness':cli('readiness'),'scope':'synthetic native-backed workflow/check pipelines and operator-approved correction',
        'limits':['trusted code; no worker OS isolation','no live planner','no installed scheduler','no named-chat dispatch','operator note is not proof of external reconciliation']}
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(output),'version':report['version'],'passingMission':'complete','regressionBlocked':True,
        'implicitRetryRefused':True,'newApprovalRequired':True,'correctedMission':after['state'],'prefixReceiptReused':True,
        'OSIsolation':report['readiness']['checkWorkerEnforcesOSIsolation']}))


if __name__=='__main__': main()
