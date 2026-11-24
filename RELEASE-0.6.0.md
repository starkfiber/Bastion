# 0.6.0 Task Edition · local candidate

Repository QA becomes an end-to-end task: explicit recipe, pinned package modules, exact approval, managed execution, failure-aware CLI status, receipt reuse and checked report export. Static HTML reports expose observed outcomes, native call counts and provenance without external assets. Read-only metrics distinguish journal totals from a bounded, reverified sample.

RF² responses are now streamed with a 4 KiB stdout and 8 KiB combined output contract instead of buffering arbitrary output first. Native invocation, output-byte and elapsed-time counters feed execution receipts. Configuration and approval calls are outside that execution sample.

Running the full suite inside an RF²-gated task exposed concurrent SQLite journal initialization and a globally patched test clock racing the watchdog. Initialization now serializes journal-mode/schema setup through a private, process-released file lock with a finite wait. The laboratory clock is imported independently so its test does not replace the watchdog's clock. The first failed receipts remain retained; corrections use fresh tasks and approval.

This candidate remains trusted local Python execution with host permissions. It does not implement arbitrary goal planning, generic compilation, hostile-code isolation, unattended deployment or cross-chat dispatch. No installed RF² plugin or live GitHub workflow was changed. See [task usage](docs/TASKS.md) and the retained qualification summary in docs/assets for measured results.
