"""Versioned pure-workflow cartridges with bounded qualification and explicit activation."""
import copy
import hashlib
import json
import re

from .core import (BastionError, CAPABILITIES, canonical, digest, execute_pure,
                   resolve, validate_workflow, verify_pure)
from .store import runtime_digest


def bounded(value, limit=65536):
    if len(canonical(value).encode()) > limit:
        raise BastionError("cartridge data exceeds byte budget")


def inputs_for(manifest, inputs):
    if not isinstance(inputs, dict) or set(inputs) != set(manifest["inputs"]):
        raise BastionError("cartridge input fields mismatch")
    bounded(inputs)
    def check_data(value):
        if isinstance(value, dict):
            if "$ref" in value:
                raise BastionError("graph references are not allowed in cartridge input data")
            for child in value.values():
                check_data(child)
        elif isinstance(value, list):
            for child in value:
                check_data(child)
    check_data(inputs)
    for name, kind in manifest["inputs"].items():
        value = inputs[name]
        if kind == "u32-list" and (not isinstance(value, list) or len(value) > 64 or
                any(type(v) is not int or not 0 <= v < 2**32 for v in value)):
            raise BastionError("expected at most 64 u32 integers")


def materialize(manifest, inputs):
    inputs_for(manifest, inputs)

    def replace(value):
        if isinstance(value, dict):
            if "$input" in value:
                if set(value) != {"$input"} or not isinstance(value["$input"], str) or value["$input"] not in inputs:
                    raise BastionError("invalid cartridge input reference")
                return copy.deepcopy(inputs[value["$input"]])
            return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return value

    workflow = copy.deepcopy(manifest["workflow"])
    # Placeholders are supported only inside node parameters.
    for node in workflow["nodes"]:
        node["params"] = replace(node["params"])
    validate_workflow(workflow)
    if len(workflow["nodes"]) > manifest["budgets"]["maxNodes"]:
        raise BastionError("cartridge node budget exceeded")
    used = sorted({n["capability"] for n in workflow["nodes"]})
    if used != manifest["capabilities"] or any(CAPABILITIES[c]["effect"] != "pure" for c in used):
        raise BastionError("cartridges support declared pure capabilities only")
    return workflow


