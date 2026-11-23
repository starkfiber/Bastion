"""Durable, explicitly approved local workflow batches. No chat or desktop dispatch."""
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import uuid

from .core import BastionError, canonical, digest, identifier
from .runtime import Runtime
from .store import Store, runtime_digest


def storage(store):
    total = 0
    for path in store.root.rglob("*"):
        if path.is_symlink():
            raise BastionError("state storage contains symlink")
        if path.is_file():
            total += path.stat().st_size
    return total


def references(value):
    return value['jobs'] if 'jobs' in value else [dict(r,kind='workflow') for r in value['runs']]


def job_inspect(runtime, ref):
    if ref.get('kind','workflow')=='check':
        from . import checks
        return checks.inspect(runtime,ref['run'])
    return runtime.inspect(ref['run'])


def job_verify(runtime, ref):
    if ref.get('kind','workflow')=='check':
        from . import checks
        result=checks.verify(runtime,ref['run'])
        if not result['passed']: raise BastionError('mission code check failed; reconcile with a newly approved check')
        return result
    return runtime.verify(ref['run'])


def plan(runtime, spec, supersedes=None):
    if not isinstance(spec, dict) or set(spec) not in ({"goal", "runs", "notBefore", "deadline", "budgets"}, {"goal", "jobs", "notBefore", "deadline", "budgets"}):
        raise BastionError("invalid mission fields")
    if not isinstance(spec["goal"], str) or not spec["goal"].strip() or len(spec["goal"]) > 8000:
        raise BastionError("mission goal requires 1..8000 characters")
    for name in ("notBefore", "deadline"):
        if type(spec[name]) not in (int, float) or not math.isfinite(spec[name]):
            raise BastionError("mission times must be finite Unix seconds")
    if not time.time() < spec["deadline"] <= time.time() + 86400 or not 0 <= spec["notBefore"] < spec["deadline"]:
        raise BastionError("mission requires a future deadline within 24 hours")
    budgets = spec["budgets"]
    limits = {"maxJobs": (1, 100), "maxAttempts": (1, 3), "maxWallSeconds": (1, 86400),
              "maxOutputBytes": (1024, 1048576), "maxStateBytes": (1048576, 1073741824)}
    if not isinstance(budgets, dict) or set(budgets) != set(limits):
        raise BastionError("invalid mission budgets")
    if any(type(budgets[k]) is not int or not lo <= budgets[k] <= hi for k, (lo, hi) in limits.items()):
        raise BastionError("invalid mission budget range")
    runs = spec.get('jobs',spec.get('runs'))
    if not isinstance(runs, list) or not 1 <= len(runs) <= budgets["maxJobs"]:
        raise BastionError("mission job count exceeds budget")
    expected={'kind','run','digest'} if 'jobs' in spec else {'run','digest'}
    if any(not isinstance(r, dict) or set(r) != expected for r in runs):
        raise BastionError("mission requires exact run/digest references")
    if any(r.get('kind','workflow') not in ('workflow','check') for r in runs):
        raise BastionError('unsupported mission job kind')
    if len({(r.get('kind','workflow'),r["run"]) for r in runs}) != len(runs):
        raise BastionError("duplicate mission run")
    effects=[]
    for ref in runs:
        state = job_inspect(runtime,ref)
        allowed=('draft','approved','passed') if ref.get('kind')=='check' else ('draft','approved','verified')
        if state["digest"] != ref["digest"] or state["state"] not in allowed:
            raise BastionError("mission run not ready or digest mismatch")
        if ref.get('kind')=='check':
            effects.append({'kind':'check','manifest':state['plan']['manifest'],'sources':state['plan']['sources'],
                'externalEffectsControlled':False,'OSIsolation':False,'recovery':'operator replacement only; no implicit retry'})
        else:
            effects.append({'kind':'workflow','capabilities':sorted({n['capability'] for n in state['plan']['workflow']['nodes']}),
                'externalEffects':False,'recovery':'approved idempotent local recovery'})
    value = dict(spec, schema="bastion.mission.v2" if 'jobs' in spec else "bastion.mission.v1", workspace=str(runtime.store.workspace), runtimeDigest=runtime_digest(),
                 native=runtime.native.identity if runtime.native else None,
                 recovery="workflow: approved idempotent recovery; check: never implicitly retry code",
                 threadScope="this-project; no host chat dispatch")
    if supersedes is not None: value['supersedes']=supersedes
    if 'jobs' in spec: value['effects']=effects
    if len(canonical(value).encode())>1024*1024: raise BastionError('mission plan exceeds 1 MiB; split the batch')
    identity, sha = uuid.uuid4().hex, digest(value)
    with runtime.store.connect(write=True) as db:
        db.execute("INSERT INTO missions(id,plan,digest,state) VALUES(?,?,?,'draft')", (identity, canonical(value), sha))
        for index, ref in enumerate(runs):
            db.execute("INSERT INTO mission_jobs(mission,position,run,digest,state,attempts,kind) VALUES(?,?,?,?,'pending',0,?)",
                       (identity, index, ref["run"], ref["digest"],ref.get('kind','workflow')))
        runtime.store.event(db, identity, "mission-planned", {"digest": sha})
    return {"mission": identity, "digest": sha, "state": "draft", "plan": value}


