import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bastion import cartridges as c
from bastion.core import BastionError, execute_pure, verify_pure
from bastion.mcp import invoke, listing
from bastion.runtime import Runtime
from bastion.store import Store


def manifest():
    return {"schema": "bastion.cartridge.v1", "name": "checked-sum", "version": "1.0.0",
        "description": "Sum bounded unsigned integers with exact fixture oracles",
        "inputs": {"values": "u32-list"}, "capabilities": ["math.sum_u32"],
        "workflow": {"schema": "bastion.workflow.v1", "title": "Checked sum", "nodes": [
            {"id": "sum", "capability": "math.sum_u32", "params": {"values": {"$input": "values"}}}]},
        "fixtures": [
            {"inputs": {"values": []}, "expected": {"outputs": {"sum": 0}}},
            {"inputs": {"values": [2, 3]}, "expected": {"outputs": {"sum": 5}}},
            {"inputs": {"values": [True]}, "expected": {"error": "expected at most 64 u32 integers"}},
            {"inputs": {"values": [-1]}, "expected": {"error": "expected at most 64 u32 integers"}},
            {"inputs": {"values": [4294967295, 1]}, "expected": {"error": "u32 overflow"}}],
        "assets": [], "budgets": {"maxNodes": 1, "maxOutputBytes": 1024}}


class CartridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.runtime = Runtime(self.store)

    def active(self, value=None):
        identity = c.register(self.runtime, value or manifest())["cartridge"]
        qualified = c.qualify(self.runtime, identity)
        c.activate(self.runtime, identity, qualified["qualification"])
        return identity, qualified

    def test_lifecycle_preserves_execution_approval_and_pins_provenance(self):
        identity, q = self.active()
        plan = invoke(self.runtime, "bastion_cartridge_propose", {"name": "checked-sum", "inputs": {"values": [7, 8]}})
        self.assertEqual(plan["state"], "draft")
        self.assertEqual(plan["plan"]["cartridge"]["id"], identity)
        with self.assertRaises(BastionError):
            self.runtime.run(plan["run"], plan["digest"])
        self.runtime.approve(plan["run"], plan["digest"])
        self.assertEqual(self.runtime.run(plan["run"], plan["digest"])["receipt"]["outputs"], {"sum": 15})
        self.assertEqual(Runtime(Store(self.temp.name)).verify(plan["run"])["state"], "verified")
        names = {t["name"] for t in listing()["tools"]}
        self.assertIn("bastion_cartridge_propose", names)
        self.assertNotIn("bastion_cartridge_activate", names)

    def test_asset_change_blocks_registration_reuse_proposal_and_approved_execution(self):
        asset = Path(self.temp.name) / "contract.txt"
        asset.write_text("original")
        value = manifest()
        value["assets"] = ["contract.txt"]
        identity, _ = self.active(value)
        plan = c.propose(self.runtime, "checked-sum", {"values": [1]})
        self.runtime.approve(plan["run"], plan["digest"])
        asset.write_text("changed")
        with self.assertRaisesRegex(BastionError, "assets changed"):
            c.propose(self.runtime, "checked-sum", {"values": [1]})
        with self.assertRaisesRegex(BastionError, "asset identity changed"):
            self.runtime.run(plan["run"], plan["digest"])
        with self.assertRaisesRegex(BastionError, "immutable"):
            c.register(self.runtime, value)

    def test_qualification_uses_real_outcomes_and_refuses_bad_oracles(self):
        value = manifest()
        value["fixtures"][1]["expected"]["outputs"]["sum"] = 999
        identity = c.register(self.runtime, value)["cartridge"]
        q = c.qualify(self.runtime, identity)
        self.assertFalse(q["report"]["passed"])
        self.assertEqual(q["report"]["cases"][1]["actual"], {"outputs": {"sum": 5}})
        with self.assertRaisesRegex(BastionError, "failed or stale"):
            c.activate(self.runtime, identity, q["qualification"])

    def test_runtime_and_qualification_tampering_refused(self):
        identity, q = self.active()
        with patch("bastion.cartridges.runtime_digest", return_value="changed"):
            with self.assertRaisesRegex(BastionError, "stale"):
                c.propose(self.runtime, "checked-sum", {"values": [1]})
        with self.store.connect(write=True) as db:
            report = copy.deepcopy(q["report"])
            report["scope"] = "tampered"
            db.execute("UPDATE cartridge_qualifications SET report=?", (json.dumps(report),))
        with self.assertRaisesRegex(BastionError, "identity mismatch"):
            c.activate(self.runtime, identity, q["qualification"])

    def test_rejects_unknown_effects_duplicate_fixtures_and_disabled_budgets(self):
        for mutation in ("effects", "duplicate", "positive-only", "zero-budget", "bool-budget", "unknown-input"):
            value = manifest()
            if mutation == "effects": value["capabilities"] = ["knowledge.ingest"]
            if mutation == "duplicate": value["fixtures"].append(value["fixtures"][0])
            if mutation == "positive-only": value["fixtures"] = value["fixtures"][:2]
            if mutation == "zero-budget": value["budgets"]["maxNodes"] = 0
            if mutation == "bool-budget": value["budgets"]["maxNodes"] = True
            if mutation == "unknown-input": value["workflow"]["nodes"][0]["params"]["values"] = {"$input": "missing"}
            with self.subTest(mutation=mutation), self.assertRaises(BastionError):
                c.register(self.runtime, value)

    def test_version_immutability_and_paired_upgrade_regression_gate(self):
        baseline, _ = self.active()
        changed = manifest()
        changed["description"] = "Different content, same version"
        with self.assertRaisesRegex(BastionError, "immutable"):
            c.register(self.runtime, changed)
        changed["version"] = "2.0.0"
        changed["capabilities"] = ["data.value"]
        changed["workflow"]["nodes"][0] = {"id": "sum", "capability": "data.value", "params": {"value": 0}}
        changed["fixtures"][1]["expected"] = {"outputs": {"sum": 0}}
        changed["fixtures"][4]["expected"] = {"outputs": {"sum": 0}}
        candidate = c.register(self.runtime, changed)["cartridge"]
        qualified = c.qualify(self.runtime, candidate)
        self.assertTrue(qualified["report"]["passed"])
        compared = c.compare(self.runtime, baseline, candidate)
        self.assertTrue(compared["baselinePassed"])
        self.assertFalse(compared["candidatePassed"])
        self.assertEqual(len(compared["regressions"]), 2)
        with self.assertRaisesRegex(BastionError, "regresses"):
            c.activate(self.runtime, candidate, qualified["qualification"])
        self.assertEqual(c.propose(self.runtime, "checked-sum", {"values": [2, 3]})["cartridge"], baseline)

    def test_compatible_upgrade_replays_retained_cases(self):
        baseline, _ = self.active()
        value = manifest()
        value["version"] = "1.1.0"
        value["fixtures"].append({"inputs": {"values": [4294967295]}, "expected": {"outputs": {"sum": 4294967295}}})
        candidate, _ = self.active(value)
        self.assertTrue(c.compare(self.runtime, baseline, candidate)["candidatePassed"])
        self.assertEqual(c.propose(self.runtime, "checked-sum", {"values": [1]})["cartridge"], candidate)

    def test_input_and_output_budgets_fail_before_a_plan_is_created(self):
        self.active()
        for inputs in ({"values": [False]}, {"values": [-1]}, {"values": list(range(65))}, {"extra": []}, {"values": [4294967295, 1]}):
            with self.assertRaises(BastionError):
                c.propose(self.runtime, "checked-sum", inputs)
        value = manifest()
        value["version"] = "2.0.0"
        value["inputs"] = {"values": "json"}
        value["capabilities"] = ["data.value"]
        value["workflow"]["nodes"][0] = {"id": "sum", "capability": "data.value", "params": {"value": {"$input": "values"}}}
        value["fixtures"] = [
            {"inputs": {"values": 0}, "expected": {"outputs": {"sum": 0}}},
            {"inputs": {"values": 1}, "expected": {"outputs": {"sum": 1}}},
            {"inputs": {}, "expected": {"error": "cartridge input fields mismatch"}},
            {"inputs": {"extra": None}, "expected": {"error": "cartridge input fields mismatch"}}]
        value["name"] = "bounded-echo"
        value["budgets"]["maxOutputBytes"] = 32
        self.active(value)
        with self.assertRaisesRegex(BastionError, "byte budget"):
            c.propose(self.runtime, "bounded-echo", {"values": "x" * 100})
        with self.assertRaisesRegex(BastionError, "graph references"):
            c.propose(self.runtime, "bounded-echo", {"values": {"nested": {"$ref": "sum"}}})
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)

    def test_sum_algebraic_properties_and_fault_injection(self):
        value = manifest()
        rng = random.Random(20261123)
        for _ in range(100):
            values = [rng.randrange(10000) for _ in range(rng.randrange(30))]
            actual = c.execute(value, {"values": values})["sum"]
            self.assertEqual(actual, c.execute(value, {"values": list(reversed(values))})["sum"])
            self.assertEqual(actual, c.execute(value, {"values": values + [0]})["sum"])
        with patch("bastion.cartridges.execute_pure", return_value=123):
            self.assertFalse(all(case["passed"] for case in c.evaluate(value)))

    def test_record_projection_has_exact_fields_and_rejects_ambiguous_inputs(self):
        params = {"value": {"name": "Example", "status": "ready", "extra": "omit"}, "fields": ["status", "name"]}
        result = execute_pure("data.select_fields", params)
        self.assertEqual(result, {"name": "Example", "status": "ready"})
        self.assertTrue(verify_pure("data.select_fields", params, result))
        self.assertFalse(verify_pure("data.select_fields", params, dict(result, extra="leaked")))
        for fields in ([], ["name", "name"], [True], [["name"]], ["missing"], ["x" * 65]):
            with self.subTest(fields=fields), self.assertRaises(BastionError):
                execute_pure("data.select_fields", {"value": params["value"], "fields": fields})
        # Idempotence and preservation under input key reordering.
        self.assertEqual(execute_pure("data.select_fields", {"value": result, "fields": params["fields"]}), result)
        self.assertEqual(execute_pure("data.select_fields", {"value": dict(reversed(list(params["value"].items()))), "fields": params["fields"]}), result)

    def test_cli_lifecycle_in_fresh_processes(self):
        root = Path(self.temp.name)
        (root/"cartridge.json").write_text(json.dumps(manifest()))
        (root/"inputs.json").write_text(json.dumps({"values": [9, 1]}))
        def cli(*args):
            child = subprocess.run([sys.executable, "-m", "bastion", "--workspace", str(root), *args],
                capture_output=True, text=True, timeout=20)
            self.assertEqual(child.returncode, 0, child.stderr)
            return json.loads(child.stdout)
        identity = cli("cartridge", "register", "cartridge.json")["cartridge"]
        q = cli("cartridge", "qualify", identity)
        cli("cartridge", "activate", identity, q["qualification"])
        plan = cli("cartridge", "propose", "checked-sum", "inputs.json")
        cli("approve", plan["run"], plan["digest"])
        cli("run", plan["run"], plan["digest"])
        self.assertEqual(cli("verify", plan["run"])["receipt"]["outputs"]["sum"], 10)
