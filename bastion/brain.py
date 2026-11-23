"""Bounded, provider-neutral context assembled from this project's records."""
import hashlib
import json

from .core import BastionError, digest


def context(runtime, query):
    store = runtime.store
    if not isinstance(query, str) or not 1 <= len(query) <= 200 or not query.strip():
        raise BastionError("query must contain 1..200 characters and non-whitespace text")
    nodes, edges, excluded = [], [], []
    project = {"id": "project", "kind": "project", "authority": "none"}
    nodes.append(project)

    def add(kind, identity, data):
        key = kind + ":" + identity
        nodes.append(dict(data, id=key, kind=kind))
        edges.append({"source": "project", "target": key, "relation": "contains"})
        return key

    for row in store.search(query):
        if hashlib.sha256(row["content"].encode()).hexdigest() != row["sha256"]:
            excluded.append({"kind": "knowledge", "id": row["id"], "reason": "content hash mismatch"})
            continue
        add("knowledge", row["id"], {"source": row["source"], "sha256": row["sha256"],
            "excerpt": row["content"][:2000], "truncated": len(row["content"]) > 2000,
            "authority": "data-only", "provenance": row["provenance"][:2000]})

    # Parameterized literal substring matching, identical to the knowledge search.
    needle = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = "%" + needle + "%"
    with store.connect() as db:
        skills = [dict(r) for r in db.execute(
            "SELECT * FROM skills WHERE name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' ORDER BY name LIMIT 20",
            (pattern, pattern))]
        lessons = [dict(r) for r in db.execute(
            "SELECT l.*,e.kind,e.quality,e.evidence FROM lessons l JOIN experiences e ON l.source=e.id "
            "WHERE l.state='reviewed' AND l.text LIKE ? ESCAPE '\\' ORDER BY l.id LIMIT 20", (pattern,))]
    for row in skills:
        try:
            pin = store.skill_pins([row["name"]])[0]
        except (BastionError, OSError) as exc:
            excluded.append({"kind": "skill", "id": row["name"], "reason": str(exc)})
            continue
        add("skill", row["name"], {"metadata": pin, "authority": "guidance-only",
            "instructions": "Load explicitly with bastion_skill; no scripts executed."})

    verified = {}

    def evidence_status(row):
        if row["kind"] != "workflow" or row["quality"] != "verified-local-workflow":
            return "unverified-here"
        try:
            evidence = json.loads(row["evidence"])
            run = evidence["run"]
            if run not in verified:
                verified[run] = runtime.verify(run)["receiptDigest"]
            if verified[run] != evidence["receiptDigest"]:
                return "invalid"
        except (BastionError, OSError, ValueError, KeyError, TypeError):
            return "invalid"
        return "reverified-local-workflow"

    for row in store.search(query, "experiences"):
        status = evidence_status(row)
        add("experience", row["id"], {"summary": row["summary"][:2000],
            "experienceKind": row["kind"], "recordedQuality": row["quality"],
            "evidenceStatus": status, "authority": "data-only"})
    for row in lessons:
        if evidence_status(row) != "reverified-local-workflow":
            excluded.append({"kind": "lesson", "id": row["id"], "reason": "source evidence did not reverify"})
            continue
        key = add("lesson", row["id"], {"text": row["text"], "sourceExperience": row["source"],
            "evidence": json.loads(row["evidence"]), "evidenceStatus": "reverified-local-workflow",
            "authority": "guidance-only", "scope": "this-project"})
        # The source may not match the query, so retain it as an explicit reference node.
        source = "experience:" + row["source"]
        if not any(n["id"] == source for n in nodes):
            add("experience", row["source"], {"evidenceStatus": "reverified-local-workflow",
                "authority": "data-only", "referenceOnly": True})
        edges.append({"source": key, "target": source, "relation": "supported-by"})

    package = {"schema": "bastion.context.v1", "query": query, "nodes": nodes, "edges": edges,
        "excluded": excluded, "retrieval": {"method": "literal-substring", "limitPerCollection": 20,
        "completeProjectMap": False}, "authority": "context-only; no execution permission",
        "scope": "this-project", "modelRequired": False}
    return dict(package, digest=digest(package))
