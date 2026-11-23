import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from bastion import cache, missions
from bastion.core import BastionError, decide
from bastion.mcp import invoke, listing
from bastion.native import NativeEngine, configure
from bastion.runtime import Runtime
from bastion.store import Store

ENGINE = (Path.home() / '.codex/plugins/cache/rf2-harness-local/local-ai-harness/0.3.0/bin/rf2-harness')


class MissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.runtime = Runtime(self.store)

    def workflow(self, value=6, nodes=1):
        return self.runtime.plan({"schema": "bastion.workflow.v1", "title": "Mission fixture", "nodes": [
            {"id": "n" + str(i), "capability": "data.value", "params": {"value": value}} for i in range(nodes)]})

    def spec(self, plans=None):
        return {"goal": "Verify bounded local work", "runs": [{"run": p["run"], "digest": p["digest"]} for p in (plans or [self.workflow()])],
            "notBefore": 0, "deadline": time.time() + 120,
            "budgets": {"maxJobs": 100, "maxAttempts": 2, "maxWallSeconds": 30,
                        "maxOutputBytes": 65536, "maxStateBytes": 64 * 1024 * 1024}}

    def approved(self, spec=None):
        p = missions.plan(self.runtime, spec or self.spec())
        missions.approve(self.runtime, p["mission"], p["digest"])
        return p

    def test_batch_approval_execution_receipts_and_repeat_use(self):
        p = self.approved(self.spec([self.workflow(1), self.workflow(2)]))
        result = missions.work(self.runtime, p["mission"], p["digest"])
        self.assertEqual(result["state"], "complete")
        self.assertEqual([j["attempts"] for j in result["jobs"]], [1, 1])
        reopened = Runtime(Store(self.temp.name))
        self.assertEqual(missions.work(reopened, p["mission"], p["digest"])["jobs"], result["jobs"])
        self.assertEqual(missions.due(reopened)["missions"], [])

    def test_no_approval_wrong_digest_and_cross_project_refused(self):
        p = missions.plan(self.runtime, self.spec())
        with self.assertRaisesRegex(BastionError, "not approved"):
            missions.work(self.runtime, p["mission"], p["digest"])
        with self.assertRaisesRegex(BastionError, "digest"):
            missions.approve(self.runtime, p["mission"], "0" * 64)
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(BastionError, "not found"):
                missions.inspect(Runtime(Store(other)), p["mission"])

    def test_schedule_is_persistent_and_waits_without_sleeping(self):
        spec = self.spec()
        spec["notBefore"] = time.time() + 60
        p = self.approved(spec)
        self.assertEqual(missions.work(self.runtime, p["mission"], p["digest"])["state"], "waiting")
        self.assertEqual(missions.due(Runtime(Store(self.temp.name)))["missions"], [])

    def test_invalid_budgets_deadlines_and_duplicate_runs(self):
        for mutation in ("bool-budget", "zero-budget", "past", "nan", "duplicate"):
            spec = self.spec()
            if mutation == "bool-budget": spec["budgets"]["maxAttempts"] = True
            if mutation == "zero-budget": spec["budgets"]["maxWallSeconds"] = 0
            if mutation == "past": spec["deadline"] = 1
            if mutation == "nan": spec["deadline"] = float("nan")
            if mutation == "duplicate": spec["runs"].append(spec["runs"][0])
            with self.subTest(mutation=mutation), self.assertRaises(BastionError):
                missions.plan(self.runtime, spec)

    def test_output_budget_blocks_and_keeps_receipt_evidence(self):
        spec = self.spec([self.workflow("x" * 2000)])
        spec["budgets"]["maxOutputBytes"] = 1024
        p = self.approved(spec)
        with self.assertRaisesRegex(BastionError, "output budget"):
            missions.work(self.runtime, p["mission"], p["digest"])
        result = missions.inspect(self.runtime, p["mission"])
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["jobs"][0]["attempts"], 1)

    def test_deadline_and_attempt_budgets_never_reset_on_resume(self):
        p = self.approved()
        with self.store.connect(write=True) as db:
            db.execute("UPDATE missions SET started=? WHERE id=?", (time.time() - 40, p["mission"]))
        with self.assertRaisesRegex(BastionError, "wall-time"):
            missions.work(self.runtime, p["mission"], p["digest"])
        p = self.approved()
        with self.store.connect(write=True) as db:
            db.execute("UPDATE mission_jobs SET attempts=2 WHERE mission=?", (p["mission"],))
        with self.assertRaisesRegex(BastionError, "attempt budget"):
            missions.work(self.runtime, p["mission"], p["digest"])

    def test_active_worker_exclusion_and_job_tampering(self):
        p = self.approved()
        with self.store.execution_lock("mission-" + p["mission"]):
            with self.assertRaisesRegex(BastionError, "active worker"):
                missions.work(self.runtime, p["mission"], p["digest"])
        other = self.workflow()
        with self.store.connect(write=True) as db:
            db.execute("UPDATE mission_jobs SET run=?,digest=? WHERE mission=?", (other["run"], other["digest"], p["mission"]))
        with self.assertRaisesRegex(BastionError, "job identity"):
            missions.inspect(self.runtime, p["mission"])

    def test_completed_receipt_tampering_and_state_budget(self):
        p = self.approved()
        missions.work(self.runtime, p["mission"], p["digest"])
        with self.store.connect(write=True) as db:
            db.execute("UPDATE mission_jobs SET receipt='wrong' WHERE mission=?", (p["mission"],))
        with self.assertRaisesRegex(BastionError, "receipt mismatch"):
            missions.work(self.runtime, p["mission"], p["digest"])
        p = self.approved()
        with patch("bastion.missions.storage", return_value=2**30):
            with self.assertRaisesRegex(BastionError, "state budget"):
                missions.work(self.runtime, p["mission"], p["digest"])

    def test_mcp_exposes_no_approval_worker_or_native_configuration(self):
        p = invoke(self.runtime, "bastion_mission_plan", {"spec": self.spec()})
        self.assertEqual(p["state"], "draft")
        names = {t["name"] for t in listing()["tools"]}
        self.assertIn("bastion_storage", names)
        for forbidden in ("bastion_mission_approve", "bastion_mission_work", "bastion_native_configure"):
            self.assertNotIn(forbidden, names)

    def test_tick_runs_only_due_approved_missions(self):
        pending = missions.plan(self.runtime, self.spec())
        approved = self.approved()
        result = missions.tick(self.runtime, limit=1)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["results"][0]["mission"], approved["mission"])
        self.assertEqual(missions.inspect(self.runtime, pending["mission"])["state"], "draft")


