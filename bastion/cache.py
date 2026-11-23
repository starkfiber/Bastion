"""Quota-bound explicitly rebuildable cache. Unique knowledge and receipts are never pruned."""
import hashlib
import os
import stat
import time

from .core import BastionError, digest


def directory(store):
    root = store.root / "cache"
    if root.is_symlink():
        raise BastionError("cache directory cannot be a symlink")
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise BastionError("cache directory must be private and user-owned")
    return root


def stash(store, relative, ttl=3600, quota=16 * 1024 * 1024):
    if type(ttl) is not int or not 1 <= ttl <= 86400 or type(quota) is not int or not 1 <= quota <= 64 * 1024 * 1024:
        raise BastionError("invalid cache budget or TTL")
    content = store.project_file(relative).read_bytes()
    identity = hashlib.sha256(content).hexdigest()
    root = directory(store)
    with store.connect(write=True) as db:
        total = sum(p.stat().st_size for p in root.iterdir() if p.is_file() and not p.is_symlink())
        path = root / identity
        if path.is_symlink():
            raise BastionError("cache object cannot be a symlink")
        if total + (0 if path.exists() else len(content)) > quota:
            raise BastionError("cache quota exhausted")
        if not path.exists():
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        if path.read_bytes() != content:
            raise BastionError("cache object hash mismatch")
        db.execute("INSERT OR REPLACE INTO cache_entries VALUES(?,?,?)", (identity, len(content), time.time() + ttl))
    return {"object": identity, "bytes": len(content), "classification": "explicitly-rebuildable"}


def prune_plan(store):
    root = directory(store)
    with store.connect() as db:
        records = [dict(r) for r in db.execute("SELECT * FROM cache_entries WHERE expires<=? ORDER BY id", (time.time(),))]
    for record in records:
        path = root / record["id"]
        if path.is_symlink() or (path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != record["id"]):
            raise BastionError("cache prune identity mismatch")
    value = {"objects": records, "scope": "registered expired rebuildable cache only", "workspace": str(store.workspace)}
    return dict(value, digest=digest(value))


def prune(store, claimed):
    plan = prune_plan(store)
    if plan["digest"] != claimed:
        raise BastionError("cache prune plan changed; inspect a fresh plan")
    root = directory(store)
    with store.connect(write=True) as db:
        current = [dict(r) for r in db.execute("SELECT * FROM cache_entries WHERE expires<=? ORDER BY id", (time.time(),))]
        if current != plan["objects"]:
            raise BastionError("cache prune plan changed")
        for record in current:
            path = root / record["id"]
            if path.is_symlink() or (path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != record["id"]):
                raise BastionError("cache prune identity mismatch")
            path.unlink(missing_ok=True)
            db.execute("DELETE FROM cache_entries WHERE id=?", (record["id"],))
    return {"removed": len(current), "bytes": sum(r["size"] for r in current), "scope": plan["scope"]}
