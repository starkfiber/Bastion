"""Source-pinned, operator-approved unittest checks for reviewed local code."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
import uuid

from .core import BastionError, canonical, digest, identifier
from .missions import storage
from .store import runtime_digest


def interpreter():
    path = Path(sys.executable).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def source_pins(store, manifest):
    pins = {name: hashlib.sha256(store.project_file(name).read_bytes()).hexdigest() for name in manifest["files"]}
    if sum(store.project_file(name).stat().st_size for name in pins) > 4 * 1024 * 1024:
        raise BastionError("check source exceeds 4 MiB")
    return pins


def plan(runtime, manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"name", "files", "testModules", "minTests", "budgets", "trust"}:
        raise BastionError("invalid check manifest")
    if manifest["trust"] != "reviewed-local-code; not-os-sandboxed":
        raise BastionError("check requires explicit reviewed-code trust boundary")
    if not isinstance(manifest["name"], str) or not 1 <= len(manifest["name"]) <= 200:
        raise BastionError("check name required")
    files = manifest["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= 100 or any(not isinstance(f, str) for f in files) or len(set(files)) != len(files):
        raise BastionError("check requires 1..100 unique files")
    if any(Path(f).is_absolute() or ".." in Path(f).parts or f != Path(f).as_posix() or not f or f.startswith(".") for f in files):
        raise BastionError("check files must be normalized visible relative paths")
    modules = manifest["testModules"]
    if not isinstance(modules, list) or not 1 <= len(modules) <= 20 or any(not isinstance(m, str) or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", m) for m in modules):
        raise BastionError("check requires explicit top-level test module names")
    if len(set(modules)) != len(modules) or any(m + ".py" not in files for m in modules):
        raise BastionError("test modules must be unique and included in pinned files")
    if type(manifest["minTests"]) is not int or not 1 <= manifest["minTests"] <= 1000:
        raise BastionError("check requires at least one expected test")
    limits = {"wallSeconds": (1, 120), "cpuSeconds": (1, 60), "outputBytes": (1024, 1048576), "stateBytes": (1048576, 1073741824)}
    budgets = manifest["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != set(limits) or any(type(budgets[k]) is not int or not lo <= budgets[k] <= hi for k,(lo,hi) in limits.items()):
        raise BastionError("invalid check budgets")
    value = {"schema": "bastion.check.v1", "manifest": manifest, "sources": source_pins(runtime.store, manifest),
        "workspace": str(runtime.store.workspace), "runtimeDigest": runtime_digest(), "interpreter": interpreter(),
        "native": runtime.native.identity if runtime.native else None,
        "isolation": "separate worktree and process group; no hostile-code OS sandbox"}
    identity, sha = uuid.uuid4().hex, digest(value)
    with runtime.store.connect(write=True) as db:
        db.execute("INSERT INTO checks(id,plan,digest,state) VALUES(?,?,?,'draft')", (identity, canonical(value), sha))
        runtime.store.event(db, identity, "check-planned", {"digest": sha})
    return {"check": identity, "digest": sha, "state": "draft", "plan": value}


def inspect(runtime, identity):
    identifier(identity)
    with runtime.store.connect() as db:
        row = db.execute("SELECT * FROM checks WHERE id=?", (identity,)).fetchone()
    if not row: raise BastionError("check not found")
    value = json.loads(row["plan"])
    if digest(value) != row["digest"] or value["workspace"] != str(runtime.store.workspace):
        raise BastionError("check identity mismatch")
    return {"check": identity, "digest": row["digest"], "state": row["state"], "approved": row["approved"],
        "plan": value, "receipt": json.loads(row["receipt"]) if row["receipt"] else None,
        "receiptDigest": row["receipt_digest"], "error": row["error"]}


def bound(runtime, identity, claimed, live=False):
    item = inspect(runtime, identity)
    value = item["plan"]
    if item["digest"] != claimed or value["runtimeDigest"] != runtime_digest() or value["interpreter"] != interpreter():
        raise BastionError("check plan/runtime/interpreter identity changed")
    if live and source_pins(runtime.store, value["manifest"]) != value["sources"]:
        raise BastionError("check source changed; create a new plan")
    from .native import configured
    native = configured(runtime.store)
    if value['native'] != (native.identity if native else None) or value['native'] != (runtime.native.identity if runtime.native else None):
        raise BastionError("check native identity changed")
    return item


def native_gate(runtime, state, action):
    if runtime.native:
        result = runtime.native.gate(state, action, True, runtime.store.workspace)
        if not result['allowed'] or result.get('next') != {'approve':1,'start':2,'finish':3,'fail':4}[action]:
            raise BastionError("native check gate refused: " + str(result.get('reason')))


def approve(runtime, identity, claimed):
    with runtime.store.execution_lock("check-" + identity):
        item = bound(runtime, identity, claimed, live=True)
        if item["state"] not in ("draft", "approved"): raise BastionError("check cannot be approved")
        if item['state']=='draft': native_gate(runtime,'draft','approve')
        with runtime.store.connect(write=True) as db:
            db.execute("UPDATE checks SET state='approved',approved=? WHERE id=?", (claimed, identity))
            runtime.store.event(db, identity, "check-approved", {"digest": claimed})
    return {"check": identity, "digest": claimed, "state": "approved"}


def artifact_root(store, identity):
    root = store.root / "checks"
    if root.is_symlink() or (root / identity).is_symlink(): raise BastionError("check artifact symlink refused")
    root.mkdir(mode=0o700, exist_ok=True)
    return root / identity


def run(runtime, identity, claimed):
    with runtime.store.execution_lock("check-" + identity):
        item = bound(runtime, identity, claimed, live=True)
        if item["state"] in ("passed", "failed"): return verify(runtime, identity)
        if item["approved"] != claimed or item["state"] != "approved":
            raise BastionError("check is unapproved or needs reconciliation; never retry code implicitly")
        plan_value, manifest = item["plan"], item["plan"]["manifest"]
        budgets = manifest["budgets"]
        source_bytes=sum(runtime.store.project_file(name).stat().st_size for name in plan_value['sources'])
        if storage(runtime.store) + source_bytes >= budgets["stateBytes"]: raise BastionError("check state budget exhausted")
        native_gate(runtime,'approved','start')
        root = artifact_root(runtime.store, identity)
        if root.exists(): raise BastionError("check artifact directory exists; inspect interrupted evidence")
        root.mkdir(mode=0o700)
        snapshot = root / "snapshot"
        snapshot.mkdir(mode=0o700)
        for name, wanted in plan_value["sources"].items():
            content = runtime.store.project_file(name).read_bytes()
            if hashlib.sha256(content).hexdigest() != wanted: raise BastionError("source changed during snapshot")
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (root / "request.json").write_text(canonical({"manifest": manifest, "planDigest": claimed}))
        with runtime.store.connect(write=True) as db:
            db.execute("UPDATE checks SET state='running' WHERE id=?", (identity,))
            runtime.store.event(db, identity, "check-started", {"digest": claimed})
        command = [sys.executable, "-I", "-B", str(Path(__file__).with_name("check_worker.py")), str(root),
                   str(os.getpid()), str(budgets["wallSeconds"]), str(budgets["cpuSeconds"])]
        process = subprocess.Popen(command, cwd=str(snapshot), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        monitor = selectors.DefaultSelector()
        monitor.register(process.stdout, selectors.EVENT_READ)
        deadline, seen, stop_reason = time.monotonic() + budgets["wallSeconds"], 0, None
        try:
            with (root / "output.log").open("wb") as log:
                while monitor.get_map():
                    if time.monotonic() >= deadline: stop_reason = "wall-time budget exhausted"; break
                    if storage(runtime.store) > budgets["stateBytes"]: stop_reason = "state budget exhausted"; break
                    for key, _ in monitor.select(0.05):
                        data = os.read(key.fd, 4096)
                        if not data: monitor.unregister(key.fileobj); continue
                        allowed = max(0, budgets["outputBytes"] - seen)
                        log.write(data[:allowed]); seen += min(len(data), allowed)
                        if len(data) > allowed: stop_reason = "output budget exhausted"; break
                    if stop_reason: break
            if stop_reason:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=max(0.01, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            stop_reason = "wall-time budget exhausted"
        finally:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
            monitor.close(); process.stdout.close()
        if storage(runtime.store) > budgets['stateBytes']:
            stop_reason = stop_reason or 'state budget exhausted'
        result_path = root / "result.json"
        try:
            result = json.loads(result_path.read_text()) if result_path.is_file() and result_path.stat().st_size <= 65536 else None
        except (ValueError, UnicodeError):
            result = None
        unchanged = all((snapshot/name).is_file() and not (snapshot/name).is_symlink() and hashlib.sha256((snapshot/name).read_bytes()).hexdigest() == wanted for name,wanted in plan_value["sources"].items())
        passed = bool(not stop_reason and process.returncode == 0 and result and result.get("passed") is True and
                      type(result.get("testsRun")) is int and result["testsRun"] >= manifest["minTests"] and unchanged)
        native_gate(runtime,'running','finish' if passed else 'fail')
        receipt = {"schema": "bastion.check-receipt.v1", "check": identity, "planDigest": claimed,
            "passed": passed, "exitCode": process.returncode, "stopReason": stop_reason,
            "tests": result, "sourceUnchanged": unchanged, "outputBytes": seen,
            "outputSha256": hashlib.sha256((root/"output.log").read_bytes()).hexdigest(),
            "resultSha256": hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path.exists() else None,
            "snapshotHashes": {name: hashlib.sha256((snapshot/name).read_bytes()).hexdigest() if (snapshot/name).is_file() and not (snapshot/name).is_symlink() else None for name in plan_value['sources']},
            "scope": "observed tests of operator-reviewed code; OS isolation unqualified; external effects not controlled"}
        with runtime.store.connect(write=True) as db:
            db.execute("UPDATE checks SET state=?,receipt=?,receipt_digest=? WHERE id=?",
                       ("passed" if passed else "failed", canonical(receipt), digest(receipt), identity))
            runtime.store.event(db, identity, "check-finished", {"receiptDigest": digest(receipt), "passed": passed})
        return verify(runtime, identity)


def verify(runtime, identity):
    item = inspect(runtime, identity)
    receipt = item["receipt"]
    if not receipt or digest(receipt) != item["receiptDigest"] or receipt["planDigest"] != item["digest"] or item["approved"] != item["digest"]:
        raise BastionError("check receipt integrity failed")
    if item["state"] != ("passed" if receipt["passed"] else "failed"): raise BastionError("check outcome state mismatch")
    if receipt["check"] != identity: raise BastionError("check receipt identity mismatch")
    with runtime.store.connect() as db:
        events = db.execute("SELECT payload FROM events WHERE run=? AND kind='check-finished'", (identity,)).fetchall()
    if not any(json.loads(e['payload']).get('receiptDigest') == item['receiptDigest'] for e in events):
        raise BastionError("check receipt has no matching completion event")
    root = artifact_root(runtime.store, identity)
    if hashlib.sha256((root/"output.log").read_bytes()).hexdigest() != receipt["outputSha256"]:
        raise BastionError("check log integrity failed")
    result = root/"result.json"
    if (hashlib.sha256(result.read_bytes()).hexdigest() if result.exists() else None) != receipt["resultSha256"]:
        raise BastionError("check result integrity failed")
    for name,wanted in receipt['snapshotHashes'].items():
        path=root/'snapshot'/name
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
        if actual != wanted: raise BastionError("check snapshot integrity failed")
    runtime.store.verify_events()
    return {"check": identity, "state": item["state"], "passed": receipt["passed"], "integrityVerified": True,
            "receipt": receipt, "receiptDigest": item["receiptDigest"]}
