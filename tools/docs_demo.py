"""Capture a synthetic CLI walkthrough; requires explicit --run and uses no provider."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def capture():
    trace=[]
    with tempfile.TemporaryDirectory(prefix='bastion-docs-') as folder:
        workspace=Path(folder)
        for name in ('workflow.json','brief.txt'): shutil.copyfile(ROOT/'demo'/name,workspace/name)
        def cli(*args):
            result=subprocess.run([sys.executable,'-m','bastion','--workspace',str(workspace),*args],cwd=str(ROOT),capture_output=True,text=True,timeout=20)
            if result.returncode: raise RuntimeError(result.stderr)
            data=json.loads(result.stdout)
            trace.append({'command':['python3','-m','bastion','--workspace','<demo-workspace>',*args],
                'exitCode':result.returncode,'response':json.loads(json.dumps(data).replace(str(workspace),'<demo-workspace>'))})
            return data
        p=cli('plan','workflow.json')
        cli('inspect',p['run'])
        cli('approve',p['run'],p['digest'])
        result=cli('run',p['run'],p['digest'])
        verified=cli('verify',p['run'])
        reused=cli('run',p['run'],p['digest'])
        context=cli('brain','model')
        assert result['receipt']['outputs']['sum']==6
        assert result['receiptDigest']==verified['receiptDigest']==reused['receiptDigest']
        return {'version':'0.5.0','scope':'synthetic six-node CLI fixture; temporary state removed after capture',
            'pathsRedacted':True,'sum':6,'receiptReused':True,'contextNodes':len(context['nodes']),'trace':trace}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',required=True,help='Explicitly approve and execute the bundled synthetic demo only')
    parser.add_argument('--report',default='docs/assets/walkthrough.json')
    args=parser.parse_args()
    data=capture(); path=Path(args.report); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'report':str(path),'sum':6,'receiptReused':True,'providerCalls':False}))


if __name__=='__main__': main()
