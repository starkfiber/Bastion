"""Explicitly run the bundled reviewed repository QA recipe, retain reports, never publish."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',required=True,help='Approve and execute only the bundled reviewed QA specification')
    parser.add_argument('--workspace',default='dist/repository-task')
    parser.add_argument('--native-engine')
    parser.add_argument('--native-sha256')
    args=parser.parse_args()
    if bool(args.native_engine)!=bool(args.native_sha256): parser.error('supply both native path and reviewed SHA-256')
    workspace=Path(args.workspace).resolve()
    if workspace.exists(): raise SystemExit('Use a new workspace; existing evidence is preserved')
    spec=json.loads((ROOT/'demo/repository-qa.json').read_text())
    for name in spec['files']:
        source=ROOT/name
        if not source.is_file() or source.is_symlink(): raise SystemExit('Missing or symlink source: '+name)
    workspace.mkdir(parents=True,mode=0o700)
    for name in spec['files']:
        target=workspace/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    (workspace/'task.json').write_text(json.dumps(spec,indent=2)+'\n')
    def cli(*argv,allow_failed=False):
        command=[sys.executable,'-m','bastion','--workspace',str(workspace),*argv]
        result=subprocess.run(command,cwd=str(ROOT),capture_output=True,text=True,timeout=120)
        if result.returncode and not (allow_failed and result.returncode==1 and result.stdout): raise RuntimeError(result.stderr)
        return json.loads(result.stdout)
    if args.native_engine: cli('native-configure',str(Path(args.native_engine).resolve()),args.native_sha256)
    plan=cli('task','plan','task.json')
    # --run authorizes this exact bundled recipe, not a model-generated manifest.
    cli('task','approve',plan['task'],plan['digest'])
    started=time.monotonic();result=cli('task','run',plan['task'],plan['digest'],allow_failed=True)
    first_ms=(time.monotonic()-started)*1000
    started=time.monotonic();reuse=cli('task','run',plan['task'],plan['digest'],allow_failed=True)
    reuse_ms=(time.monotonic()-started)*1000
    assert reuse['reused'] and reuse['receiptDigest']==result['receiptDigest']
    for format,suffix in [('markdown','md'),('html','html')]: cli('task','export',plan['task'],result['receiptDigest'],'report.'+suffix,'--format',format)
    report=cli('task','report',plan['task']);metrics=cli('metrics')
    (workspace/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (workspace/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    measurement={'schema':'bastion.task-timing.v1','firstRunCliMs':round(first_ms,3),'receiptReuseCliMs':round(reuse_ms,3),
        'sampleCount':1,'scope':'single local observation per operation, includes CLI startup; not a throughput benchmark',
        'task':plan['task'],'receiptDigest':result['receiptDigest'],'passed':result['passed'],'nativeConfigured':bool(args.native_engine)}
    (workspace/'timing.json').write_text(json.dumps(measurement,indent=2)+'\n')
    print(json.dumps({'workspace':str(workspace),'passed':result['passed'],'tests':report['tests'],
        'executionMs':report['metrics']['executionMs'],'native':report['metrics']['native'],
        'receiptReused':True,'timing':measurement,'report':str(workspace/'report.html')}))
    return 0 if result['passed'] else 1


if __name__=='__main__': sys.exit(main())