class CacheTests(unittest.TestCase):
    setUp = MissionTests.setUp
    def test_dedup_quota_and_exact_expired_prune_preserve_unique_records(self):
        source = Path(self.temp.name) / "rebuildable.txt"
        source.write_text("rebuildable")
        obj = cache.stash(self.store, "rebuildable.txt", ttl=1, quota=20)
        self.assertEqual(cache.stash(self.store, "rebuildable.txt", ttl=1, quota=20)["object"], obj["object"])
        unique = self.store.add_experience("note", "unique knowledge", {}, "unverified")
        with self.store.connect(write=True) as db:
            db.execute("UPDATE cache_entries SET expires=0")
        plan = cache.prune_plan(self.store)
        self.assertEqual(cache.prune(self.store, plan["digest"])["removed"], 1)
        self.assertTrue(source.exists())
        self.assertEqual(self.store.search("unique", "experiences")[0]["id"], unique)

    def test_refresh_stale_plan_tampering_symlink_and_quota(self):
        source = Path(self.temp.name) / "file.txt"
        source.write_text("abc")
        obj = cache.stash(self.store, "file.txt", ttl=1)
        with self.store.connect(write=True) as db:
            db.execute("UPDATE cache_entries SET expires=0")
        plan = cache.prune_plan(self.store)
        cache.stash(self.store, "file.txt", ttl=60)
        with self.assertRaisesRegex(BastionError, "plan changed"):
            cache.prune(self.store, plan["digest"])
        with self.assertRaisesRegex(BastionError, "quota"):
            cache.stash(self.store, "file.txt", quota=1)
        path = self.store.root / "cache" / obj["object"]
        path.write_text("tampered")
        with self.store.connect(write=True) as db:
            db.execute("UPDATE cache_entries SET expires=0")
        with self.assertRaisesRegex(BastionError, "identity"):
            cache.prune_plan(self.store)
        path.unlink()
        path.symlink_to(source)
        with self.assertRaisesRegex(BastionError, "identity"):
            cache.prune_plan(self.store)


