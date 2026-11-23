"""DAG scheduler with exact approval, content pins and resumable node receipts."""
import hashlib
import json
import uuid

from .core import (BastionError, CAPABILITIES, canonical, decide, digest,
                   execute_pure, identifier, resolve, validate_workflow, verify_pure)
from .store import runtime_digest


class Runtime:
    def __init__(self, store):
        self.store = store
        from .native import configured
        self.native = configured(store)

    def plan(self, workflow, cartridge=None):
        order = validate_workflow(workflow)
        files = {}
        for node in workflow["nodes"]:
            if node["capability"] == "knowledge.ingest":
                relative = node["params"]["path"]
                if not isinstance(relative, str):
                    raise BastionError("ingest path must be literal at planning time")
                files[relative] = hashlib.sha256(self.store.project_file(relative).read_bytes()).hexdigest()
        envelope = {"schema": "bastion.plan.v1", "workflow": workflow, "order": order,
                    "runtimeDigest": runtime_digest(), "capabilities": CAPABILITIES,
                    "files": files, "skills": self.store.skill_pins(workflow.get("skills", [])),
                    "knowledgeSnapshot": self.store.knowledge_snapshot(), "workspace": str(self.store.workspace)}
        if cartridge is not None:
            envelope["cartridge"] = cartridge
        envelope["native"] = self.native.identity if self.native else None
        envelope["knowledgeRoot"] = digest([[r["id"], r["sha256"]] for r in envelope["knowledgeSnapshot"]])
        identity = uuid.uuid4().hex
        sha = digest(envelope)
        with self.store.connect(write=True) as db:
            db.execute("INSERT INTO runs(id,plan,digest,state) VALUES(?,?,?,'draft')", (identity, canonical(envelope), sha))
            for node in workflow["nodes"]:
                db.execute("INSERT INTO tasks(run,node,state) VALUES(?,?,'pending')", (identity, node["id"]))
            self.store.event(db, identity, "planned", {"planDigest": sha})
        return {"run": identity, "digest": sha, "state": "draft", "plan": envelope}

    @staticmethod
    def row(db, run):
        identifier(run)
        row = db.execute("SELECT * FROM runs WHERE id=?", (run,)).fetchone()
        if not row:
            raise BastionError("run not found")
        return row

    def bound(self, row, claimed=None, live=False):
        from .native import configured
        current_native = configured(self.store)
        if (current_native.identity if current_native else None) != (self.native.identity if self.native else None):
            raise BastionError("native configuration changed; reopen runtime")
        plan = json.loads(row["plan"])
        if digest(plan) != row["digest"] or (claimed is not None and claimed != row["digest"]):
            raise BastionError("plan digest mismatch")
        if plan["runtimeDigest"] != runtime_digest() or plan["capabilities"] != CAPABILITIES:
            raise BastionError("runtime identity changed; create a new plan")
        if plan["workspace"] != str(self.store.workspace):
            raise BastionError("workspace identity changed")
        if plan.get("native") != (self.native.identity if self.native else None):
            raise BastionError("native engine identity changed; create a new plan")
        if live:
            if "cartridge" in plan:
                for relative, wanted in plan["cartridge"]["assets"].items():
                    if hashlib.sha256(self.store.project_file(relative).read_bytes()).hexdigest() != wanted:
                        raise BastionError("cartridge asset identity changed")
            current = self.store.skill_pins(plan["workflow"].get("skills", []))
            if current != plan["skills"]:
                raise BastionError("skill identity changed")
            for relative, wanted in plan["files"].items():
                if hashlib.sha256(self.store.project_file(relative).read_bytes()).hexdigest() != wanted:
                    raise BastionError("input identity changed")
        return plan

    def transition(self, db, row, action, explicit=False):
        allowed, following, reason = decide(row["state"], action,
            explicit or row["approved"] == row["digest"], True, True, True, explicit)
        if not allowed:
            raise BastionError(reason)
        if self.native:
            native = self.native.gate(row["state"], action, explicit or row["approved"] == row["digest"], self.store.workspace)
            states = {"draft": 0, "approved": 1, "running": 2, "verified": 3, "failed": 4, "uncertain": 5}
            if not native["allowed"] or native.get("next") != states[following]:
                raise BastionError("native gate refused: " + str(native.get("reason")))
        db.execute("UPDATE runs SET state=? WHERE id=?", (following, row["id"]))
        return following

    def approve(self, run, claimed):
        with self.store.connect(write=True) as db:
            row = self.row(db, run)
            plan = self.bound(row, claimed, live=True)
            if self.store.knowledge_root() != plan["knowledgeRoot"]:
                raise BastionError("knowledge changed since planning")
            if row["state"] == "approved" and row["approved"] == claimed:
                return {"run": run, "digest": claimed, "state": "approved"}
            state = self.transition(db, row, "approve", explicit=True)
            db.execute("UPDATE runs SET approved=? WHERE id=?", (claimed, run))
            self.store.event(db, run, "approved", {"digest": claimed})
        return {"run": run, "digest": claimed, "state": state}

    def check_knowledge_context(self, plan):
        base = {r["id"]: r["sha256"] for r in plan["knowledgeSnapshot"]}
        permitted = {digest({"source": p, "sha256": sha}): sha for p, sha in plan["files"].items()}
        current = self.store.knowledge_snapshot()
        observed = {r["id"]: r["sha256"] for r in current}
        if any(observed.get(identity) != sha for identity, sha in base.items()):
            raise BastionError("knowledge changed since approval")
        for record in current:
            if (record["id"] not in base and permitted.get(record["id"]) != record["sha256"]
                    or hashlib.sha256(record["content"].encode()).hexdigest() != record["sha256"]):
                raise BastionError("knowledge changed since approval")

    def knowledge_for_outputs(self, plan, outputs):
        records = {r["id"]: r for r in plan["knowledgeSnapshot"]}
        with self.store.connect() as db:
            for node in plan["workflow"]["nodes"]:
                if node["capability"] == "knowledge.ingest" and node["id"] in outputs:
                    identity = outputs[node["id"]]["id"]
                    row = db.execute("SELECT * FROM knowledge WHERE id=?", (identity,)).fetchone()
                    if not row:
                        raise BastionError("retained knowledge missing")
                    records[identity] = dict(row)
        return records

    @staticmethod
    def search_snapshot(records, query):
        if not isinstance(query, str) or not 1 <= len(query) <= 200:
            raise BastionError("invalid knowledge query")
        return [r for _, r in sorted(records.items()) if query.lower() in r["content"].lower()][:20]

    def inspect(self, run):
        with self.store.connect() as db:
            row = self.row(db, run)
            tasks = [dict(t) for t in db.execute("SELECT * FROM tasks WHERE run=? ORDER BY node", (run,))]
            return {"run": run, "state": row["state"], "digest": row["digest"],
                    "approved": row["approved"] == row["digest"], "error": row["error"],
                    "plan": json.loads(row["plan"]), "tasks": tasks,
                    "receipt": json.loads(row["receipt"]) if row["receipt"] else None}

    def execute_node(self, node, params, plan, outputs=None):
        if self.native and node["capability"] == "math.sum_u32":
            return self.native.sum(params["values"])
        capability = node["capability"]
        if CAPABILITIES[capability]["effect"] == "pure":
            return execute_pure(capability, params)
        if capability == "knowledge.search":
            return self.search_snapshot(self.knowledge_for_outputs(plan, outputs or {}), params["query"])
        if capability == "knowledge.ingest":
            relative = params["path"]
            content = self.store.project_file(relative).read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            if sha != plan["files"].get(relative):
                raise BastionError("input changed during execution")
            text = content.decode("utf-8")
            identity = digest({"source": relative, "sha256": sha})
            with self.store.connect(write=True) as db:
                db.execute("INSERT OR IGNORE INTO knowledge VALUES(?,?,?,?,?)",
                           (identity, relative, text, sha, "user-selected-project-file; data-not-authority"))
            return {"id": identity, "sha256": sha, "source": relative}
        raise BastionError("unsupported capability")

    def run(self, run, claimed):
        with self.store.execution_lock(run):
            return self._run(run, claimed)

    def _run(self, run, claimed):
        with self.store.connect() as db:
            completed = self.row(db, run)["state"] == "verified"
        if completed:
            with self.store.connect() as db:
                self.bound(self.row(db, run), claimed)
            return self.verify(run)
        with self.store.connect(write=True) as db:
            row = self.row(db, run)
            plan = self.bound(row, claimed, live=True)
            self.check_knowledge_context(plan)
            self.transition(db, row, "start")
            self.store.event(db, run, "started", {"digest": claimed})
            db.execute("UPDATE runs SET error=NULL WHERE id=?", (run,))
        outputs = {}
        try:
            nodes = {node["id"]: node for node in plan["workflow"]["nodes"]}
            for name in plan["order"]:
                node = nodes[name]
                with self.store.connect(write=True) as db:
                    task = db.execute("SELECT * FROM tasks WHERE run=? AND node=?", (run, name)).fetchone()
                    params = resolve(node["params"], outputs)
                    if task["state"] == "done":
                        value = json.loads(task["result"])
                        if digest(value) != task["result_digest"] or canonical(params) != task["params"]:
                            raise BastionError("retained task integrity failure")
                        outputs[name] = value
                        continue
                    if task["state"] != "pending":
                        raise BastionError("unfinished task requires explicit recovery")
                    db.execute("UPDATE tasks SET state='running',params=? WHERE run=? AND node=?", (canonical(params), run, name))
                    self.store.event(db, run, "node-started", {"node": name})
                value = self.execute_node(node, params, plan, outputs)
                if len(canonical(value).encode()) > 2 * 1024 * 1024:
                    raise BastionError("node output exceeds 2 MiB")
                if "cartridge" in plan:
                    from .cartridges import bounded
                    bounded(dict(outputs, **{name: value}), plan["cartridge"]["budgets"]["maxOutputBytes"])
                with self.store.connect(write=True) as db:
                    db.execute("UPDATE tasks SET state='done',result=?,result_digest=? WHERE run=? AND node=?",
                               (canonical(value), digest(value), run, name))
                    self.store.event(db, run, "node-completed", {"node": name, "resultDigest": digest(value)})
                outputs[name] = value
            receipt = {"schema": "bastion.receipt.v1", "run": run, "planDigest": claimed,
                       "runtimeDigest": plan["runtimeDigest"], "outputs": outputs,
                       "proof": "bounded-local-workflow", "externalEffects": False,
                       "isolation": "trusted-builtins-only; no OS sandbox"}
            # Verify before declaring the run verified, not merely after writing a result.
            self.verify_tasks(run, plan)
            with self.store.connect(write=True) as db:
                row = self.row(db, run)
                self.transition(db, row, "finish")
                db.execute("UPDATE runs SET receipt=? WHERE id=?", (canonical(receipt), run))
                self.store.event(db, run, "verified", {"receiptDigest": digest(receipt)})
            self.ensure_experience(receipt)
            return {"run": run, "state": "verified", "receipt": receipt, "receiptDigest": digest(receipt)}
        except Exception as exc:
            with self.store.connect(write=True) as db:
                row = self.row(db, run)
                if row["state"] == "running":
                    self.transition(db, row, "fail")
                    db.execute("UPDATE runs SET error=? WHERE id=?", (str(exc)[:1000], run))
                    self.store.event(db, run, "failed", {"reason": str(exc)[:1000]})
            if isinstance(exc, BastionError):
                raise
            raise BastionError(str(exc)) from exc

    def verify_tasks(self, run, plan):
        outputs = {}
        nodes = {node["id"]: node for node in plan["workflow"]["nodes"]}
        with self.store.connect() as db:
            for name in plan["order"]:
                row = db.execute("SELECT * FROM tasks WHERE run=? AND node=?", (run, name)).fetchone()
                if not row or row["state"] != "done":
                    raise BastionError("workflow incomplete")
                value = json.loads(row["result"])
                params = resolve(nodes[name]["params"], outputs)
                if canonical(params) != row["params"] or digest(value) != row["result_digest"]:
                    raise BastionError("task integrity failure")
                capability = nodes[name]["capability"]
                if CAPABILITIES[capability]["effect"] == "pure":
                    if not verify_pure(capability, params, value):
                        raise BastionError("independent task verification failed")
                elif capability == "knowledge.ingest":
                    expected = {"id": digest({"source": params["path"], "sha256": plan["files"][params["path"]]}),
                                "sha256": plan["files"][params["path"]], "source": params["path"]}
                    if value != expected:
                        raise BastionError("ingest receipt identity failed")
                    record = db.execute("SELECT * FROM knowledge WHERE id=?", (value["id"],)).fetchone()
                    if not record or hashlib.sha256(record["content"].encode()).hexdigest() != value["sha256"]:
                        raise BastionError("knowledge content changed")
                elif capability == "knowledge.search":
                    expected = self.search_snapshot(self.knowledge_for_outputs(plan, outputs), params["query"])
                    if value != expected:
                        raise BastionError("invalid knowledge search evidence")
                outputs[name] = value
        if "cartridge" in plan:
            from .cartridges import bounded
            bounded(outputs, plan["cartridge"]["budgets"]["maxOutputBytes"])
        return outputs

    def ensure_experience(self, receipt):
        return self.store.add_experience("workflow", "Verified workflow " + receipt["run"],
            {"run": receipt["run"], "receiptDigest": digest(receipt)}, "verified-local-workflow")

    def verify(self, run):
        with self.store.connect() as db:
            row = self.row(db, run)
            plan = self.bound(row)
            if row["state"] != "verified" or not row["receipt"] or row["approved"] != row["digest"]:
                raise BastionError("no verified approved receipt")
            receipt = json.loads(row["receipt"])
            expected = {"schema": "bastion.receipt.v1", "run": run, "planDigest": row["digest"],
                        "runtimeDigest": plan["runtimeDigest"], "outputs": self.verify_tasks(run, plan),
                        "proof": "bounded-local-workflow", "externalEffects": False,
                        "isolation": "trusted-builtins-only; no OS sandbox"}
            if receipt != expected:
                raise BastionError("receipt verification failed")
            events = db.execute("SELECT payload FROM events WHERE run=? AND kind='verified'", (run,)).fetchall()
            if not any(json.loads(e["payload"]).get("receiptDigest") == digest(receipt) for e in events):
                raise BastionError("receipt has no matching verification event")
        chain = self.store.verify_events()
        self.ensure_experience(receipt)
        return {"run": run, "state": "verified", "receipt": receipt, "receiptDigest": digest(receipt), "audit": chain}

    def recover(self, run, claimed):
        with self.store.execution_lock(run):
            return self._recover(run, claimed)

    def _recover(self, run, claimed):
        # The kernel file lock proves this runtime has no live worker for the run.
        with self.store.connect(write=True) as db:
            row = self.row(db, run)
            self.bound(row, claimed, live=True)
            if row["state"] == "running":
                self.transition(db, row, "interrupt")
                self.store.event(db, run, "interrupted", {})
                row = self.row(db, run)
            failed = row["state"] == "failed"
            self.transition(db, row, "retry", explicit=True)
            if failed:
                # A completed task may itself have failed verification. All supported
                # effects are pure or content-addressed/idempotent, so recompute safely.
                db.execute("UPDATE tasks SET state='pending',params=NULL,result=NULL,result_digest=NULL WHERE run=?", (run,))
            else:
                db.execute("UPDATE tasks SET state='pending' WHERE run=? AND state!='done'", (run,))
            self.store.event(db, run, "operator-retry", {"digest": claimed})
        return {"run": run, "state": "approved", "digest": claimed}
