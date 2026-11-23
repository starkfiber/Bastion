"""Pinned RF² decision/compute adapter. No shell or arbitrary native command surface."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from .core import BastionError, canonical


class NativeEngine:
    def __init__(self, path, sha256, floor_mib=40960):
        self.path = Path(path)
        if not self.path.is_absolute() or self.path.is_symlink() or not self.path.is_file():
            raise BastionError("native engine must be an absolute regular non-symlink file")
        if type(floor_mib) is not int or not 1 <= floor_mib <= 2**32 - 1:
            raise BastionError("invalid native free-space floor")
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != sha256:
            raise BastionError("native engine hash mismatch")
        if not os.access(str(self.path), os.X_OK):
            raise BastionError("native engine is not executable")
        self.identity = {"path": str(self.path), "sha256": sha256, "floorMiB": floor_mib,
                         "contract": "RF2_SYSTEM_A64_V1"}

    def call(self, args=(), data=None):
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.identity["sha256"]:
            raise BastionError("native engine changed")
        try:
            result = subprocess.run([str(self.path), *map(str, args)], input=data,
                stdin=subprocess.DEVNULL if data is None else None, text=True,
                capture_output=True, timeout=5)
            if len(result.stdout) > 4096:
                raise BastionError("native response exceeds contract")
            value = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise BastionError("native engine unavailable or invalid response") from exc
        return result.returncode, value

    def sum(self, values):
        if not isinstance(values, list) or len(values) > 64 or any(type(v) is not int or not 0 <= v < 2**32 for v in values):
            raise BastionError("expected at most 64 u32 integers")
        rc, value = self.call(data="7 " + str(len(values)) + " " + " ".join(map(str, values)) + "\n")
        if rc == 3 and value == {"error": "overflow"}:
            raise BastionError("u32 overflow")
        if rc != 0 or set(value) != {"value"} or type(value["value"]) is not int or value["value"] != sum(values):
            raise BastionError("native sum failed independent verification")
        return value["value"]

    def gate(self, state, action, approved, workspace):
        states = {"draft": 0, "approved": 1, "running": 2, "verified": 3, "failed": 4, "uncertain": 5}
        actions = {"approve": 0, "start": 1, "finish": 2, "fail": 3, "interrupt": 4, "retry": 6}
        free = min(shutil.disk_usage(workspace).free // 2**20, 2**32 - 1)
        rc, value = self.call([states[state], actions[action], free, self.identity["floorMiB"], 1, int(approved), 0])
        if rc != 0 or not isinstance(value, dict) or type(value.get("allowed")) is not bool:
            raise BastionError("invalid native gate response")
        return value


def configured(store):
    with store.connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key='native-engine'").fetchone()
    if not row:
        return None
    value = json.loads(row["value"])
    return NativeEngine(value["path"], value["sha256"], value["floorMiB"])


def configure(store, path, sha256):
    engine = NativeEngine(path, sha256)
    # The identity is explicitly supplied by the operator. A hash is not a signature.
    if engine.sum([1, 2, 3]) != 6:
        raise BastionError("native contract probe failed")
    with store.connect(write=True) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('native-engine',?)", (canonical(engine.identity),))
        store.event(db, "native", "engine-configured", engine.identity)
    return {"native": engine.identity, "scope": "pinned native gate and checked sum; not an AI inference engine"}
