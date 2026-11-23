"""Project-scoped persistence. Same-user integrity, not hostile-user isolation."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid

from .core import BastionError, canonical, digest


def runtime_digest():
    root = Path(__file__).parent
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.glob("*.py"))})


class Store:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve(strict=True)
        if not self.workspace.is_dir():
            raise BastionError("workspace must be a directory")
        self.root = self.workspace / ".bastion"
        if self.root.is_symlink():
            raise BastionError("state directory cannot be a symlink")
        self.root.mkdir(mode=0o700, exist_ok=True)
        info = self.root.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise BastionError("state directory must be private and user-owned")
        self.path = self.root / "state.sqlite3"
        if self.path.is_symlink():
            raise BastionError("database cannot be a symlink")
        descriptor = os.open(str(self.path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise BastionError("database must be a private regular file")
        finally:
            os.close(descriptor)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, plan TEXT NOT NULL,
              digest TEXT NOT NULL, state TEXT NOT NULL, approved TEXT, receipt TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS tasks(run TEXT NOT NULL, node TEXT NOT NULL,
              state TEXT NOT NULL, params TEXT, result TEXT, result_digest TEXT,
              PRIMARY KEY(run,node));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, run TEXT NOT NULL,
              kind TEXT NOT NULL, payload TEXT NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS knowledge(id TEXT PRIMARY KEY, source TEXT NOT NULL,
              content TEXT NOT NULL, sha256 TEXT NOT NULL, provenance TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS skills(name TEXT PRIMARY KEY, path TEXT NOT NULL,
              sha256 TEXT NOT NULL, description TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS experiences(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
              summary TEXT NOT NULL, evidence TEXT NOT NULL, quality TEXT NOT NULL,
              created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY, text TEXT NOT NULL,
              source TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS handoffs(id TEXT PRIMARY KEY, package TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS handoff_proposals(run TEXT PRIMARY KEY, handoff TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cartridges(id TEXT PRIMARY KEY, name TEXT NOT NULL,
              version TEXT NOT NULL, package TEXT NOT NULL, UNIQUE(name,version));
            CREATE TABLE IF NOT EXISTS cartridge_qualifications(id TEXT PRIMARY KEY, cartridge TEXT NOT NULL, report TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cartridge_active(name TEXT PRIMARY KEY, cartridge TEXT NOT NULL, qualification TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checks(id TEXT PRIMARY KEY, plan TEXT NOT NULL, digest TEXT NOT NULL,
              state TEXT NOT NULL, approved TEXT, receipt TEXT, receipt_digest TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS cache_entries(id TEXT PRIMARY KEY, size INTEGER NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY, plan TEXT NOT NULL, digest TEXT NOT NULL,
              state TEXT NOT NULL, approved TEXT, started REAL, error TEXT);
            CREATE TABLE IF NOT EXISTS mission_jobs(mission TEXT NOT NULL, position INTEGER NOT NULL,
              run TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL,
              receipt TEXT, output_bytes INTEGER, error TEXT, PRIMARY KEY(mission,position));
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns={row['name'] for row in db.execute('PRAGMA table_info(mission_jobs)')}
            if 'kind' not in columns:
                db.execute("ALTER TABLE mission_jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'workflow'")

    @contextlib.contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(str(self.path), timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA fullfsync=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def project_file(self, relative):
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise BastionError("file must be a relative project path")
        path = self.workspace / relative
        cursor = self.workspace
        for part in Path(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise BastionError("symlink inputs are not supported")
        resolved = path.resolve(strict=True)
        if self.workspace not in resolved.parents or self.root == resolved or self.root in resolved.parents:
            raise BastionError("input must remain in project, outside internal state")
        if not resolved.is_file() or resolved.stat().st_size > 1024 * 1024:
            raise BastionError("input must be a file of at most 1 MiB")
        return resolved

    @contextlib.contextmanager
    def execution_lock(self, run):
        from .core import identifier
        identifier(run)
        path = self.root / (run + ".lock")
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise BastionError("execution lock is not private")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BastionError("run has an active worker; recovery refused") from exc
            yield
        finally:
            os.close(fd)

    def knowledge_snapshot(self):
        with self.connect() as db:
            records = [dict(row) for row in db.execute("SELECT * FROM knowledge ORDER BY id")]
        if len(canonical(records).encode()) > 8 * 1024 * 1024:
            raise BastionError("knowledge snapshot exceeds 8 MiB; narrow the project")
        return records

    @staticmethod
    def event(db, run, kind, payload):
        previous = db.execute("SELECT digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        data = {"run": run, "kind": kind, "payload": payload, "previous": previous}
        db.execute("INSERT INTO events(run,kind,payload,previous,digest) VALUES(?,?,?,?,?)",
                   (run, kind, canonical(payload), previous, digest(data)))

    def verify_events(self):
        previous = "0" * 64
        count = 0
        with self.connect() as db:
            for row in db.execute("SELECT * FROM events ORDER BY seq"):
                data = {"run": row["run"], "kind": row["kind"],
                        "payload": json.loads(row["payload"]), "previous": previous}
                if row["previous"] != previous or row["digest"] != digest(data):
                    raise BastionError("event chain verification failed")
                previous = row["digest"]
                count += 1
        return {"events": count, "head": previous, "scope": "local-integrity"}

    def knowledge_root(self):
        with self.connect() as db:
            return digest([list(row) for row in db.execute("SELECT id,sha256 FROM knowledge ORDER BY id")])

    def search(self, query, table="knowledge"):
        if not isinstance(query, str) or not 1 <= len(query) <= 200:
            raise BastionError("query must contain 1..200 characters")
        if table not in ("knowledge", "experiences"):
            raise BastionError("unknown search collection")
        field = "content" if table == "knowledge" else "summary"
        needle = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM " + table + " WHERE " + field + " LIKE ? ESCAPE '\\' ORDER BY id LIMIT 20", ("%" + needle + "%",))]

    def add_experience(self, kind, summary, evidence, quality):
        identity = digest({"kind": kind, "summary": summary, "evidence": evidence, "quality": quality})
        with self.connect(write=True) as db:
            db.execute("INSERT OR IGNORE INTO experiences VALUES(?,?,?,?,?,?)",
                       (identity, kind, summary, canonical(evidence), quality, time.time()))
        return identity

    def register_skill(self, relative):
        path = self.project_file(relative)
        text = path.read_text()
        if path.name != "SKILL.md" or not text.startswith("---\n"):
            raise BastionError("expected SKILL.md with frontmatter")
        parts = text.split("---", 2)
        if len(parts) != 3:
            raise BastionError("unterminated skill metadata")
        # A deliberately bounded subset; reject complex YAML instead of guessing.
        fields = {}
        for line in parts[1].strip().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            if ":" not in line or line[0].isspace():
                raise BastionError("only flat name/description metadata is supported")
            key, value = line.split(":", 1)
            if key in fields or key not in ("name", "description"):
                raise BastionError("unsupported or duplicate skill metadata")
            fields[key] = value.strip().strip("\"'")
        import re
        name = fields.get("name", "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64 or path.parent.name != name:
            raise BastionError("skill name must match its directory")
        description = fields.get("description", "")
        if not 1 <= len(description) <= 1024:
            raise BastionError("skill description required")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.connect(write=True) as db:
            db.execute("INSERT OR REPLACE INTO skills VALUES(?,?,?,?)", (name, relative, sha, description))
            self.event(db, "skills", "register", {"name": name, "sha256": sha})
        return {"name": name, "sha256": sha, "authority": "guidance-only", "scripts_executed": False}

    def skill_pins(self, names):
        pins = []
        with self.connect() as db:
            for name in sorted(set(names)):
                row = db.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
                if not row:
                    raise BastionError("skill is not registered")
                if hashlib.sha256(self.project_file(row["path"]).read_bytes()).hexdigest() != row["sha256"]:
                    raise BastionError("registered skill changed")
                pins.append(dict(row))
        return pins

    def propose_lesson(self, text, source):
        if not isinstance(text, str) or not 1 <= len(text) <= 4000:
            raise BastionError("lesson must contain 1..4000 characters")
        with self.connect(write=True) as db:
            if not db.execute("SELECT 1 FROM experiences WHERE id=?", (source,)).fetchone():
                raise BastionError("lesson requires existing experience")
            identity = uuid.uuid4().hex
            db.execute("INSERT INTO lessons VALUES(?,?,?,?)", (identity, text, source, "proposed"))
            self.event(db, identity, "lesson-proposed", {"source": source, "textDigest": digest(text)})
        return identity

    def promote_lesson(self, identity):
        # Explicit operator review plus revalidation; synthetic batches never qualify.
        from .runtime import Runtime
        with self.connect() as db:
            row = db.execute("SELECT l.*, e.kind,e.evidence,e.quality FROM lessons l JOIN experiences e ON l.source=e.id WHERE l.id=?", (identity,)).fetchone()
            if not row or row["quality"] != "verified-local-workflow" or row["kind"] != "workflow":
                raise BastionError("lesson requires verified workflow evidence, not simulation volume")
            evidence = json.loads(row["evidence"])
        result = Runtime(self).verify(evidence["run"])
        if result["receiptDigest"] != evidence["receiptDigest"]:
            raise BastionError("lesson evidence changed")
        with self.connect(write=True) as db:
            db.execute("UPDATE lessons SET state='reviewed' WHERE id=?", (identity,))
            self.event(db, identity, "lesson-reviewed", {"evidence": evidence})
        return {"id": identity, "state": "reviewed", "scope": "this-project", "policy_authority": False}
