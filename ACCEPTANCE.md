# Foundation acceptance contract

The implementation must:

1. Accept a model-neutral graph, reject unsupported effects and validate dependencies before execution.
2. Bind approval to the actual plan, runtime, project inputs and registered skill content.
3. Keep approval and recovery outside the model-facing MCP tool set.
4. Retain task evidence, verify results before declaring completion and return the same receipt on repeat execution.
5. Recover from real process death and partial idempotent local writes without falsely claiming verified completion.
6. Prevent a second runtime worker or recovery action from taking over the same active run.
7. Separate project data, skill guidance, evidence quality and execution authority.
8. Require explicit review and verifiable workflow evidence for reviewed lessons; refuse promotion based on synthetic volume.
9. Stream at least two million bounded policy/calculation trials, preserve actual outcomes and verify the complete ledger from a fresh process.
10. Report actual capability boundaries, blocked integrations and untested claims.

All ten requirements have supporting executable checks or retained evidence in this candidate. This contract intentionally does not certify arbitrary model quality, unrestricted orchestration, production security or installed-plugin interoperability. See `architecture.md` for the remaining gates.

## Mission Edition 0.3.0 contract

The local mission milestone additionally requires exact batch approval, persisted deadlines/attempt budgets, native executable identity pins, duplicate-worker exclusion, parent-loss cancellation, receipt reuse after real process death, output/state guards, and fresh-digest pruning of registered rebuildable cache only. Tests and retained `evidence/mission-qualification.json` and `evidence/mission-recovery.json` support that bounded scope.

The installed plugin remains unchanged. No arbitrary MVP build, live model call, other-chat dispatch, installed scheduler, physical power-loss recovery, browser correctness, capacity, security certification or AGI result is included in this milestone.
