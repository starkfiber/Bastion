> This detailed guide describes the 0.5 contracts inherited by the local 0.6 candidate. For repository tasks, package test modules, report export and observed metrics, use [Task Edition](TASKS.md).

# BASTION Mixed Mission Edition — local 0.5.0 candidate

A working local prototype for the BASTION vision: models propose work; a persistent harness retains the graph, approved capabilities, project knowledge, skill identities, receipts and reviewed lessons.

Run with Python 3.9+ on macOS or Linux. No runtime dependencies or provider accounts are required. Linux is not yet qualified by the retained test evidence. The project is a candidate source implementation; it has not replaced the installed RF² plugin.

## Quick start

From this directory:

```sh
python3 -m bastion --workspace demo plan workflow.json
```

Inspect the full returned plan. Substitute its run ID and digest below:

```sh
python3 -m bastion --workspace demo inspect RUN
python3 -m bastion --workspace demo approve RUN DIGEST
python3 -m bastion --workspace demo run RUN DIGEST
python3 -m bastion --workspace demo verify RUN
python3 -m bastion --workspace demo map RUN
python3 -m bastion --workspace demo knowledge model
```

`python3 bin/bastion` provides the same commands directly from this checkout. State stays in the selected workspace's private `.bastion/` directory. Keep workspaces separate across projects.

The demo imports its brief, recalls project knowledge, calculates a bounded sum through a dependency graph, asserts the answer and fingerprints the recalled evidence. It does not call a model or external service.

## What works

- A validated directed work graph with dependencies and data references.
- Exact digest approval, pinned runtime/input/skill identities and bounded built-in capabilities.
- SQLite task results, hash-linked events, explicit interrupted-run recovery and repeat receipt reuse.
- Content-addressed project knowledge, recorded provenance and deterministic scoped search.
- Operator registration of a bounded SKILL.md metadata subset, lazy instruction loading and stale-content refusal. No skill scripts are automatically executed.
- Provider-neutral workflow proposals, including OpenAI-shaped and Anthropic-shaped tool-call fixtures. These are format adapters, not live API integrations.
- Experience records with evidence quality; lessons require explicit review and verified workflow evidence. Simulation volume cannot promote a lesson or modify policy.
- A streaming synthetic policy/calculation laboratory, retained per-trial binary evidence, fresh-process verification and exact case replay.
- Twenty-three MCP tools with input/output schemas. Approval, code execution, worker launch, native configuration, cache deletion, cartridge qualification/activation and lesson review stay outside MCP.

## Check Edition 0.4.0

This release adds operator-approved **reviewed, trusted Python unittest jobs**. It pins explicit source files, interpreter, runtime and optional RF² engine; copies the selected files into a private worktree; and retains test outcomes, logs and receipt hashes. Empty or skipped-only suites, changed declared source, test failures and exhausted time/output budgets cannot pass. Configured RF² gates mediate approval, start and completion.

This is **not an OS sandbox**. A real nested `sandbox-exec` probe failed with `sandbox_apply: Operation not permitted` (exit 71). The worker inherits host permissions; filesystem/network effects outside the copied worktree are not controlled. Only reviewed and authorized code belongs here. Process-group cleanup assumes code does not deliberately escape the group. CPU limits apply per process; state-byte monitoring is not an OS quota. Check snapshots and logs are retained rather than automatically deleted.

A manifest contains `name`, `files` (1..100 explicit relative paths), `testModules` (1..20 pinned top-level module names), `minTests` (at least one), `trust` set to `reviewed-local-code; not-os-sandboxed`, and `budgets` with `wallSeconds`, `cpuSeconds`, `outputBytes` and `stateBytes`. There is no shell-command field or dependency installer.

```sh
python3 -m bastion --workspace PROJECT check plan check.json
python3 -m bastion --workspace PROJECT check inspect CHECK_ID
python3 -m bastion --workspace PROJECT check approve CHECK_ID DIGEST
python3 -m bastion --workspace PROJECT check run CHECK_ID DIGEST
python3 -m bastion --workspace PROJECT check verify CHECK_ID
```

