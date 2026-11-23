# Repository tasks and observed metrics · 0.6.0 candidate

The `python-unittest` task recipe runs reviewed repository tests in pinned worktrees, produces a verified result and exports an HTML or Markdown report. It uses the existing check journal and approval contract; it is not a new sandbox, model planner or generic build runner.

## Inspect the recipe

`demo/repository-qa.json` names every source file, explicit package initializer, test module, minimum test count and resource budget. Dotted test modules now require their package initializers to be pinned, preventing accidental namespace resolution to an unrelated installed package. Review the files and trust declaration before authorizing execution.

From this source checkout:

```sh
python3 -m bastion task plan demo/repository-qa.json
python3 -m bastion task inspect TASK_ID
python3 -m bastion task approve TASK_ID PLAN_DIGEST
python3 -m bastion task run TASK_ID PLAN_DIGEST
python3 -m bastion task report TASK_ID --format markdown
python3 -m bastion metrics --limit 100
```

The selected workspace is the current project unless `--workspace PROJECT` is supplied before the command. No package installation or network call occurs. Source files, interpreter, runtime and configured native executable remain pinned. Failed task execution returns CLI status 1 and a valid failure receipt, while report/verification can still succeed. A receipt proves a recorded outcome, not a passing outcome.

## Export a deliverable

Choose an existing visible directory in that same workspace. Use the returned **receipt digest**, not the plan digest:

```sh
python3 -m bastion task export TASK_ID RECEIPT_DIGEST report.html --format html
python3 -m bastion task export TASK_ID RECEIPT_DIGEST report.md
```

Export refuses existing files, hidden/internal-state paths, path traversal and symlink parents. It records the output SHA-256. It writes a static report with escaped content and no external requests. Keep unique receipts and reports outside disposable cache. A repeated run returns the existing receipt rather than re-executing code, and adds a reuse event.

## Run this repository's reviewed QA recipe

```sh
python3 tools/run_repository_task.py --run --workspace dist/my-reviewed-qa
```

`--run` explicitly approves only the included specification. The helper first copies its declared files into a new private workspace, plans and approves the exact digest, executes, verifies receipt reuse, and exports `report.html`, `report.md`, `report.json`, `metrics.json` and `timing.json`. It refuses an existing workspace. On failure it keeps the failure report and exits 1. It never retries uncertain code or publishes.

For native start/outcome gates, additionally supply a separately reviewed executable and its SHA-256 using `--native-engine ABSOLUTE_PATH --native-sha256 SHA256`. The binary is not bundled. The task's native metric counts the two execution gates; configuration and approval occur outside that metric, and child tests may perform their own native calls.

## Read the metrics accurately

State counts cover the project journal. Receipt outcomes, observed tests and latency statistics cover only the newest requested sample, at most 100 receipts; each is reverified before it is counted. Receipt reuse and report export counts come from durable events. Missing legacy timing is unknown, not zero. Native durations include process startup. No token spend, inference speed, throughput, OS isolation or concurrent-chat capacity is measured. Event-chain verification still scales linearly with retained history.

MCP exposes `bastion_metrics` and `bastion_task_report` as read-only tools. Approval, test execution and file export remain operator CLI operations. No installed plugin or scheduler is modified.

## GitHub integration

The prepared `repository-task.yml` workflow is manually triggered, has `contents: read`, and uses an explicit Python matrix. It runs the bundled recipe and retains only named reports as artifacts for seven days, even when tests fail. It does not upload the private journal or source snapshots. Hosted runs cannot verify those receipts independently without the original retained journal; the downloaded reports are observations, not standalone cryptographic attestations. Native qualification is separate from a Linux job where the installed Mac binary is absent.

The workflow is local and has not run on GitHub. Its action syntax follows the official [setup-python](https://github.com/actions/setup-python) and [upload-artifact](https://github.com/actions/upload-artifact) documentation.