def inspect(runtime, identity):
    identifier(identity)
    with runtime.store.connect() as db:
        row = db.execute("SELECT * FROM missions WHERE id=?", (identity,)).fetchone()
        if not row:
            raise BastionError("mission not found")
        value = json.loads(row["plan"])
        if digest(value) != row["digest"] or value["workspace"] != str(runtime.store.workspace):
            raise BastionError("mission identity mismatch")
        jobs = [dict(r) for r in db.execute("SELECT * FROM mission_jobs WHERE mission=? ORDER BY position", (identity,))]
    if ([{"kind":r['kind'],"run": r["run"], "digest": r["digest"]} for r in jobs] != references(value) or
            [r["position"] for r in jobs] != list(range(len(jobs)))):
        raise BastionError("mission job identity mismatch")
    if row["state"] == "complete" and any(r["state"] != "done" for r in jobs):
        raise BastionError("mission completion evidence incomplete")
    return {"mission": identity, "digest": row["digest"], "state": row["state"], "approved": row["approved"],
            "started": row["started"], "error": row["error"], "plan": value, "jobs": jobs}


def bound(runtime, identity, claimed):
    result = inspect(runtime, identity)
    if result["digest"] != claimed or result["plan"]["runtimeDigest"] != runtime_digest():
        raise BastionError("mission digest or runtime changed")
    if result["plan"]["native"] != (runtime.native.identity if runtime.native else None):
        raise BastionError("mission native identity changed")
    return result


def approve(runtime, identity, claimed):
    with runtime.store.execution_lock("mission-" + identity):
        result = bound(runtime, identity, claimed)
        if result["state"] not in ("draft", "approved") or time.time() >= result["plan"]["deadline"]:
            raise BastionError("mission cannot be approved")
        # Full preflight first. Individual approved runs remain independently inspectable.
        for ref in result["jobs"]:
            if ref['kind']=='check':
                from . import checks
                checks.bound(runtime,ref['run'],ref['digest'],live=True)
            else:
                with runtime.store.connect() as db:
                    runtime.bound(runtime.row(db, ref["run"]), ref["digest"], live=True)
        for ref in result["jobs"]:
            if ref['kind']=='check':
                from . import checks
                if checks.inspect(runtime,ref['run'])['state']!='passed': checks.approve(runtime,ref['run'],ref['digest'])
            elif runtime.inspect(ref["run"])["state"] != "verified":
                runtime.approve(ref["run"], ref["digest"])
        with runtime.store.connect(write=True) as db:
            db.execute("UPDATE missions SET approved=?,state='approved' WHERE id=?", (claimed, identity))
            runtime.store.event(db, identity, "mission-approved", {"digest": claimed})
    return {"mission": identity, "digest": claimed, "state": "approved"}