Inspect `passed`, not merely CLI exit status or `integrityVerified`: a completed **failed** job also has a valid receipt. Repeating execution returns the retained outcome. Interrupted code checks require investigation and a newly approved plan; no implicit code-job retry occurs. In 0.5, typed missions may include checks, but workflow auto-recovery never applies to code jobs.

MCP exposes check plan, inspect and verify only. `tools/qualify_checks.py` reproduces qualification against actual Bastion kernel source and a deliberately regressed copy. See [validation summary](VALIDATION.md) and [remaining gates](../RELEASE-0.4.0.md).
- A bounded project brain graph: knowledge excerpts, hash-checked skill metadata, experience quality and reverified reviewed lessons in one provider-neutral context package.

## Project brain and model continuity

```sh
python3 -m bastion --workspace demo brain model
```

`brain QUERY` (or MCP `bastion_context` with `query`) returns a `bastion.context.v1` JSON graph with typed nodes, relationships, exclusions and a deterministic package digest. Any planner can consume this same format. Knowledge and experience summaries use literal substring search; skills match names/descriptions and lessons match reviewed text. Each collection returns at most 20 matches; knowledge excerpts are capped at 2,000 characters. This is a query-specific context graph, not a complete project map or semantic search engine.

Knowledge content hashes and skill pins are checked before inclusion. Reviewed lessons are included only after their local workflow receipts reverify; missing or invalid evidence excludes the lesson. Proposed lessons are omitted. Synthetic experiences retain their recorded quality and are marked unverified here. The package grants no execution permission, loads no skill scripts and makes no model calls. Receipt verification can restore a missing content-addressed experience record using the existing verifier.

The package survives model changes because it comes from project storage. Live provider handoff and model performance remain unqualified. Existing approvals pin runtime source: after a code update, create and approve a new plan rather than attempting to run an old approval.

## Retained planner handoffs

```sh
python3 -m bastion --workspace demo handoff "Read the brief and verify the bounded calculation" --query model
```

The returned `handoff` digest identifies retained inputs: goal, project brain context, runtime identity, capabilities and proposal format. Give the `package` to a planner of your choice. No provider is contacted by this command. Treat knowledge excerpts and experience text as data; skill and lesson text is guidance, never execution authority.

Save a planner's workflow or supported tool-call response as a JSON file inside the selected workspace, then substitute the returned handoff digest and proposal filename:

```sh
python3 -m bastion --workspace demo handoff-inspect HANDOFF_DIGEST
python3 -m bastion --workspace demo handoff-propose HANDOFF_DIGEST proposal.json --provider external --model chosen-model
```

The existing `demo/workflow.json` is also a valid fixture for this path; it does not require a model. Submission rechecks the retained context and runtime, normalizes the proposal and creates a **draft** plan. Inspect that plan and use the existing exact-digest approval/run/verify commands. Provider labels record provenance and cannot approve work. The handoff records which inputs were supplied for a proposal; it cannot prove a planner actually used them or that the proposal satisfies the goal.

MCP exposes the same operations as `bastion_handoff`, `bastion_handoff_inspect` and `bastion_handoff_propose`. A handoff can be reused across provider sessions within its original project while the selected context and runtime remain current. Changes require a new handoff; copying it into another project does not authorize reuse. Inspection lists associated proposal IDs and their current run states. Matching knowledge, skills, experiences or reviewed lessons changing can invalidate a handoff; unrelated project records are outside its query-specific snapshot.

## Enhanced cartridges

Twenty upstream skill approaches were compared with the foundation. The resulting original cartridge layer packages **existing pure built-ins plus the new `data.select_fields` capability** as typed, versioned workflows. The three examples are checked-sum, canonical-fingerprint and record-projector. This is reusable local execution, not twenty newly installed skills or live integrations.

```sh
python3 -m bastion --workspace demo cartridge register cartridges/checked-sum.json
python3 -m bastion --workspace demo cartridge qualify CARTRIDGE_DIGEST
python3 -m bastion --workspace demo cartridge activate CARTRIDGE_DIGEST QUALIFICATION_DIGEST
python3 -m bastion --workspace demo cartridge propose checked-sum cartridges/checked-sum-inputs.json
```

