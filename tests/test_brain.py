import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bastion.brain import context
from bastion.core import BastionError, digest
from bastion.mcp import invoke, listing
from bastion.runtime import Runtime
from bastion.store import Store


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.runtime = Runtime(self.store)

    def lesson(self):
        plan = self.runtime.plan({"schema": "bastion.workflow.v1", "title": "Memory evidence",
            "nodes": [{"id": "value", "capability": "data.value", "params": {"value": 6}}]})
        self.runtime.approve(plan["run"], plan["digest"])
        self.runtime.run(plan["run"], plan["digest"])
        with self.store.connect() as db:
            source = db.execute("SELECT id FROM experiences").fetchone()[0]
        lesson = self.store.propose_lesson("memory: verify outcomes", source)
        self.store.promote_lesson(lesson)
        return plan, lesson

    def test_reviewed_lesson_links_to_reverified_source_across_reopen(self):
        plan, lesson = self.lesson()
        first = context(self.runtime, "memory")
        second = context(Runtime(Store(self.temp.name)), "memory")
        self.assertEqual(first, second)
        nodes = {n["id"]: n for n in first["nodes"]}
        self.assertEqual(nodes["lesson:" + lesson]["authority"], "guidance-only")
        for edge in first["edges"]:
            self.assertIn(edge["source"], nodes)
            self.assertIn(edge["target"], nodes)
        body = dict(first)
        self.assertEqual(body.pop("digest"), digest(body))
        with self.store.connect(write=True) as db:
            db.execute("UPDATE tasks SET result='7' WHERE run=?", (plan["run"],))
        stale = context(self.runtime, "memory")
        self.assertFalse(any(n["kind"] == "lesson" for n in stale["nodes"]))
        self.assertEqual(stale["excluded"][0]["id"], lesson)

    def test_proposed_and_synthetic_lessons_never_become_guidance(self):
        source = self.store.add_experience("simulation", "memory simulation", {"trials": 2000000}, "synthetic")
        self.store.propose_lesson("memory synthetic claim", source)
        package = context(self.runtime, "memory")
        self.assertFalse(any(n["kind"] == "lesson" for n in package["nodes"]))
        experience = next(n for n in package["nodes"] if n["kind"] == "experience")
        self.assertEqual(experience["evidenceStatus"], "unverified-here")
        self.assertEqual(experience["recordedQuality"], "synthetic")

    def test_knowledge_integrity_excerpt_and_project_separation(self):
        text = "memory " + "a" * 3000
        sha = hashlib.sha256(text.encode()).hexdigest()
        with self.store.connect(write=True) as db:
            db.execute("INSERT INTO knowledge VALUES(?,?,?,?,?)", ("document", "brief.txt", text, sha, "local"))
        node = next(n for n in context(self.runtime, "memory")["nodes"] if n["kind"] == "knowledge")
        self.assertTrue(node["truncated"])
        self.assertEqual(len(node["excerpt"]), 2000)
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(len(context(Runtime(Store(other)), "memory")["nodes"]), 1)
        with self.store.connect(write=True) as db:
            db.execute("UPDATE knowledge SET content='memory corrupted'")
        self.assertEqual(context(self.runtime, "memory")["excluded"][0]["kind"], "knowledge")

    def test_skill_pin_and_mcp_boundary(self):
        folder = Path(self.temp.name) / "memory"
        folder.mkdir()
        skill = folder / "SKILL.md"
        skill.write_text("---\nname: memory\ndescription: Memory guidance\n---\nInstructions\n")
        self.store.register_skill("memory/SKILL.md")
        package = invoke(self.runtime, "bastion_context", {"query": "memory"})
        self.assertTrue(any(n["kind"] == "skill" for n in package["nodes"]))
        skill.write_text("changed")
        self.assertEqual(context(self.runtime, "memory")["excluded"][0]["kind"], "skill")
        self.assertIn("bastion_context", {t["name"] for t in listing()["tools"]})
        for query in ("", "   ", "x" * 201, None):
            with self.assertRaises(BastionError):
                context(self.runtime, query)
        self.assertEqual(len(context(self.runtime, "%")["nodes"]), 1)

    def test_cli_package_matches_direct_context(self):
        self.lesson()
        result = subprocess.run([sys.executable, "-m", "bastion", "--workspace", self.temp.name,
            "brain", "memory"], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), context(self.runtime, "memory"))


if __name__ == "__main__":
    unittest.main()
