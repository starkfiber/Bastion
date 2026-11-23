"""Project-bound, bounded delta progress. Cursors are integrity anchors, not credentials."""
import base64
import json

from .core import BastionError, canonical, digest

ZERO='0'*64


def cursor(journal,seq,head):
    return base64.urlsafe_b64encode(canonical({'journal':journal,'seq':seq,'head':head}).encode()).decode().rstrip('=')


def changes(runtime,after=None,limit=50):
    if type(limit) is not int or not 1<=limit<=100: raise BastionError('progress limit must be 1..100')
    with runtime.store.connect() as db:
        journal=digest({'id':json.loads(db.execute("SELECT value FROM settings WHERE key='journal-id'").fetchone()['value']),'workspace':str(runtime.store.workspace)})
        seq,head=0,ZERO
        if after is not None:
            try:
                if not isinstance(after,str) or len(after)>1024: raise ValueError()
                token=json.loads(base64.b64decode(after+'='*((-len(after))%4),altchars=b'-_',validate=True))
                if set(token)!={'journal','seq','head'} or token['journal']!=journal or type(token['seq']) is not int or token['seq']<0: raise ValueError()
                seq,head=token['seq'],token['head']
                anchor=db.execute('SELECT digest FROM events WHERE seq=?',(seq,)).fetchone()
                if (seq==0 and head!=ZERO) or (seq>0 and (not anchor or anchor['digest']!=head)): raise ValueError()
            except (ValueError,TypeError,KeyError,UnicodeError) as exc: raise BastionError('invalid, missing-history or foreign progress cursor') from exc
        rows=db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?',(seq,limit+1)).fetchall()
        events=[];used=0
        for row in rows[:limit]:
            payload=json.loads(row['payload'])
            data={'run':row['run'],'kind':row['kind'],'payload':payload,'previous':head}
            if row['seq']!=seq+1 or row['previous']!=head or digest(data)!=row['digest']: raise BastionError('progress event chain mismatch')
            event={'seq':row['seq'],'run':row['run'],'kind':row['kind'],'payload':payload,'digest':row['digest']}
            if len(canonical(event).encode())>65536:
                event['payload']={'omitted':True,'sha256':digest(payload),'bytes':len(canonical(payload).encode())}
            size=len(canonical(event).encode())
            if events and used+size>262144: break
            events.append(event);used+=size;seq,head=row['seq'],row['digest']
        latest=db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
        totals={table:{r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM '+table+' GROUP BY state')} for table in ('runs','checks','missions')}
    return {'schema':'bastion.progress.v1','events':events,'cursor':cursor(journal,seq,head),'hasMore':seq<latest,
        'stateCounts':totals,'payloadBytes':used,'authority':'data only; no dispatch or approval',
        'scope':'delta chain from supplied anchor; not a full historical audit or cryptographic authentication'}