Inspect the returned draft and use the existing exact-digest approve, run and verify commands. Registration, qualification and activation are separate from execution approval. `cartridge list`, `cartridge inspect DIGEST` and `cartridge compare BASELINE CANDIDATE` expose package state and paired replay.

Manifests declare exact inputs, capabilities, workflow templates, supporting assets, output/node budgets and at least two successful plus two rejection fixtures. Versions are immutable. Asset hashes are checked before use and pinned into execution plans. Changes require new package versions. Qualification executes the actual pure handlers against authored expected outcomes, verifies results and retains per-case evidence bound to runtime identity. Activation replays those cases; replacing an active version additionally replays the baseline's retained expectations against the candidate. Rewriting the candidate's own tests cannot remove that baseline gate.

The runtime rejects graph-reference markers inside cartridge inputs, ambiguous field declarations, zero/boolean budgets, duplicate fixtures and unsupported effects. It checks output bytes in preflight, execution and receipt verification. These are local data bounds, not provider-spend, process-memory or wall-time caps. Qualification is limited to the authored examples; it is not proof that an arbitrary goal is satisfied. No shell, network or browser cartridge is supported.

The local research archive contains the earlier 20-approach comparison and source inventory; it is excluded from this publication bundle. See the [validation summary](VALIDATION.md) for the scope of the retained local checks. Historical foundation evidence and source manifests describe the earlier candidate; runtime updates require new qualifications and execution approvals.

## The model boundary

Any host can submit the `bastion.workflow.v1` JSON contract. Model/provider labels are provenance, never permission. `propose FILE --provider NAME --model NAME` normalizes supported tool-call shapes. A model switch preserves stored knowledge and execution history because those belong to BASTION's workspace, not a model session.

This does not make all models equally capable. Planning quality and task success still depend on the model, task and tools. The current tests prove proposal-format compatibility, not equivalent performance across live models.

## Native RF² and durable missions

### Mixed missions in 0.5.0

Use `jobs` instead of legacy `runs` to declare typed jobs. Both workflow and check IDs occupy the `run` field; `kind` determines the handler. Every reference is bound to its exact digest:

```json
{
  "goal": "Process project data, run reviewed tests, then perform a final local check",
  "jobs": [
    {"kind": "workflow", "run": "WORKFLOW_ID", "digest": "WORKFLOW_DIGEST"},
    {"kind": "check", "run": "CHECK_ID", "digest": "CHECK_DIGEST"}
  ],
  "notBefore": 0,
  "deadline": 0,
  "budgets": {
    "maxJobs": 10, "maxAttempts": 2, "maxWallSeconds": 300,
    "maxOutputBytes": 65536, "maxStateBytes": 67108864
  }
}
```

Replace `deadline: 0` with an explicit future Unix timestamp within 24 hours. The ordinary mission plan/inspect/approve/work/tick commands apply. Mixed plans include effect disclosures, code manifests and source hashes for review and are bounded to 1 MiB. A check passes its own operator approval/start/finish gates and must have a valid **passing** receipt before downstream jobs can execute.

Workflow jobs keep bounded idempotent recovery. Failed or interrupted checks block the mission and are never retried implicitly. If a check committed its passing receipt before the mission controller died, the next controller adopts that verified receipt without rerunning code. Otherwise an operator must investigate the uncertain outcome and prepare a fresh check plan.

```sh
python3 -m bastion --workspace PROJECT mission replace-check MISSION_ID DIGEST POSITION NEW_CHECK_ID NEW_CHECK_DIGEST --reason "Reviewed outcome and correction"
```

Positions are zero-based. Replacement produces a new **draft** mission with explicit provenance; it requires new approval. The previous mission and evidence remain blocked and retained. Original deadline and absolute wall-budget cutoff cannot be extended by waiting to approve a replacement. The operator's reason is a record, not proof that external effects were reconciled. Unchanged completed-prefix receipts are reused.

