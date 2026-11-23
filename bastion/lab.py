"""Streaming synthetic policy/kernel experiments, never simulated real users."""
import hashlib
import json
import os
from pathlib import Path
import struct
import time
import uuid

from .core import BastionError, canonical, decide, execute_pure
from .store import runtime_digest

STATES = ("draft", "approved", "running", "verified", "failed", "uncertain")
ACTIONS = ("approve", "start", "finish", "fail", "interrupt", "retry")
COMBINATIONS = len(STATES) * len(ACTIONS) * 32
# index, policy combination, allowed/expected, next/expected, operands, actual/expected result
ROW = struct.Struct("<QHBBBBIIQQ")
INVALID = 2**32
OVERFLOW = INVALID + 1
TABLE = {("draft", "approve"): "approved", ("approved", "start"): "running",
         ("running", "finish"): "verified", ("running", "fail"): "failed",
         ("running", "interrupt"): "uncertain", ("uncertain", "retry"): "approved",
         ("failed", "retry"): "approved"}


def fixture(index, seed):
    combo = index % COMBINATIONS
    flags = combo % 32
    action = ACTIONS[(combo // 32) % len(ACTIONS)]
    state = STATES[combo // (32 * len(ACTIONS))]
    approved, binding, budget, supported, explicit = [bool(flags & (1 << n)) for n in range(5)]
    # Independent truth-table oracle, not a call to decide() or its transition table.
    expected = (binding and supported and (state, action) in TABLE
                and (action not in ("approve", "retry") or explicit)
                and (action == "interrupt" or approved)
                and (action != "start" or budget))
    next_state = TABLE[(state, action)] if expected else state
    operand = ((index + seed) * 2654435761) & 0xffffffff
    kind = (index // COMBINATIONS) % 8
    small = operand % 1000000
    if kind == 0:
        values, reference = [small, small + 1], 2 * small + 1
    elif kind == 1:
        values, reference = [0xffffffff, small + 1], OVERFLOW
    elif kind == 2:
        values, reference = [True], INVALID
    elif kind == 3:
        values, reference = [-1], INVALID
    elif kind == 4:
        values, reference = [0] * 65, INVALID
    elif kind == 5:
        values, reference = [0xffffffff], 0xffffffff
    elif kind == 6:
        values, reference = [], 0
    else:
        values, reference = [2**32], INVALID
    return combo, (state, action, approved, binding, budget, supported, explicit), expected, next_state, small, kind, values, reference


def trial(index, seed):
    combo, policy, expected, following, small, kind, values, reference = fixture(index, seed)
    allowed, next_state, _ = decide(*policy)
    try:
        result = execute_pure("math.sum_u32", {"values": values})
    except BastionError as exc:
        result = OVERFLOW if "overflow" in str(exc) else INVALID
    failed = allowed != expected or next_state != following or result != reference
    packed = ROW.pack(index, combo, int(allowed), int(expected), STATES.index(next_state),
                      STATES.index(following), small, kind, result, reference)
    return packed, failed, allowed, kind


def run_campaign(store, trials, seed=1, max_seconds=60):
    if type(trials) is not int or not 1 <= trials <= 10000000:
        raise BastionError("trials must be 1..10,000,000")
    if type(seed) is not int or not 0 <= seed <= 0xffffffff or not 1 <= max_seconds <= 600:
        raise BastionError("invalid seed or wall-time budget")
    labs = store.root / "labs"
    if labs.is_symlink():
        raise BastionError("lab directory cannot be a symlink")
    labs.mkdir(mode=0o700, exist_ok=True)
    identity = uuid.uuid4().hex
    root = labs / identity
    root.mkdir(mode=0o700)
    manifest = {"schema": "bastion.lab.v1", "id": identity, "seed": seed,
                "requested": trials, "maxSeconds": max_seconds, "runtimeDigest": runtime_digest(),
                "scope": "synthetic-policy-and-u32-kernel", "externalRequests": 0,
                "modelCalls": 0, "generatorVersion": 1, "recordBytes": ROW.size}
    (root / "manifest.json").write_text(canonical(manifest) + "\n")
    (root / "summary.json").write_text(canonical({"status": "running", "executed": 0}) + "\n")
    started = time.monotonic()
    executed = failures = allowed_count = 0
    kinds = [0] * 8
    hasher = hashlib.sha256()
    with (root / "trials.bin").open("xb") as stream:
        buffer = bytearray()
        for index in range(trials):
            if index % 1000 == 0 and time.monotonic() - started >= max_seconds:
                break
            packed, failed, allowed, kind = trial(index, seed)
            buffer.extend(packed)
            executed += 1
            failures += int(failed)
            allowed_count += int(allowed)
            kinds[kind] += 1
            if len(buffer) >= 1024 * 1024:
                hasher.update(buffer)
                stream.write(buffer)
                buffer.clear()
        if buffer:
            hasher.update(buffer)
            stream.write(buffer)
        stream.flush()
        os.fsync(stream.fileno())
    summary = {"schema": "bastion.lab-result.v1", "campaign": identity,
               "manifestDigest": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
               "status": "complete" if executed == trials else "budget-exhausted",
               "requested": trials, "executedPolicyTrials": executed, "executedKernelFixtures": executed,
               "uniquePolicyCombinations": min(executed, COMBINATIONS), "kernelFamilies": kinds,
               "mismatches": failures, "allowedDecisions": allowed_count,
               "deniedDecisions": executed - allowed_count, "seconds": time.monotonic() - started,
               "ledgerBytes": executed * ROW.size, "ledgerSHA256": hasher.hexdigest(),
               "scope": manifest["scope"], "modelCalls": 0, "externalRequests": 0,
               "realWorldExperiences": 0, "learningPromotions": 0}
    temporary = root / "summary.part"
    temporary.write_text(canonical(summary) + "\n")
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    temporary.replace(root / "summary.json")
    store.add_experience("simulation", "Synthetic laboratory: %d policy trials and %d kernel fixtures; %d mismatches" % (executed, executed, failures),
                         {"campaign": identity, "summaryDigest": hashlib.sha256((root / "summary.json").read_bytes()).hexdigest()},
                         "synthetic-policy-kernel")
    return summary


def verify_campaign(store, identity):
    from .core import identifier
    identifier(identity)
    root = store.root / "labs" / identity
    if root.is_symlink() or (store.root / "labs").is_symlink():
        raise BastionError("lab directory cannot be a symlink")
    for name in ("manifest.json", "summary.json", "trials.bin"):
        if (root / name).is_symlink():
            raise BastionError("lab evidence cannot be a symlink")
    manifest = json.loads((root / "manifest.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    if manifest.get("runtimeDigest") != runtime_digest():
        raise BastionError("lab runtime identity changed")
    if summary.get("manifestDigest") != hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest():
        raise BastionError("lab manifest changed")
    if summary.get("status") != "complete" or summary.get("mismatches") != 0:
        raise BastionError("lab incomplete or contains failures")
    hasher = hashlib.sha256()
    count = 0
    allowed_count = 0
    kinds = [0] * 8
    with (root / "trials.bin").open("rb") as stream:
        while True:
            packed = stream.read(ROW.size)
            if not packed:
                break
            if len(packed) != ROW.size:
                raise BastionError("truncated lab ledger")
            hasher.update(packed)
            index, combo, allowed, expected, next_state, next_expected, small, kind, actual, reference = ROW.unpack(packed)
            fcombo, policy, oracle, following, operand, family, _, result = fixture(count, manifest["seed"])
            if ((index, combo, expected, next_expected, small, kind, reference)
                    != (count, fcombo, int(oracle), STATES.index(following), operand, family, result)
                    or allowed != expected or next_state != next_expected or actual != reference):
                raise BastionError("lab oracle or trial mismatch")
            count += 1
            allowed_count += allowed
            kinds[kind] += 1
    if (count != manifest["requested"] or count != summary.get("executedPolicyTrials")
            or count != summary.get("executedKernelFixtures") or count * ROW.size != summary.get("ledgerBytes")
            or allowed_count != summary.get("allowedDecisions") or count - allowed_count != summary.get("deniedDecisions")
            or kinds != summary.get("kernelFamilies") or hasher.hexdigest() != summary.get("ledgerSHA256")):
        raise BastionError("lab ledger integrity failed")
    return {"campaign": identity, "verified": True, "records": count,
            "scope": "retained-ledger-integrity-and-independent-oracle-consistency",
            "runtimeDigest": manifest["runtimeDigest"], "summary": summary}


def replay_trial(store, identity, index):
    from .core import identifier
    identifier(identity)
    if type(index) is not int or index < 0:
        raise BastionError("trial index must be nonnegative")
    root = store.root / "labs" / identity
    if root.is_symlink() or root.parent.is_symlink():
        raise BastionError("lab directory cannot be a symlink")
    for name in ("manifest.json", "summary.json", "trials.bin"):
        if (root / name).is_symlink():
            raise BastionError("lab evidence cannot be a symlink")
    manifest = json.loads((root / "manifest.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    if (manifest["runtimeDigest"] != runtime_digest()
            or summary.get("manifestDigest") != hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()):
        raise BastionError("lab identity changed")
    if index >= summary.get("executedPolicyTrials", 0):
        raise BastionError("trial was not executed")
    with (root / "trials.bin").open("rb") as stream:
        stream.seek(index * ROW.size)
        retained = stream.read(ROW.size)
    replayed, failed, _, _ = trial(index, manifest["seed"])
    if failed or retained != replayed:
        raise BastionError("trial replay disagrees with retained evidence")
    _, policy, expected, following, _, family, values, reference = fixture(index, manifest["seed"])
    return {"campaign": identity, "trial": index, "reproduced": True, "policy": list(policy),
            "expectedAllowed": expected, "expectedState": following, "kernelFamily": family,
            "values": values, "encodedReference": reference,
            "scope": "one-synthetic-trial; not-whole-campaign-verification"}
