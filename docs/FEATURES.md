# Task Edition additions · 0.6.0 candidate

Reviewed repository QA, pinned package tests, checked HTML/Markdown exports, native execution counters and bounded receipt-backed metrics are implemented locally. See [task usage](TASKS.md). The earlier feature contracts below remain in force.

# Features and current boundaries

| Area | Implemented | Boundary |
|---|---|---|
| Graph execution | Typed dependencies and pinned approvals | Supported built-ins only |
| Knowledge | Project-scoped content-addressed ingestion | Literal retrieval, not semantic understanding |
| Brain context | Knowledge, skill metadata, experience and reviewed lessons | Bounded query graph; incomplete project view |
| Handoffs | Retained goal, context and capability inputs | No proof a model read or understood them |
| Skills | Registered metadata, content hashes, lazy guidance | Skill scripts never execute automatically |
| Cartridges | Versioned pure templates and fixture qualification | Authored examples are not universal correctness |
| Code checks | Explicit source/interpreter pins, unittest results, logs | Reviewed trusted code; host permissions remain |
| Missions | Typed workflow/check sequencing, deadlines and budgets | Up to 100 jobs; no arbitrary chat orchestration |
| Recovery | Receipt reuse and bounded workflow recovery | Uncertain code never retries implicitly |
| Corrections | New draft mission and new approval | Original deadline/wall cutoff retained |
| Native RF² | Pinned checked sum and decision gate | Not model inference; optional separate executable |
| Cache | Rebuildable content deduplication, TTL and quota | Unique memory/receipts are not auto-deleted |
| Readiness | Synthetic local boundary probe and tool presence | Availability is not backend qualification |
| MCP | 23 planning/inspection/bounded workflow tools | No model-facing approval or code-run tool |

## Still open

OS-enforced worker isolation, live planner integration, general build recipes, installed persistent scheduling, explicit named-chat routing, evaluated semantic retrieval and compaction. The candidate does not run your Mac or every chat, guarantee infinite memory, establish AGI, or promise any arbitrary MVP by morning.

## Evidence levels

Retained local 0.5 tests: 82 passed. Native-backed synthetic mixed-mission qualification exercised success, deliberate regression, downstream blocking, refusal of implicit retry and approved correction. Controlled process-death tests are not physical power-loss qualification. Twelve WhatIF status/header probes are not browser, capacity or security qualification. CI configuration is prepared but hosted execution is pending.