`python3 -m bastion --workspace PROJECT readiness` reports local host-tool availability and runs a disposable OS-boundary probe against synthetic files and a loopback listener. It neither contacts providers nor installs anything. Probe availability/success is separate from an isolated check-worker backend. On this host the nested sandbox probe remains refused, and no Docker/Podman/Lima or Codex CLI is available.

Schema migration adds a `kind` column with `workflow` as the legacy default, serializes concurrent startup, and preserves existing job records. Runtime identity changes still require fresh execution plans after upgrade. See [0.5.0 release scope](../RELEASE-0.5.0.md) and [native-backed validation summary](VALIDATION.md).

The local 0.3.0 candidate can use the installed RF² executable for checked sums and an additional native transition gate. Configure an exact reviewed executable and its SHA-256 in a chosen project:

```sh
python3 -m bastion --workspace PROJECT native-configure ABSOLUTE_ENGINE_PATH SHA256
```

The engine identity is pinned into plans. The Python host retains filesystem checks, approval, storage, scheduling and independent result verification. RF² is a bounded decision/calculation engine; it does not supply a model or desktop permissions. The installed RF² plugin and protected journal are not modified by candidate configuration.

A mission references existing draft/approved workflow IDs and exact digests. Its JSON specification contains `goal`, `runs`, `notBefore`, `deadline` and `budgets`. Times are finite Unix seconds; deadlines must be within 24 hours. Budgets explicitly bound job count (up to 100), attempts (up to three per job), elapsed wall time, captured output and observed project state bytes. The workflow-only example below shows the mission specification. Raw retained evidence remains in the local development repository and is excluded from the publication bundle.

```sh
python3 -m bastion --workspace PROJECT mission plan mission.json
python3 -m bastion --workspace PROJECT mission inspect MISSION_ID
python3 -m bastion --workspace PROJECT mission approve MISSION_ID DIGEST
python3 -m bastion --workspace PROJECT mission work MISSION_ID DIGEST
python3 -m bastion --workspace PROJECT mission due
python3 -m bastion --workspace PROJECT mission tick --limit 1
```

One explicit mission approval covers the exact bounded local workflows and their idempotent recovery. Approval does not authorize a model to substitute new jobs. Each worker runs in its own process group with a parent-loss/deadline watchdog. Kernel locks exclude active duplicate workers. Retrying revalidates source/plan identity and retained task evidence; completed jobs reuse receipts. The first-start wall budget persists across restarts. A failed or exhausted mission stays visibly blocked. `tick` processes due approved/running missions only, prioritizing earlier deadlines; it never approves work or installs a service.

The LaunchAgent example in `deploy/local.bastion.missions.example.plist` is **not installed**. It references the retained synthetic qualification workspace and is for review, not production use. No scheduler is running after qualification. A deployed scheduler needs an explicitly selected real project and host installation. `notBefore` is a due-time condition, not a wake timer. Arbitrary cron expressions, missed-occurrence catch-up, generic code generation, Mac app control and host-chat dispatch are not implemented.

## Storage and memory controls

Mission workers observe state usage and stop on budget exhaustion. This is a polling guard, not a filesystem quota: writes can temporarily exceed the threshold. No host-wide RAM, disk or provider-spend guarantee is claimed. Native start gates also enforce the configured free-space floor. Knowledge, lessons and unique receipts remain project-owned and are not deleted automatically.

An explicit rebuildable cache supports content deduplication, TTL and a default 16 MiB quota. It never executes cached contents. Pruning requires the digest of a fresh inspected plan, rechecks hashes and expiry metadata, and touches registered expired cache objects only:

```sh
python3 -m bastion --workspace PROJECT cache stash rebuildable.txt --ttl 3600
python3 -m bastion --workspace PROJECT cache prune-plan
python3 -m bastion --workspace PROJECT cache prune PRUNE_DIGEST
```

Refresh invalidates an old prune plan. Unregistered files, original project inputs, knowledge, experience and receipt journals are preserved. This prevents cache housekeeping from silently discarding unique evidence; it does not promise infinite memory or zero storage growth.

