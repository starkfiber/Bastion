# 0.4.0 Check Edition — local candidate

The release adds a real code-check boundary beyond 0.3's bounded built-ins. Explicit file and interpreter hashes are bound to a full inspectable plan. Approval precedes execution. A separate worktree and process group run named unittest modules with CPU/wall/output/state guards. Receipts preserve pass/fail separately from evidence integrity, including logs, observed test counts and snapshot hashes. Native RF² gates apply when configured. No installed plugin or host settings were changed.

Qualification runs four checks against the actual Bastion kernel, then changes the copied sum implementation to return a wrong result. The original passes, the regression fails one test, fresh-process verification preserves both outcomes, and repeating the failed job reuses its receipt. Additional unit tests cover empty/skipped-only suites, source and log tampering, output/time limits and approval refusal.

## What remains before overnight MVP delivery

| Priority | Gate | Needed evidence |
|---|---|---|
| 1 | OS-enforced execution isolation | A protected worker/VM or authorized sandbox must deny outside writes, private reads and outbound network; current nested sandbox probe was refused |
| 2 | Check/build jobs inside missions | Typed effects, explicit reconciliation and safe retry policy; current code checks deliberately stay outside automatic mission recovery |
| 3 | Real planner and build recipe | Authorized host/model execution on one concrete MVP with pinned dependencies and independently checked artifacts |
| 4 | Installed scheduler | User-selected real project, persistent host installation and sleep/reboot/missed-run tests; no scheduler is installed |
| 5 | Named chat routing and evaluated memory | Explicit conversation scope, project isolation, retrieval/compaction tests and recoverable archive policy |

The host refused the nested sandbox-exec probe (exit 71). Therefore source pinning and copied worktrees are not advertised as hostile-code isolation. The code being executed is trusted, reviewed local code and retains the host's permissions. Captured output is byte-bounded; filesystem monitoring may overshoot between polls; CPU accounting is per process rather than aggregate. Test success is observed behavior, not a proof of program correctness.

The installed RF² harness plugin remains unchanged. This version is the local candidate in this repository. Historical 0.3 and earlier receipts retain their original scope; they are not relabeled as 0.4 qualification.
