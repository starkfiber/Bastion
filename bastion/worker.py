"""A mission-owned process group with a parent-loss and deadline watchdog."""
import json
import os
import signal
import sys
import threading
import time

from .core import BastionError, canonical
from .runtime import Runtime
from .store import Store


def main():
    if len(sys.argv) not in (7,8):
        raise SystemExit("worker requires workspace, run, digest, parent PID, seconds, state byte limit")
    workspace, run, claimed, parent, seconds, state_limit = sys.argv[1:7]
    kind=sys.argv[7] if len(sys.argv)==8 else 'workflow'
    if kind not in ('workflow','check'): raise SystemExit('unsupported job kind')
    parent, seconds, state_limit = int(parent), float(seconds), int(state_limit)
    if os.getpid() != os.getpgrp() or os.getppid() != parent or not 0 < seconds <= 86400:
        raise SystemExit("worker requires its own managed process group and live parent")
    store = Store(workspace)
    deadline = time.monotonic() + seconds
    stop = threading.Event()

    def watch():
        from .missions import storage
        while not stop.wait(0.05):
            try:
                exceeded = storage(store) > state_limit
            except OSError:
                exceeded = True
            if os.getppid() != parent or time.monotonic() >= deadline or exceeded:
                os.killpg(os.getpgrp(), signal.SIGKILL)

    threading.Thread(target=watch, daemon=True).start()
    try:
        runtime=Runtime(store)
        if kind=='check':
            from .checks import run as run_check
            result=run_check(runtime,run,claimed)
        else:
            result=runtime.run(run,claimed)
        print(canonical(result), flush=True)
    except (BastionError, OSError, ValueError) as exc:
        print(canonical({"error": str(exc)}), file=sys.stderr, flush=True)
        return 1
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