def run_child(runtime, ref, deadline, output_budget, state_budget):
    command = [sys.executable, "-m", "bastion.worker", str(runtime.store.workspace), ref["run"], ref["digest"],
               str(os.getpid()), str(max(0.001, deadline - time.monotonic())), str(state_budget),ref.get('kind','workflow')]
    process = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    monitor = selectors.DefaultSelector()
    for pipe in (process.stdout, process.stderr):
        monitor.register(pipe, selectors.EVENT_READ)
    seen, error = 0, None
    try:
        while monitor.get_map():
            if time.monotonic() >= deadline:
                error = "mission wall-time budget exhausted"
                break
            if storage(runtime.store) > state_budget:
                error = "mission state budget exhausted"
                break
            for key, _ in monitor.select(timeout=0.05):
                data = os.read(key.fd, 4096)
                seen += len(data)
                if not data:
                    monitor.unregister(key.fileobj)
                if seen > output_budget:
                    error = "mission output budget exhausted"
                    break
            if error:
                break
        if error:
            raise BastionError(error)
        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if code:
            raise BastionError("job child failed; inspect retained evidence before any code retry")
    finally:
        # The whole child group is ours, including native descendants. Never leave it detached.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        monitor.close()
        process.stdout.close()
        process.stderr.close()
    return seen


def work(runtime, identity, claimed):
    with runtime.store.execution_lock("mission-" + identity):
        result = bound(runtime, identity, claimed)
        if result["approved"] != claimed or result["state"] not in ("approved", "running", "blocked", "complete"):
            raise BastionError("mission is not approved")
        if result["state"] == "complete":
            for ref in result["jobs"]:
                if job_verify(runtime,ref)["receiptDigest"] != ref["receipt"]:
                    raise BastionError("mission receipt mismatch")
            return inspect(runtime, identity)
        value, budgets = result["plan"], result["plan"]["budgets"]
        if time.time() < value["notBefore"]:
            return {"mission": identity, "state": "waiting", "notBefore": value["notBefore"]}
        started = result["started"] or time.time()
        wall_deadline = min(value["deadline"], started + budgets["maxWallSeconds"],value.get('supersedes',{}).get('wallDeadline',float('inf')))
        with runtime.store.connect(write=True) as db:
            db.execute("UPDATE missions SET state='running',started=?,error=NULL WHERE id=?", (started, identity))
        try:
            for ref in result["jobs"]:
                if ref["state"] == "done":
                    if job_verify(runtime,ref)["receiptDigest"] != ref["receipt"]:
                        raise BastionError("mission receipt mismatch")
                    continue
                if time.time() >= wall_deadline:
                    raise BastionError("mission deadline or wall-time budget exhausted")
                if storage(runtime.store) >= budgets["maxStateBytes"]:
                    raise BastionError("mission state budget exhausted")
                state = job_inspect(runtime,ref)["state"]
                if ref['kind']=='check' and state=='passed':
                    verified=job_verify(runtime,ref)
                    with runtime.store.connect(write=True) as db:
                        db.execute("UPDATE mission_jobs SET state='done',receipt=?,output_bytes=0 WHERE mission=? AND position=?",
                                   (verified['receiptDigest'],identity,ref['position']))
                        runtime.store.event(db,identity,'mission-check-receipt-adopted',{'check':ref['run'],'receipt':verified['receiptDigest']})
                    continue
                if ref['kind']=='check' and state!='approved':
                    raise BastionError('code check needs reconciliation; failed/interrupted code is never implicitly retried')
                if ref["attempts"] >= budgets["maxAttempts"]:
                    raise BastionError("mission attempt budget exhausted")
                if ref['kind']=='workflow' and state in ("running", "uncertain", "failed"):
                    # Kernel locks prove the previous workflow worker is no longer active.
                    runtime.recover(ref["run"], ref["digest"])
                with runtime.store.connect(write=True) as db:
                    db.execute("UPDATE mission_jobs SET state='running',attempts=attempts+1,error=NULL WHERE mission=? AND position=?",
                               (identity, ref["position"]))
                remaining = wall_deadline - time.time()
                used = run_child(runtime, ref, time.monotonic() + remaining, budgets["maxOutputBytes"], budgets["maxStateBytes"])
                verified = job_verify(runtime,ref)
                if storage(runtime.store) > budgets["maxStateBytes"]:
                    raise BastionError("mission state budget exhausted")
                with runtime.store.connect(write=True) as db:
                    db.execute("UPDATE mission_jobs SET state='done',receipt=?,output_bytes=? WHERE mission=? AND position=?",
                               (verified["receiptDigest"], used, identity, ref["position"]))
                    runtime.store.event(db, identity, "mission-job-verified", {"run": ref["run"], "receipt": verified["receiptDigest"]})
            with runtime.store.connect(write=True) as db:
                db.execute("UPDATE missions SET state='complete' WHERE id=?", (identity,))
                runtime.store.event(db, identity, "mission-complete", {"jobs": len(result["jobs"])})
        except (BastionError, OSError, subprocess.TimeoutExpired) as exc:
            with runtime.store.connect(write=True) as db:
                db.execute("UPDATE missions SET state='blocked',error=? WHERE id=?", (str(exc), identity))
                runtime.store.event(db, identity, "mission-blocked", {"reason": str(exc)})
            raise BastionError(str(exc)) from exc
    return inspect(runtime, identity)


