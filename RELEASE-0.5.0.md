# 0.5.0 Mixed Mission Edition — local candidate

This version closes the typed mission/check integration gate. A mission can sequence bounded workflows and explicitly reviewed unittest jobs under one exact batch approval. Its plan discloses job kind, source pins, test manifest, uncontrolled external effects and missing OS isolation. Native RF² gates mediate the configured workflow and check paths.

## Recovery contract

| Job/outcome | Behavior |
|---|---|
| Interrupted bounded workflow | Existing idempotent recovery under approved budgets |
| Check passed and receipt committed | Verify and adopt receipt without re-executing code |
| Check failed | Block mission and downstream work; preserve failure receipt |
| Check interrupted without receipt | Block for investigation; never infer success or retry automatically |
| Operator-reviewed replacement | New draft mission, new exact approval, preserved lineage and original deadline/wall cutoff |

Old mission rows migrate to the workflow kind without rewriting IDs, digests or outcomes. Concurrent initialization is tested. A code replacement cannot reset an exhausted budget or gain time while awaiting approval. Legacy workflow-only specifications remain supported, subject to normal runtime-version reapproval.

## Qualification

The retained native-backed experiment completes a mixed pipeline, deliberately regresses actual Bastion kernel source, verifies that the check failure blocks downstream work and cannot be silently retried, then corrects the source under a fresh check and newly approved replacement mission. The completed prefix's receipt is reused. The original blocked mission remains in the journal.

Tests also cover real parent-process death, uncertain-code refusal, receipt adoption, typed-job tampering, deadlines, concurrent schema migration and readiness reporting. See `evidence/mixed-mission-tests.txt` and `evidence/mixed-mission-qualification.json`.

## Gates still open

1. **OS-enforced worker isolation.** The host refuses nested sandbox application (exit 71). No Docker, Podman or Lima executable is available. Worktrees and managed processes do not constitute hostile-code isolation.
2. **A real planner and broader build recipe.** No Codex CLI is available and no provider was connected. Current code jobs run reviewed unittest modules; they do not generate or compile an arbitrary MVP.
3. **Installed host scheduling and explicitly named chat routing.** No service is installed or left running, and other conversations are not inspected or dispatched.

The `readiness` command reports these boundaries. Even a successful synthetic sandbox probe would not certify a check-worker backend; that requires separate implementation and integration tests. No plugin/global journal was upgraded or replaced. The release is the local source candidate in this repository.
