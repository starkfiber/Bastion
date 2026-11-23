# 0.7.0 Control Edition · source candidate

Adds bounded, project-bound progress cursors and durable cooperative mission cancellation. Progress survives process restarts, refuses foreign/missing anchors and checks the returned event segment. Cancellation is recorded before worker acknowledgement; interrupted reviewed code remains uncertain and is never implicitly retried. Downstream jobs stay unexecuted. No RF² reconciliation action is repurposed as a stop action.

The seven WhatIF 3.2 harness scenarios now exercise actual CLI contracts on owned fixtures. The separate 97-test suite includes active cancellation and nested check watchdog cleanup. Raw private journals and the ThesisPro notebook are retained locally and excluded from publication.

This release incorporates the previously local 0.6 Task Edition: reviewed repository QA, static reports, observed native/usage metrics, bounded native response capture and serialized SQLite initialization. See [0.6 changes](RELEASE-0.6.0.md), [control usage](docs/CONTROL.md) and [Claw review](docs/CLAW-REVIEW.md).

Live model planning, general-purpose code generation, installed scheduling, hostile-code OS isolation and cross-chat dispatch remain open. No comparison establishes that Bastion is more powerful than another harness. Source publication is separate from upgrading the installed plugin or executing hosted CI.
