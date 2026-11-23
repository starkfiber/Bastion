"""Local CLI timing samples, not an AI/model speed benchmark."""
import argparse
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=int,default=15)
    parser.add_argument('--out',default='docs/assets/performance.json')
    args=parser.parse_args()
    if not 5<=args.samples<=30: parser.error('samples must be 5..30')
    timings={'four_process_workflow_cycle':[],'verified_receipt_reuse':[],'brain_context_query':[]}
    workflow={'schema':'bastion.workflow.v1','title':'CLI timing fixture','nodes':[{'id':'sum','capability':'math.sum_u32','params':{'values':[1,2,3]}}]}
    with tempfile.TemporaryDirectory(prefix='bastion-timing-') as d:
        workspace=Path(d); (workspace/'workflow.json').write_text(json.dumps(workflow))
        def cli(*argv):
            p=subprocess.run([sys.executable,'-m','bastion','--workspace',str(workspace),*argv],cwd=str(ROOT),capture_output=True,text=True,timeout=20)
            if p.returncode: raise RuntimeError(p.stderr)
            return json.loads(p.stdout)
        cli('init')
        for _ in range(args.samples):
            start=time.perf_counter()
            p=cli('plan','workflow.json'); cli('approve',p['run'],p['digest'])
            run=cli('run',p['run'],p['digest']); cli('verify',p['run'])
            timings['four_process_workflow_cycle'].append((time.perf_counter()-start)*1000)
            start=time.perf_counter(); repeated=cli('run',p['run'],p['digest'])
            timings['verified_receipt_reuse'].append((time.perf_counter()-start)*1000)
            assert repeated['receiptDigest']==run['receiptDigest']
            start=time.perf_counter(); cli('brain','timing')
            timings['brain_context_query'].append((time.perf_counter()-start)*1000)
    result={'version':'0.5.0','capturedAtUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'environment':{'os':platform.system(),'architecture':platform.machine(),'python':platform.python_version()},
        'samples':args.samples,'nativeEngineConfigured':False,'providerCalls':False,
        'scope':'tiny synthetic fixture, local CLI startup plus journal work; one unrecorded init warm-up',
        'metrics':{k:{'medianMs':statistics.median(v),'minMs':min(v),'maxMs':max(v),'samplesMs':v} for k,v in timings.items()},
        'limitations':['Not model inference or end-to-end MVP speed.','Not a cross-machine or competitor comparison.','Small samples under uncontrolled host load.','Brain query matches no stored knowledge in this fixture.']}
    path=Path(args.out); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:round(v['medianMs'],2) for k,v in result['metrics'].items()}))


if __name__=='__main__': main()
