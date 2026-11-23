"""Trusted unittest bootstrap for explicitly reviewed code; not a security boundary."""
import json
import os
from pathlib import Path
import resource
import signal
import sys
import threading
import time
import unittest


def main():
    root, parent, wall, cpu = Path(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
    if os.getpid() != os.getpgrp() or os.getppid() != parent: raise SystemExit("managed check process required")
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    deadline, stop = time.monotonic()+wall, threading.Event()
    def watch():
        while not stop.wait(0.05):
            if os.getppid()!=parent or time.monotonic()>=deadline: os.killpg(os.getpgrp(),signal.SIGKILL)
    threading.Thread(target=watch,daemon=True).start()
    manifest=json.loads((root/'request.json').read_text())['manifest']
    sys.path.insert(0,str(root/'snapshot'))
    try:
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in manifest['testModules'])
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        passed=result.wasSuccessful() and result.testsRun>=manifest['minTests'] and result.testsRun>len(result.skipped)
        (root/'result.json').write_text(json.dumps({'passed':passed,'testsRun':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'skipped':len(result.skipped)})+'\n')
        return 0 if passed else 1
    finally: stop.set()


if __name__=='__main__': sys.exit(main())
