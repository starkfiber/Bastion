# Durable progress and cancellation · 0.7.0

## Follow work without replaying the whole journal

```sh
python3 -m bastion --workspace PROJECT progress --limit 50
python3 -m bastion --workspace PROJECT progress --cursor RETURNED_CURSOR --limit 50
```

Each response contains bounded events, current state counts, a continuation cursor and `hasMore`. The cursor survives process restarts. It is bound to this journal and resolved project path; a foreign cursor, missing anchor, sequence gap or changed event is refused. Payloads above 64 KiB are represented by a digest and byte count. Pages are limited to 100 events and approximately 256 KiB of event payload. State counts describe current state, not a historical snapshot at the cursor.

The cursor is a local integrity anchor, not a credential or signed attestation. Verification covers the delta after that anchor; use `audit` for the full retained chain. Retention and compaction are not implemented by this command. MCP provides `bastion_progress` with a cursor string; use an empty string for the first page. Progress cannot launch work, approve a plan or access another chat.

## Stop an owned mission

```sh
python3 -m bastion --workspace PROJECT mission cancel MISSION_ID PLAN_DIGEST --reason "Stop this reviewed task"
```

Cancellation requires the exact plan digest and a bounded operator reason. The durable `cancel-requested` state is separate from the worker's acknowledged `cancelled` state. An active controller checks the request while supervising its child. A stopped controller can acknowledge it on the next `mission work` or `mission tick`; requesting cancellation alone does not start a service.

The controller stops its owned worker group. Nested reviewed-check cleanup relies on its existing parent-loss watchdog; hostile code that deliberately escapes process groups is outside this boundary. A running code job without a receipt remains uncertain and cannot be implicitly retried. Downstream work stays unexecuted, completed receipts remain retained, and cancellation never asserts that external effects were reversed. A terminal cancelled mission cannot be approved and resumed. An active cancellation cannot retroactively revoke independently approved jobs outside this mission.

Cancellation is a host operator control. The native RF² ABI has no cancellation action; its reconciliation action must not be misused to declare cancellation or completion. Existing native start/outcome gates remain in force for managed execution.

## WhatIF 3.2 protocol campaign

The separately developed WhatIF adapter pins this checkout's Python modules and interpreter, requires an exact source acknowledgement and plan digest, then runs fixed scenarios on owned disposable fixtures. It checks verified receipt reuse, approval refusal, digest refusal, changed-input refusal, foreign progress cursors, report tampering and cancellation before execution. A fresh process rechecks the command evidence and fixed oracles. This is seven executed CLI scenarios, not seven simulated users or a load benchmark.

The Bastion suite separately tests active code cancellation and nested-worker cleanup. No live provider, production target or competing harness was executed. Full WhatIF sandbox-dependent qualification remains limited by this host's isolation environment; see its own source checkout's qualification report.