def due(runtime, limit=10):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise BastionError("invalid due mission limit")
    with runtime.store.connect() as db:
        candidates = db.execute("SELECT id,digest,plan FROM missions WHERE state IN ('approved','running') ORDER BY id").fetchall()
    candidates = sorted(candidates, key=lambda r: (json.loads(r["plan"])["deadline"], r["id"]))
    return {"missions": [{"mission": r["id"], "digest": r["digest"]} for r in candidates
                         if json.loads(r["plan"])["notBefore"] <= time.time()][:limit],
            "dispatch": "local only; invoke mission work explicitly or through an operator-installed scheduler"}


def replace_check(runtime, identity, claimed, position, replacement, replacement_digest, reason):
    """Create a new unapproved mission; never reset or erase an uncertain code attempt."""
    if type(position) is not int or not isinstance(reason,str) or not reason.strip() or len(reason)>2000:
        raise BastionError('replacement requires a position and explicit operator reason')
    with runtime.store.execution_lock('mission-'+identity):
        old=bound(runtime,identity,claimed)
        if old['approved']!=claimed or old['state'] not in ('running','blocked') or not 0<=position<len(old['jobs']):
            raise BastionError('mission is not ready for check replacement')
        target=old['jobs'][position]
        if target['kind']!='check' or target['state']=='done' or replacement==target['run']:
            raise BastionError('only an unresolved check can be replaced with a fresh check')
        with runtime.store.execution_lock('check-'+target['run']):
            from . import checks
            state=checks.inspect(runtime,target['run'])['state']
            if state not in ('running','failed'):
                raise BastionError('check has no failed or uncertain outcome to replace')
            fresh=checks.bound(runtime,replacement,replacement_digest,live=True)
            if fresh['state']!='draft': raise BastionError('replacement check must be a fresh unapproved draft')
            spec={k:old['plan'][k] for k in ('goal','notBefore','deadline')}
            spec['budgets']=dict(old['plan']['budgets'])
            remaining=int(spec['budgets']['maxWallSeconds']-max(0,time.time()-(old['started'] or time.time())))
            if remaining<1: raise BastionError('mission wall-time budget exhausted; replacement cannot reset it')
            spec['budgets']['maxWallSeconds']=remaining
            spec['jobs']=[dict(kind=r['kind'],run=r['run'],digest=r['digest']) for r in old['jobs']]
            spec['jobs'][position]={'kind':'check','run':replacement,'digest':replacement_digest}
            provenance={'mission':identity,'digest':claimed,'position':position,'previousCheck':target['run'],
                        'operatorReason':reason,'externalReconciliationProven':False,
                        'wallDeadline':min((old['started'] or time.time())+old['plan']['budgets']['maxWallSeconds'],old['plan'].get('supersedes',{}).get('wallDeadline',float('inf')))}
            result=plan(runtime,spec,supersedes=provenance)
            with runtime.store.connect(write=True) as db:
                db.execute("UPDATE missions SET state='blocked' WHERE id=?",(identity,))
                runtime.store.event(db,identity,'mission-check-replacement-planned',{'newMission':result['mission'],'position':position})
            return result


def tick(runtime, limit=10):
    results = []
    for ref in due(runtime, limit)["missions"]:
        try:
            result = work(runtime, ref["mission"], ref["digest"])
            results.append({"mission": ref["mission"], "state": result["state"]})
        except BastionError as exc:
            results.append({"mission": ref["mission"], "state": "blocked-or-busy", "reason": str(exc)})
    return {"processed": len(results), "results": results, "scope": "approved typed jobs; no implicit retry of code"}