The local 65-repository study is excluded from this publication bundle. See the [validation summary](VALIDATION.md) for mission test scope. This edition implements the local reliability foundation for bounded unattended work. It cannot yet take an arbitrary chat request and autonomously produce an MVP by morning. Live planning, reviewed build execution, authenticated host scheduling and explicit cross-chat routing remain separate gates.

## Experience laboratory

```sh
python3 -m bastion --workspace demo lab run --trials 2000000 --seed 20261123 --max-seconds 120
python3 -m bastion --workspace demo lab verify CAMPAIGN
python3 -m bastion --workspace demo lab replay CAMPAIGN 123456
```

Every iteration evaluates the real Python policy kernel against a separately written truth-table oracle and the real bounded calculation handler against reference fixtures. All records are streamed to disk; full campaign data is not accumulated in RAM. Each row retains actual and expected outcomes, the policy combination and fixture identity. The verifier reconstructs expected fixtures and checks every retained row, file digest and aggregate count. Replay executes one exact case again.

The policy domain contains **1,152 combinations** of state, action and five flags. Eight arithmetic fixture families cover normal sums, overflow, booleans, negatives, oversized arrays, maximum values, empty arrays and oversized integers. Millions of iterations are repeated/varied trials within this finite domain. They are not millions of distinct capabilities, application journeys, human users, model-generated lessons or real-world experiences.

Budget exhaustion and interruption leave incomplete evidence. Used campaign directories are never silently restarted. The laboratory is an original local deterministic engine inspired by scenario testing. The connected WhatIF plugin did not return usable inspection results during this work; no WhatIF-provider execution or qualification is claimed.

## MCP

Launch a dedicated process for a chosen project:

```sh
/absolute/path/to/bastion-os/bin/bastion --workspace /absolute/path/to/project mcp
```

Configure this command in the host only after reviewing the code and selecting the project. No host configuration or installed plugin has been changed automatically. MCP currently uses a bounded synchronous stdio implementation. Arbitrary shell, network, browser, device and external-account capabilities are unsupported.

## Recovery and learning

After an interrupted worker exits:

```sh
python3 -m bastion --workspace demo recover RUN DIGEST
python3 -m bastion --workspace demo run RUN DIGEST
```

A per-run kernel file lock prevents recovery while this runtime still owns an active worker. Completed nodes are retained after interruption. Failed verification resets all tasks on explicit retry, because the invalid result may belong to a completed task. All supported write effects are content-addressed local ingestions; no external exactly-once guarantee is asserted.

Search experience records with `experience QUERY`. `lesson-propose EXPERIENCE_ID TEXT` creates a proposed lesson; `lesson-review LESSON_ID` checks its workflow receipt again and marks it reviewed for this project. Reviewed text remains guidance, never executable policy or proof of generalization.

## Trust and proof limits

This prototype is not a kernel, hypervisor, general application runner or hostile-code sandbox. The workflow runtime executes reviewed built-ins and refuses unknown capabilities. The separate operator-approved check path executes reviewed trusted Python code without OS isolation. Private files, hashes, exact approvals and event chains protect the intended local workflow; a hostile process with equivalent user privileges can still modify code and state. Adversarial isolation requires a separately protected execution service and OS-enforced workers.

The candidate can run a pinned native RF² gate and checked sum when configured. Eight host-allowed transitions and retained native-backed missions were checked; exhaustive parity and OS-enforced isolation remain open gates. The installed RF² 0.3.0 plugin, its journal and its pinned Cartridges were left unchanged. There are no live model calls, agent fleet, external MCP connections, production deployments, browser sessions or self-modifying skills.

Before expanding execution, add a reviewed capability contract with input/output limits, effects, authorization, identity pins, cancellation, verification and recovery semantics. A SKILL.md instruction is never sufficient to enable a new capability.

## Acceptance checks

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Tests cover real process death, partial ingestion, stale pins, faulty workers, false recall results, tampering, provider-shaped proposals, stdio MCP, active-worker recovery refusal, simulation provenance and interrupted laboratory budgets. See [validation](VALIDATION.md) for scope and [release gates](../RELEASE-0.5.0.md) for limitations.
