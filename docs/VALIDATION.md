# Validation scope

## Native-fixture review

The isolated native-fixture review passed 107 unittest cases with zero failures, errors or skips in 46.409 seconds (47.520 seconds including the parent observation). This includes the original 97 cases plus ten fixture-discovery controls. All three original native tests executed against an explicitly selected, hash-pinned RF² integration 0.3.1 executable. The original clean 0.7 source had reported three skips because it assumed an obsolete installed 0.3.0 path; no legacy path or binary alias was recreated to obtain this result.

The configured executable's SHA-256 was `3bc928a1a4057b295a1416b9ff109f39e907887a29676b841e74ef666d67777e`. Its native decisions and calculations are separate from Python's execution of tests. The new discovery controls prove an explicit missing dependency or wrong hash fails rather than silently skipping. See [native test setup](NATIVE-TESTS.md).

The historical repository-QA task and its captured performance still cover 97 cases. Updating the recipe to include the new controls does not turn that retained observation into a new 107-case task measurement. This review does not install or publish the product or qualify hosted CI and other platforms.

## Historical qualification

The local 0.5.0 development suite passed 82 unittest checks in 6.639 seconds. This is one retained test run, not a performance benchmark. Tests cover pinned inputs, approval, recovery, controller/process loss, uncertain-code refusal, tampering, typed mission integration, concurrent migration, storage rules and readiness reporting.

The retained native-backed synthetic qualification passed a mixed workflow/check pipeline; a deliberately regressed kernel failed and blocked downstream work; implicit retry was refused; a corrected check required a fresh replacement mission and approval; the completed prefix receipt was reused. The installed native executable is not distributed here.

Raw qualification journals, source worktrees, private paths and research copies remain in the local development repository and are deliberately excluded from this bundle. This page summarizes those observations; it is not an independently reproducible proof without the local inputs. Tests and qualification helpers are included so an operator can inspect and rerun their applicable checks. Native tests can skip when the separately installed executable is absent.

The [CLI walkthrough](assets/walkthrough.json) and [timing samples](assets/performance.json) are included directly. The walkthrough uses disposable state, produces sum 6 and reuses its receipt. Timing samples measure tiny pure-workflow CLI/journal work, with no inference or native backend.

A separate WhatIF local fixture returned expected status codes in 12 probes. That is neither a load test nor a security assessment. OS sandbox enforcement remains unavailable, and hosted GitHub CI has not run. Passing tests do not establish unlimited memory, hundreds of concurrent conversations or generic overnight MVP delivery.