def validate(manifest):
    fields = {"schema", "name", "version", "description", "inputs", "capabilities", "workflow", "fixtures", "assets", "budgets"}
    if not isinstance(manifest, dict) or set(manifest) != fields or manifest["schema"] != "bastion.cartridge.v1":
        raise BastionError("invalid cartridge manifest")
    bounded(manifest, 512 * 1024)
    if not isinstance(manifest["name"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", manifest["name"]):
        raise BastionError("invalid cartridge name")
    if not isinstance(manifest["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest["version"]):
        raise BastionError("cartridge version must be numeric major.minor.patch")
    if not isinstance(manifest["description"], str) or not 1 <= len(manifest["description"]) <= 1024:
        raise BastionError("cartridge description required")
    if not isinstance(manifest["inputs"], dict) or not 1 <= len(manifest["inputs"]) <= 16:
        raise BastionError("cartridge requires 1..16 inputs")
    if any(not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", k) or v not in ("json", "u32-list")
           for k, v in manifest["inputs"].items()):
        raise BastionError("unsupported cartridge input declaration")
    budgets = manifest["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != {"maxNodes", "maxOutputBytes"} or any(type(v) is not int for v in budgets.values()):
        raise BastionError("invalid cartridge budgets")
    if not 1 <= budgets["maxNodes"] <= 32 or not 1 <= budgets["maxOutputBytes"] <= 65536:
        raise BastionError("invalid cartridge budget range")
    caps = manifest["capabilities"]
    if not isinstance(caps, list) or any(not isinstance(c, str) or c not in CAPABILITIES or CAPABILITIES[c]["effect"] != "pure" for c in caps):
        raise BastionError("cartridges support declared pure capabilities only")
    if caps != sorted(set(caps)):
        raise BastionError("capabilities must be sorted and unique")
    assets = manifest["assets"]
    if not isinstance(assets, list) or len(assets) > 32 or any(not isinstance(p, str) for p in assets) or len(set(assets)) != len(assets):
        raise BastionError("invalid cartridge assets")
    fixtures = manifest["fixtures"]
    if not isinstance(fixtures, list) or not 4 <= len(fixtures) <= 64:
        raise BastionError("cartridge requires 4..64 fixtures")
    positives = 0
    seen = set()
    for case in fixtures:
        if not isinstance(case, dict) or set(case) != {"inputs", "expected"} or not isinstance(case["inputs"], dict):
            raise BastionError("invalid cartridge fixture")
        expected = case["expected"]
        if not isinstance(expected, dict) or set(expected) not in ({"outputs"}, {"error"}):
            raise BastionError("fixture requires exact outputs or error")
        if "outputs" in expected and not isinstance(expected["outputs"], dict):
            raise BastionError("fixture outputs must be an object")
        if "error" in expected and (not isinstance(expected["error"], str) or not expected["error"]):
            raise BastionError("fixture error must be nonempty text")
        positives += "outputs" in expected
        key = digest(case["inputs"])
        if key in seen:
            raise BastionError("duplicate cartridge fixture inputs")
        seen.add(key)
    if positives < 2 or len(fixtures) - positives < 2:
        raise BastionError("qualification requires positive and rejection coverage")
    # Check structure independently of fixture expectations.
    if not isinstance(manifest["workflow"], dict) or not isinstance(manifest["workflow"].get("nodes"), list):
        raise BastionError("invalid cartridge workflow")
    materialize(manifest, {k: [] if v == "u32-list" else None for k, v in manifest["inputs"].items()})


def asset_pins(store, manifest):
    return {p: hashlib.sha256(store.project_file(p).read_bytes()).hexdigest() for p in sorted(manifest["assets"])}


def register(runtime, manifest):
    validate(manifest)
    package = {"manifest": manifest, "assets": asset_pins(runtime.store, manifest),
        "workspace": str(runtime.store.workspace)}
    identity = digest(package)
    with runtime.store.connect(write=True) as db:
        existing = db.execute("SELECT id FROM cartridges WHERE name=? AND version=?", (manifest["name"], manifest["version"])).fetchone()
        if existing and existing["id"] != identity:
            raise BastionError("cartridge version is immutable; use a new version")
        db.execute("INSERT OR IGNORE INTO cartridges VALUES(?,?,?,?)", (identity, manifest["name"], manifest["version"], canonical(package)))
    return {"cartridge": identity, "name": manifest["name"], "version": manifest["version"], "state": "registered"}


def load(runtime, identity):
    with runtime.store.connect() as db:
        row = db.execute("SELECT package FROM cartridges WHERE id=?", (identity,)).fetchone()
    if not row:
        raise BastionError("cartridge not found")
    package = json.loads(row["package"])
    if digest(package) != identity or package["workspace"] != str(runtime.store.workspace):
        raise BastionError("cartridge identity mismatch")
    validate(package["manifest"])
    if asset_pins(runtime.store, package["manifest"]) != package["assets"]:
        raise BastionError("cartridge assets changed")
    return package


def execute(manifest, inputs):
    workflow = materialize(manifest, inputs)
    outputs = {}
    for name in validate_workflow(workflow):
        node = next(n for n in workflow["nodes"] if n["id"] == name)
        params = resolve(node["params"], outputs)
        value = execute_pure(node["capability"], params)
        if not verify_pure(node["capability"], params, value):
            raise BastionError("cartridge result verification failed")
        outputs[name] = value
        bounded(outputs, manifest["budgets"]["maxOutputBytes"])
    return outputs


def evaluate(manifest):
    """Execute actual pure built-ins. Fixture oracles are authored data, not learned truth."""
    cases = []
    for index, case in enumerate(manifest["fixtures"]):
        try:
            actual = {"outputs": execute(manifest, case["inputs"])}
        except BastionError as exc:
            actual = {"error": str(exc)}
        cases.append({"index": index, "inputDigest": digest(case["inputs"]), "actual": actual,
            "expected": case["expected"], "passed": canonical(actual) == canonical(case["expected"])})
    return cases


def qualify(runtime, identity):
    package = load(runtime, identity)
    cases = evaluate(package["manifest"])
    report = {"schema": "bastion.cartridge-qualification.v1", "cartridge": identity,
        "runtimeDigest": runtime_digest(), "cases": cases, "passed": all(c["passed"] for c in cases),
        "scope": "local pure built-ins and authored fixtures; no model or external integration"}
    qid = digest(report)
    with runtime.store.connect(write=True) as db:
        db.execute("INSERT OR IGNORE INTO cartridge_qualifications VALUES(?,?,?)", (qid, identity, canonical(report)))
    return {"qualification": qid, "report": report}


def activate(runtime, identity, qid):
    package = load(runtime, identity)
    with runtime.store.connect() as db:
        row = db.execute("SELECT report FROM cartridge_qualifications WHERE id=? AND cartridge=?", (qid, identity)).fetchone()
    if not row or digest(json.loads(row["report"])) != qid:
        raise BastionError("qualification identity mismatch")
    report = json.loads(row["report"])
    if not report["passed"] or report["runtimeDigest"] != runtime_digest() or evaluate(package["manifest"]) != report["cases"]:
        raise BastionError("qualification failed or stale")
    with runtime.store.connect() as db:
        active = db.execute("SELECT cartridge FROM cartridge_active WHERE name=?", (package["manifest"]["name"],)).fetchone()
    comparison = None
    if active and active["cartridge"] != identity:
        comparison = compare(runtime, active["cartridge"], identity)
        if not comparison["baselinePassed"] or not comparison["candidatePassed"]:
            raise BastionError("cartridge upgrade regresses retained baseline fixtures")
    with runtime.store.connect(write=True) as db:
        current = db.execute("SELECT cartridge FROM cartridge_active WHERE name=?", (package["manifest"]["name"],)).fetchone()
        if (current["cartridge"] if current else None) != (active["cartridge"] if active else None):
            raise BastionError("active cartridge changed during review; retry activation")
        db.execute("INSERT OR REPLACE INTO cartridge_active VALUES(?,?,?)", (package["manifest"]["name"], identity, qid))
        runtime.store.event(db, identity, "cartridge-activated", {"qualification": qid, "comparison": comparison})
    return {"cartridge": identity, "qualification": qid, "state": "active", "executionApproved": False}


def compare(runtime, baseline, candidate):
    old = load(runtime, baseline)["manifest"]
    new = load(runtime, candidate)["manifest"]
    if old["name"] != new["name"] or old["inputs"] != new["inputs"]:
        raise BastionError("cartridge interfaces are not comparable")
    trial = dict(new, fixtures=old["fixtures"])
    before, after = evaluate(old), evaluate(trial)
    return {"baseline": baseline, "candidate": candidate, "runtimeDigest": runtime_digest(),
        "fixtureDigest": digest(old["fixtures"]), "baselinePassed": all(c["passed"] for c in before),
        "candidatePassed": all(c["passed"] for c in after),
        "regressions": [c for b, c in zip(before, after) if b["passed"] and not c["passed"]],
        "scope": "paired replay of baseline authored fixtures; no statistical superiority claim"}


def listing(runtime):
    with runtime.store.connect() as db:
        return {"cartridges": [dict(r) for r in db.execute(
            "SELECT c.id,c.name,c.version,a.qualification FROM cartridges c LEFT JOIN cartridge_active a ON a.cartridge=c.id ORDER BY c.name,c.version")],
            "authority": "proposal-only"}


def propose(runtime, name, inputs):
    with runtime.store.connect() as db:
        row = db.execute("SELECT cartridge,qualification FROM cartridge_active WHERE name=?", (name,)).fetchone()
    if not row:
        raise BastionError("cartridge is not active")
    # Recheck source and all fixture oracles at the proposal boundary.
    package = load(runtime, row["cartridge"])
    with runtime.store.connect() as db:
        q = db.execute("SELECT report FROM cartridge_qualifications WHERE id=?", (row["qualification"],)).fetchone()
    if not q or digest(json.loads(q["report"])) != row["qualification"]:
        raise BastionError("qualification identity mismatch")
    report = json.loads(q["report"])
    if report["cartridge"] != row["cartridge"] or not report["passed"] or report["runtimeDigest"] != runtime_digest():
        raise BastionError("cartridge qualification stale")
    if evaluate(package["manifest"]) != report["cases"]:
        raise BastionError("cartridge qualification no longer matches")
    workflow = materialize(package["manifest"], inputs)
    # All admitted handlers are pure: preflight the actual input against its budgets.
    execute(package["manifest"], inputs)
    result = runtime.plan(workflow, cartridge={"id": row["cartridge"], "qualification": row["qualification"],
        "assets": package["assets"], "budgets": package["manifest"]["budgets"]})
    with runtime.store.connect(write=True) as db:
        runtime.store.event(db, result["run"], "cartridge-proposal", {"cartridge": row["cartridge"],
            "qualification": row["qualification"], "inputDigest": digest(inputs), "planDigest": result["digest"]})
    return dict(result, cartridge=row["cartridge"], qualification=row["qualification"])