@unittest.skipUnless(ENGINE.is_file(), "installed native RF2 engine unavailable")
class NativeTests(unittest.TestCase):
    setUp = MissionTests.setUp
    workflow = MissionTests.workflow
    spec = MissionTests.spec
    approved = MissionTests.approved
    def native(self):
        sha = hashlib.sha256(ENGINE.read_bytes()).hexdigest()
        configure(self.store, str(ENGINE), sha)
        self.runtime = Runtime(self.store)
        return self.runtime.native

    def test_real_native_workflow_and_allowed_transition_agreement(self):
        engine = self.native()
        self.assertEqual(engine.sum([17, 23, 42]), 82)
        with self.assertRaisesRegex(BastionError, "overflow"):
            engine.sum([4294967295, 1])
        checked = 0
        for state in ("draft", "approved", "running", "verified", "failed", "uncertain"):
            for action in ("approve", "start", "finish", "fail", "interrupt", "retry"):
                for approval in (False, True):
                    allowed, following, _ = decide(state, action, approval, True, True, True, True)
                    if allowed:
                        native = engine.gate(state, action, approval, self.store.workspace)
                        self.assertTrue(native["allowed"], (state, action, native))
                        self.assertEqual(native["next"], {"draft":0,"approved":1,"running":2,"verified":3,"failed":4,"uncertain":5}[following])
                        checked += 1
        self.assertEqual(checked, 8)
        value = self.runtime.plan({"schema":"bastion.workflow.v1","title":"Native sum","nodes":[
            {"id":"sum","capability":"math.sum_u32","params":{"values":[17,23,42]}}]})
        self.runtime.approve(value["run"], value["digest"])
        self.assertEqual(self.runtime.run(value["run"], value["digest"])["receipt"]["outputs"]["sum"], 82)

    def test_native_hash_and_setting_changes_refuse_stale_runtime(self):
        engine = self.native()
        with self.assertRaisesRegex(BastionError, "hash mismatch"):
            NativeEngine(str(ENGINE), "0" * 64)
        plan = self.workflow()
        with self.store.connect(write=True) as db:
            db.execute("DELETE FROM settings WHERE key='native-engine'")
        with self.assertRaisesRegex(BastionError, "configuration changed"):
            self.runtime.approve(plan["run"], plan["digest"])

    def test_real_mission_process_death_watchdog_and_recovery(self):
        self.native()
        graph = {"schema":"bastion.workflow.v1","title":"Native recovery fixture","nodes":[
            {"id":"n"+str(i),"capability":"math.sum_u32","params":{"values":[i,1]}} for i in range(40)]}
        run = self.runtime.plan(graph)
        p = self.approved(self.spec([run]))
        child = subprocess.Popen([sys.executable,"-m","bastion","--workspace",self.temp.name,"mission","work",p["mission"],p["digest"]],
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            end = time.monotonic()+10
            while time.monotonic()<end:
                if self.runtime.inspect(run["run"])["state"] == "running": break
                if child.poll() is not None: self.fail("mission ended before process-death injection")
                time.sleep(0.01)
            else: self.fail("mission never started")
            child.kill()
            child.wait(timeout=5)
            # Child watchdog must release the workflow lock after losing its parent.
            end = time.monotonic()+5
            while True:
                try:
                    with self.store.execution_lock(run["run"]): pass
                    break
                except BastionError:
                    if time.monotonic()>=end: self.fail("orphan worker retained lock")
                    time.sleep(0.05)
            result = missions.work(Runtime(Store(self.temp.name)),p["mission"],p["digest"])
            self.assertEqual(result["state"],"complete")
            self.assertEqual(result["jobs"][0]["attempts"],2)
        finally:
            if child.poll() is None: child.kill(); child.wait()
