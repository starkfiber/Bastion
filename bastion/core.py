"""Bounded execution kernel. Models propose work; this module owns authority."""
import hashlib
import json
import re


class BastionError(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


TRANSITIONS = {
    ("draft", "approve"): "approved",
    ("approved", "start"): "running",
    ("running", "finish"): "verified",
    ("running", "fail"): "failed",
    ("running", "interrupt"): "uncertain",
    ("uncertain", "retry"): "approved",
    ("failed", "retry"): "approved",
}


def decide(state, action, approved, binding, budget, supported, explicit=False):
    """A decision is not a sandbox or evidence that an action happened."""
    if not binding:
        return False, state, "identity-mismatch"
    if not supported:
        return False, state, "unsupported-capability"
    if (state, action) not in TRANSITIONS:
        return False, state, "invalid-transition"
    if action in ("approve", "retry") and not explicit:
        return False, state, "operator-required"
    if action != "interrupt" and not approved:
        return False, state, "approval-required"
    if action == "start" and not budget:
        return False, state, "budget-exhausted"
    return True, TRANSITIONS[(state, action)], "allowed"


CAPABILITIES = {
    "data.value": {"version": 1, "effect": "pure", "required": ["value"]},
    "math.sum_u32": {"version": 1, "effect": "pure", "required": ["values"]},
    "data.sha256": {"version": 1, "effect": "pure", "required": ["value"]},
    "data.assert_equal": {"version": 1, "effect": "pure", "required": ["actual", "expected"]},
    "data.select_fields": {"version": 1, "effect": "pure", "required": ["value", "fields"]},
    "knowledge.ingest": {"version": 1, "effect": "project-read-state-write", "required": ["path"]},
    "knowledge.search": {"version": 1, "effect": "state-read", "required": ["query"]},
}
ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise BastionError("invalid identifier")
    return value


def refs(value):
    found = set()
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) != {"$ref"}:
                raise BastionError("a reference must contain only $ref")
            found.add(identifier(value["$ref"]))
        else:
            for child in value.values():
                found.update(refs(child))
    elif isinstance(value, list):
        for child in value:
            found.update(refs(child))
    return found


def resolve(value, outputs):
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            return outputs[value["$ref"]]
        return {k: resolve(v, outputs) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, outputs) for v in value]
    return value


def validate_workflow(workflow):
    if not isinstance(workflow, dict) or set(workflow) - {"schema", "title", "nodes", "planner", "skills"}:
        raise BastionError("invalid workflow fields")
    if workflow.get("schema") != "bastion.workflow.v1":
        raise BastionError("unsupported workflow schema")
    if not isinstance(workflow.get("title"), str) or not 1 <= len(workflow["title"]) <= 200:
        raise BastionError("a short title is required")
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 256:
        raise BastionError("workflow requires 1..256 nodes")
    if len(canonical(workflow).encode()) > 1024 * 1024:
        raise BastionError("workflow exceeds 1 MiB")
    if not isinstance(workflow.get("skills", []), list) or any(not isinstance(x, str) for x in workflow.get("skills", [])):
        raise BastionError("skills must be registered names")
    graph = {}
    for node in nodes:
        if not isinstance(node, dict) or set(node) - {"id", "capability", "params", "after"}:
            raise BastionError("invalid node fields")
        name = identifier(node.get("id"))
        if name in graph:
            raise BastionError("duplicate node")
        capability = node.get("capability")
        if capability not in CAPABILITIES:
            raise BastionError("unsupported capability")
        params = node.get("params")
        if not isinstance(params, dict) or set(params) != set(CAPABILITIES[capability]["required"]):
            raise BastionError("capability parameters do not match")
        after = node.get("after", [])
        if not isinstance(after, list) or any(not isinstance(x, str) for x in after):
            raise BastionError("after must be an identifier list")
        graph[name] = refs(params) | set(after)
    if any(not dependencies <= set(graph) for dependencies in graph.values()):
        raise BastionError("missing dependency")
    order = []
    remaining = dict(graph)
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if deps <= set(order))
        if not ready:
            raise BastionError("cyclic workflow")
        order.extend(ready)
        for name in ready:
            del remaining[name]
    return order


def execute_pure(capability, params):
    if capability == "data.select_fields":
        value, fields = params["value"], params["fields"]
        if not isinstance(value, dict) or not isinstance(fields, list) or not 1 <= len(fields) <= 32:
            raise BastionError("expected object and 1..32 field names")
        if any(not isinstance(k, str) or not 1 <= len(k) <= 64 for k in fields) or len(set(fields)) != len(fields):
            raise BastionError("expected unique bounded field names")
        if any(k not in value for k in fields):
            raise BastionError("required field missing")
        return {k: value[k] for k in fields}
    if capability == "data.value":
        return params["value"]
    if capability == "data.sha256":
        return digest(params["value"])
    if capability == "data.assert_equal":
        if canonical(params["actual"]) != canonical(params["expected"]):
            raise BastionError("assertion failed")
        return {"passed": True}
    if capability == "math.sum_u32":
        values = params["values"]
        if not isinstance(values, list) or len(values) > 64:
            raise BastionError("expected at most 64 u32 values")
        total = 0
        for value in values:
            if type(value) is not int or not 0 <= value <= 4294967295:
                raise BastionError("expected u32 integer")
            total += value
            if total > 4294967295:
                raise BastionError("u32 overflow")
        return total
    raise BastionError("not a pure capability")


def verify_pure(capability, params, result):
    """The sum oracle uses an independent aggregate; other checks state their scope."""
    if capability == "data.select_fields":
        value, fields = params.get("value"), params.get("fields")
        if (not isinstance(value, dict) or not isinstance(fields, list) or not 1 <= len(fields) <= 32 or
                any(not isinstance(k, str) or not 1 <= len(k) <= 64 for k in fields) or
                len(set(fields)) != len(fields) or any(k not in value for k in fields) or not isinstance(result, dict)):
            return False
        return (set(result) == set(fields) and all(canonical(result[k]) == canonical(value[k]) for k in fields))
    if capability == "math.sum_u32":
        values = params.get("values")
        return (isinstance(values, list) and len(values) <= 64
                and all(type(v) is int and 0 <= v < 2**32 for v in values)
                and sum(values) < 2**32 and type(result) is int and result == sum(values))
    if capability == "data.value":
        return canonical(result) == canonical(params["value"])
    if capability == "data.sha256":
        return result == digest(params["value"])
    if capability == "data.assert_equal":
        return canonical(params["actual"]) == canonical(params["expected"]) and result == {"passed": True}
    return False
