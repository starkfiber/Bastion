"""Bounded receipt-backed usage metrics. No provider telemetry or background service."""
import json
import statistics

from .core import BastionError
from . import checks


def summary(runtime, limit=100):
    if type(limit) is not int or not 1<=limit<=100: raise BastionError('metrics limit must be 1..100')
    audit=runtime.store.verify_events()
    with runtime.store.connect() as db:
        states={table:{r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM '+table+' GROUP BY state')} for table in ('runs','checks','missions')}
        recent=db.execute("SELECT id FROM checks WHERE receipt IS NOT NULL ORDER BY rowid DESC LIMIT ?",(limit,)).fetchall()
        reuse=db.execute("SELECT COUNT(*) AS n FROM events WHERE kind='check-reused'").fetchone()['n']
        exports=db.execute("SELECT COUNT(*) AS n FROM events WHERE kind='task-report-exported'").fetchone()['n']
    receipts=[checks.verify(runtime,row['id'])['receipt'] for row in recent]
    measured=[r['metrics'] for r in receipts if 'metrics' in r]
    native=[m['native'] for m in measured if m.get('native') is not None]
    times=[m['executionMs'] for m in measured]
    return {'schema':'bastion.metrics.v1','stateCounts':states,'receiptReuseEvents':reuse,'reportExportEvents':exports,
        'sample':{'limit':limit,'verifiedReceipts':len(receipts),'passed':sum(r['passed'] for r in receipts),
            'failed':sum(not r['passed'] for r in receipts),'measuredExecutions':len(measured),
            'unmeasuredLegacyReceipts':len(receipts)-len(measured),
            'executionMs':{'median':statistics.median(times),'min':min(times),'max':max(times)} if times else None,
            'observedTests':sum((r.get('tests') or {}).get('testsRun',0) for r in receipts),
            'nativeExecutions':len(native),'nativeInvocations':sum(m['invocations'] for m in native),
            'nativeElapsedMs':round(sum(m['elapsedMs'] for m in native),3)},
        'eventAudit':audit,'scope':'state counts are journal totals; receipt statistics cover newest bounded sample; reuse/export counts are durable events',
        'limits':['No model tokens, spend, inference speed or concurrent-chat capacity is measured.',
            'Native timings include process startup; calls exclude configure/approval and external child activity.',
            'Legacy missing timings are unknown, never zero. No background collection or deletion.',
            'Full event-chain verification is linear in retained history; receipt verification is limited by the requested sample.']}
