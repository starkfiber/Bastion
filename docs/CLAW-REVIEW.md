# Source-guided Claw review · 24 November 2026

This is a scoped design review using primary project documentation, not a comparative execution benchmark. No rival harness was installed, executed, subjected to load or declared inferior. Original implementation decisions are kept separate from source descriptions.

| Project / inspected source | What its documentation describes | Bastion decision | Scope boundary |
|---|---|---|---|
| [OpenClaw session tools](https://github.com/openclaw/openclaw/blob/main/docs/concepts/session-tool.md), “Session state changes” | Versioned durable session signals, delta reads and explicit missing-history information | Implement project-bound progress cursors and bounded event pages | Bastion does not implement OpenClaw's live channel routing, model loop or watcher delivery |
| [DeepClaw README](https://github.com/akira/deepclaw), “Memory”, “Skills”, “Cron Scheduler” | File-based persistent context, lazy skills and scheduled prompts delivered through Telegram | Preserve project knowledge and explicit approvals; retain the existing manually invoked mission scheduler boundary | Native cron installation, Telegram and live-provider execution are not added here |
| [Harnessclaw README](https://github.com/harnessclaw/harnessclaw), “Features” and archive banner | Desktop management of agents, skills and session history; repository is archived | Keep the report view tied to observed receipts and expose compact progress data | No claim to replace its desktop application or reproduce all its behavior |
| “Rabbitclaw” | The requested name was not uniquely resolved to an authoritative project | Exclude it from product-specific conclusions | Rabbit's OpenClaw integration is a different identifiable reference; no equivalence is assumed |

The search included the named Claw variants and durable agent/session design. The sources establish documented features, not independent runtime behavior, performance, security or universal superiority. Reusable patterns were synthesized; upstream source code was not copied into Bastion.

The investigation's private ThesisPro notebook records the problem, method, source ledger, rejected superiority claim and limitations through a real local MCP session. It is an engineering notebook with an incomplete provisional word budget, not a completed degree thesis or independent peer review. It is excluded from the public source bundle.

## Decisive checks

The current local Bastion suite passed 97 tests, including real active cancellation, blocked downstream work, cursor restart/pagination and foreign/tampered cursors. A native-gated QA task also passed all 97 tests. WhatIF executed seven fixed CLI scenarios across 25 command calls and a fresh verifier rechecked the retained observations. These checks support those local contracts. An OpenClaw/DeepClaw benchmark with identical tasks, models, budgets and environments is still required before any ranking.
