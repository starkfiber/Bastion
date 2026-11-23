"""Provider-shaped proposals, without provider credentials or network calls."""
import copy
import json
from .core import BastionError, validate_workflow


def proposal(payload, provider="external", model="unspecified"):
    if not isinstance(payload, dict):
        raise BastionError("model proposal must be an object")
    if payload.get("schema") == "bastion.workflow.v1":
        workflow = copy.deepcopy(payload)
    elif payload.get("name") == "bastion_plan" and isinstance(payload.get("input"), dict):
        workflow = copy.deepcopy(payload["input"]["workflow"])
    elif isinstance(payload.get("function"), dict) and payload["function"].get("name") == "bastion_plan":
        args = payload["function"].get("arguments")
        if isinstance(args, str):
            args = json.loads(args)
        if not isinstance(args, dict) or set(args) != {"workflow"}:
            raise BastionError("invalid proposal arguments")
        workflow = copy.deepcopy(args["workflow"])
    else:
        raise BastionError("expected workflow or bastion_plan tool proposal")
    workflow["planner"] = {"provider": str(provider)[:100], "model": str(model)[:100], "authority": "proposal-only"}
    validate_workflow(workflow)
    return workflow
