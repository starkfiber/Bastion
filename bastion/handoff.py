"""Retained planner inputs and provenance; never an execution approval."""
import json

from .adapters import proposal
from .brain import context
from .core import BastionError, canonical, digest
from .mcp import catalog
from .store import runtime_digest


def prepare(runtime, goal, query):
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 8000:
        raise BastionError("goal must contain 1..8000 characters and non-whitespace text")
    package = {"schema": "bastion.handoff.v1", "goal": goal,
        "workspace": str(runtime.store.workspace), "runtimeDigest": runtime_digest(),
        "context": context(runtime, query), "capabilities": catalog(),
        "responseContract": {"schema": "bastion.workflow.v1",
            "formats": ["workflow", "openai-tool-call", "anthropic-tool-use"],
            "nodeFields": ["id", "capability", "params", "after"],
            "references": {"$ref": "node-id"}, "maxNodes": 256},
        "boundary": {"authority": "proposal-only", "contextIsInstructions": False,
            "approvalRequired": True, "networkCalls": False,
            "claim": "Retained planner inputs; no proof a model read or understood them."}}
    if len(canonical(package).encode()) > 512 * 1024:
        raise BastionError("handoff exceeds 512 KiB; narrow the query")
    identity = digest(package)
    with runtime.store.connect(write=True) as db:
        db.execute("INSERT OR IGNORE INTO handoffs VALUES(?,?)", (identity, canonical(package)))
    return {"handoff": identity, "package": package, "state": "prepared"}


def load(runtime, identity):
    if not isinstance(identity, str) or len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
        raise BastionError("invalid handoff digest")
    with runtime.store.connect() as db:
        row = db.execute("SELECT package FROM handoffs WHERE id=?", (identity,)).fetchone()
    if not row:
        raise BastionError("handoff not found in this project")
    package = json.loads(row["package"])
    if digest(package) != identity:
        raise BastionError("handoff digest mismatch")
    return package


def check_current(runtime, package):
    if package["workspace"] != str(runtime.store.workspace):
        raise BastionError("handoff workspace changed; prepare a new handoff")
    if package["runtimeDigest"] != runtime_digest() or package["capabilities"] != catalog():
        raise BastionError("handoff runtime changed; prepare a new handoff")
    current = context(runtime, package["context"]["query"])
    if current != package["context"]:
        raise BastionError("handoff context changed; prepare a new handoff")


def inspect(runtime, identity):
    package = load(runtime, identity)
    reason = None
    try:
        check_current(runtime, package)
    except BastionError as exc:
        reason = str(exc)
    with runtime.store.connect() as db:
        proposals = [dict(row) for row in db.execute(
            "SELECT r.id AS run,r.digest,r.state FROM handoff_proposals h JOIN runs r ON h.run=r.id "
            "WHERE h.handoff=? ORDER BY r.id", (identity,))]
    return {"handoff": identity, "package": package, "current": reason is None,
        "staleReason": reason, "proposals": proposals}


def submit(runtime, identity, payload, provider="external", model="unspecified"):
    package = load(runtime, identity)
    check_current(runtime, package)
    workflow = proposal(payload, provider, model)
    result = runtime.plan(workflow)
    with runtime.store.connect(write=True) as db:
        db.execute("INSERT INTO handoff_proposals VALUES(?,?)", (result["run"], identity))
        runtime.store.event(db, result["run"], "handoff-proposal", {"handoff": identity,
            "planDigest": result["digest"], "planner": workflow["planner"]})
    return dict(result, handoff=identity)
