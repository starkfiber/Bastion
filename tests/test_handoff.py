import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bastion.core import BastionError
from bastion.handoff import inspect, prepare, submit
from bastion.mcp import invoke
from bastion.runtime import Runtime
from bastion.store import Store


def workflow():
    return {"schema": "bastion.workflow.v1", "title": "Sum with independent assertion", "nodes": [
        {"id": "sum", "capability": "math.sum_u32", "params": {"values": [2, 3]}},
        {"id": "check", "capability": "data.assert_equal", "params": {"actual": {"$ref": "sum"}, "expected": 5}}]}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.runtime = Runtime(self.store)
        self.handoff = prepare(self.runtime, "Calculate and verify 2 + 3", "arithmetic")
        self.identity = self.handoff["handoff"]

    def test_two_provider_fixtures_share_context_and_produce_verified_results(self):
        payloads = [("openai", {"function": {"name": "bastion_plan", "arguments": json.dumps({"workflow": workflow()})}}),
                    ("anthropic", {"name": "bastion_plan", "input": {"workflow": workflow()}})]
        results = []
        for provider, payload in payloads:
            result = submit(self.runtime, self.identity, payload, provider, "fixture")
            self.assertEqual(result["state"], "draft")
            self.assertEqual(result["handoff"], self.identity)
            with self.assertRaises(BastionError):
                self.runtime.run(result["run"], result["digest"])
            self.runtime.approve(result["run"], result["digest"])
            receipt = self.runtime.run(result["run"], result["digest"])
            results.append(receipt["receipt"]["outputs"])
        self.assertEqual(results[0], results[1])
        retained = inspect(Runtime(Store(self.temp.name)), self.identity)
        self.assertEqual(retained["package"], self.handoff["package"])
        self.assertEqual(len(retained["proposals"]), 2)
        self.assertTrue(retained["current"])
        self.assertTrue(all(p["state"] == "verified" for p in retained["proposals"]))

    def test_stale_skill_blocks_proposal_and_new_handoff_replaces_context(self):
        folder = Path(self.temp.name) / "arithmetic"
        folder.mkdir()
        skill = folder / "SKILL.md"
        skill.write_text("---\nname: arithmetic\ndescription: arithmetic skill\n---\nGuidance\n")
        self.store.register_skill("arithmetic/SKILL.md")
        before = prepare(self.runtime, "Calculate", "arithmetic")
        skill.write_text("changed")
        self.assertFalse(inspect(self.runtime, before["handoff"])["current"])
        with self.assertRaisesRegex(BastionError, "context changed"):
            submit(self.runtime, before["handoff"], workflow())
        after = prepare(self.runtime, "Calculate", "arithmetic")
        self.assertNotEqual(before["handoff"], after["handoff"])
        self.assertEqual(after["package"]["context"]["excluded"][0]["kind"], "skill")

    def test_runtime_change_tampering_and_project_copy_refused(self):
        with patch("bastion.handoff.runtime_digest", return_value="changed"):
            with self.assertRaisesRegex(BastionError, "runtime changed"):
                submit(self.runtime, self.identity, workflow())
        with tempfile.TemporaryDirectory() as other:
            runtime = Runtime(Store(other))
            with self.assertRaisesRegex(BastionError, "not found"):
                submit(runtime, self.identity, workflow())
            with runtime.store.connect(write=True) as db:
                db.execute("INSERT INTO handoffs VALUES(?,?)", (self.identity, json.dumps(self.handoff["package"])))
            with self.assertRaisesRegex(BastionError, "workspace changed"):
                submit(runtime, self.identity, workflow())
        with self.store.connect(write=True) as db:
            data = copy.deepcopy(self.handoff["package"])
            data["goal"] = "tampered"
            db.execute("UPDATE handoffs SET package=?", (json.dumps(data),))
        with self.assertRaisesRegex(BastionError, "digest mismatch"):
            submit(self.runtime, self.identity, workflow())

    def test_unsupported_effect_never_creates_a_plan(self):
        value = workflow()
        value["nodes"][0]["capability"] = "shell.execute"
        with self.assertRaisesRegex(BastionError, "unsupported capability"):
            submit(self.runtime, self.identity, value)
        self.assertEqual(inspect(self.runtime, self.identity)["proposals"], [])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)

    def test_cli_and_mcp_use_same_retained_contract(self):
        package = invoke(self.runtime, "bastion_handoff", {"goal": "Calculate and verify 2 + 3", "query": "arithmetic"})
        self.assertEqual(package, self.handoff)
        path = Path(self.temp.name) / "proposal.json"
        path.write_text(json.dumps(workflow()))
        child = subprocess.run([sys.executable, "-m", "bastion", "--workspace", self.temp.name,
            "handoff-propose", self.identity, "proposal.json", "--provider", "local-fixture"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout)["state"], "draft")
        inspected = invoke(self.runtime, "bastion_handoff_inspect", {"handoff": self.identity})
        self.assertEqual(len(inspected["proposals"]), 1)
        proposed = invoke(self.runtime, "bastion_handoff_propose", {"handoff": self.identity,
            "payload": workflow(), "provider": "local", "model": "fixture"})
        self.assertEqual(proposed["state"], "draft")

    def test_invalid_goals_and_digests_refused(self):
        for goal in ("", " ", "x" * 8001, None):
            with self.assertRaises(BastionError):
                prepare(self.runtime, goal, "arithmetic")
        for identity in ("", "../escape", "x" * 64, None):
            with self.assertRaises(BastionError):
                inspect(self.runtime, identity)
