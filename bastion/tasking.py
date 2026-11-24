"""Repository QA recipe using existing reviewed-code authority and receipts."""
import hashlib
import os
from pathlib import Path

from . import checks
from .core import BastionError, digest


def plan(runtime, specification):
    if not isinstance(specification,dict) or specification.get('recipe')!='python-unittest':
        raise BastionError('supported task recipe: python-unittest')
    manifest={k:v for k,v in specification.items() if k!='recipe'}
    result=checks.plan(runtime,manifest)
    return dict(result,task=result['check'],recipe='python-unittest',
        acceptance='at least minTests observed, non-skipped tests, passing outcome, unchanged pinned source',
        effects='reviewed Python with host permissions; not OS sandboxed; report export is a separate operator action')


def run(runtime, identity, claimed):
    result=checks.run(runtime,identity,claimed)
    return dict(result,task=identity,reused=result.get('reused',False))


def report(runtime, identity):
    result=checks.verify(runtime,identity)
    item=checks.inspect(runtime,identity)
    receipt=result['receipt']
    return {'schema':'bastion.task-report.v1','task':identity,'name':item['plan']['manifest']['name'],
        'passed':result['passed'],'state':result['state'],'integrityVerified':True,
        'planDigest':item['digest'],'receiptDigest':result['receiptDigest'],
        'sourceFiles':len(item['plan']['sources']),'tests':receipt['tests'],
        'stopReason':receipt['stopReason'],'metrics':receipt.get('metrics'),
        'nativeEngineSha256':(item['plan'].get('native') or {}).get('sha256'),
        'outputBytes':receipt['outputBytes'],
        'scope':'reviewed local Python QA; host permissions; no live planner, deployment or external-effect reconciliation'}


def markdown(value):
    # Plain paragraphs prevent user-selected names from becoming HTML or table cells.
    import html
    tests=value['tests'] or {}
    metrics=value['metrics'] or {}
    native=metrics.get('native')
    rows=[('Outcome','PASS' if value['passed'] else 'FAIL'),('Integrity','verified'),
        ('Source files',value['sourceFiles']),('Tests run',tests.get('testsRun','unavailable')),
        ('Failures',tests.get('failures','unavailable')),('Errors',tests.get('errors','unavailable')),
        ('Skipped',tests.get('skipped','unavailable')),('Execution ms',metrics.get('executionMs','unmeasured')),
        ('Native calls during execution',native['invocations'] if native else 'not configured / unmeasured'),
        ('Captured output bytes',value['outputBytes'])]
    return '# Bastion task report\n\n'+html.escape(value['name'])+'\n\n| Measurement | Observed |\n|---|---:|\n'+''.join('| '+k+' | '+str(v)+' |\n' for k,v in rows)+'\nTask: `'+value['task']+'`\n\nPlan: `'+value['planDigest']+'`\n\nReceipt: `'+value['receiptDigest']+'`\n\n'+value['scope']+'.\n'


def export(runtime, identity, receipt_digest, destination, format="markdown"):
    value=report(runtime,identity)
    if value['receiptDigest']!=receipt_digest: raise BastionError('export receipt digest mismatch')
    if format not in ("markdown","html"): raise BastionError("unknown export format")
    if not isinstance(destination,str): raise BastionError("export destination must be text")
    relative=Path(destination)
    if (not isinstance(destination,str) or relative.is_absolute() or not relative.parts or
            any(p.startswith('.') for p in relative.parts) or destination!=relative.as_posix()):
        raise BastionError('export requires a normalized visible project-relative path')
    parent=runtime.store.workspace
    for part in relative.parts[:-1]:
        parent=parent/part
        if parent.is_symlink() or not parent.is_dir(): raise BastionError('export parent must exist and contain no symlinks')
    target=parent/relative.name
    content=(html_report(value) if format=="html" else markdown(value)).encode()
    try:
        fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except OSError as exc: raise BastionError('export refuses existing or unavailable destination') from exc
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
    except BaseException:
        # Retain an interrupted export for investigation; never overwrite it silently.
        raise
    result={'task':identity,'receiptDigest':receipt_digest,'path':destination,
        'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'passed':value['passed'],'format':format}
    with runtime.store.connect(write=True) as db: runtime.store.event(db,identity,'task-report-exported',result)
    return result


def html_report(value):
    """A static report of observed results; no scripts, fonts or external requests."""
    import html
    esc=lambda text:html.escape(str(text))
    tests=value['tests'] or {};timing=value['metrics'] or {};native=timing.get('native') or {}
    outcome='PASS' if value['passed'] else 'FAIL'
    cards=[('Tests observed',tests.get('testsRun','unknown')),('Execution',str(timing.get('executionMs','unmeasured'))+' ms'),
        ('RF² calls',native.get('invocations','not configured')),('Source pins',value['sourceFiles'])]
    tiles=''.join('<article><span>'+esc(k)+'</span><strong>'+esc(v)+'</strong></article>' for k,v in cards)
    rows=[('Receipt',value['receiptDigest']),('Plan',value['planDigest']),('Task',value['task']),
        ('Native executable SHA-256',value['nativeEngineSha256'] or 'not configured'),
        ('Failures',tests.get('failures','unknown')),('Errors',tests.get('errors','unknown')),
        ('Skipped',tests.get('skipped','unknown')),('Stop reason',value['stopReason'] or 'none recorded')]
    table=''.join('<tr><th scope="row">'+esc(k)+'</th><td>'+esc(v)+'</td></tr>' for k,v in rows)
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bastion task report</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0d1721;color:#edf3f5;font:16px/1.65 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:48px 24px}.eyebrow{color:#8edce4;font-size:13px;letter-spacing:.14em}h1{font-size:clamp(30px,5vw,52px);line-height:1.15;overflow-wrap:anywhere}p{color:#b9cbd2}.status{display:inline-block;padding:8px 16px;border:1px solid currentColor;border-radius:6px;color:'''+('#9de6bf' if value['passed'] else '#ffb4ab')+'''}section{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:36px 0}article{padding:22px;border:1px solid #385061;border-radius:12px;background:#142431}article span{display:block;font-size:14px;color:#b9cbd2}article strong{display:block;font-size:27px;margin-top:10px}table{width:100%;border-collapse:collapse;text-align:left}th,td{padding:16px 8px;border-bottom:1px solid #385061;vertical-align:top}th{width:25%;font-weight:500;color:#b9cbd2}td{font-family:ui-monospace,monospace;font-size:13px;overflow-wrap:anywhere}.note{margin-top:32px;border-left:3px solid #8edce4;padding-left:18px}footer{margin-top:44px;font-size:13px;color:#a2b8c2}@media(max-width:700px){main{padding:28px 18px}section{grid-template-columns:repeat(2,1fr)}th{width:34%}article{padding:16px}article strong{font-size:22px}}
</style></head><body><main><div class="eyebrow">BASTION / RF² · RECEIPT-BACKED QA</div><h1>'''+esc(value['name'])+'</h1><div class="status">'+outcome+''' · receipt integrity verified</div><p>The test outcome and receipt integrity are separate facts. A valid receipt can record a failed task.</p><section aria-label="Observed task metrics">'''+tiles+'</section><h2>Evidence</h2><table>'+table+'''</table><p class="note">'''+esc(value['scope'])+'''. Native call counts cover the managed task's start/outcome gates. Timing covers snapshot creation, test execution and those gates; approval and final verification are excluded. Unmeasured values remain unknown.</p><footer>Static local report · No external requests · No live planner, unattended deployment or OS sandbox claim.</footer></main></body></html>\n'''
