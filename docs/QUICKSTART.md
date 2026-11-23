# Quick start

## Requirements

Use Python 3.9 or later on a POSIX host. The code imports fcntl, resource and process-group APIs; Windows is not supported. The retained native qualification is macOS ARM64. RF² is optional for the base demo and is not bundled.

Extract the source archive, open a terminal in that directory, and run:

```sh
python3 -m bastion --help
python3 -m bastion --workspace demo plan workflow.json
```

No installation or dependency download is needed for direct source execution. An optional editable install is `python3 -m pip install -e .`; that may fetch build dependencies and should only be used if wanted.

## Inspect, approve, execute, verify

The plan response contains `run`, `digest`, and a full pinned `plan`. Inspect the files, capabilities and effects before approving. Replace the placeholders below with the actual values from your plan:

```sh
python3 -m bastion --workspace demo inspect RUN_ID
python3 -m bastion --workspace demo approve RUN_ID PLAN_DIGEST
python3 -m bastion --workspace demo run RUN_ID PLAN_DIGEST
python3 -m bastion --workspace demo verify RUN_ID
python3 -m bastion --workspace demo brain model
```

Expected final result: a verified workflow receipt whose `outputs.sum` is 6. The demo reads only its bundled brief and writes project-local state. The default `--workspace` is the current directory; choose a project explicitly to avoid mixing work.

Use `python3 tools/docs_demo.py --run` for a disposable scripted tour. The report is sanitized; its temporary journal is removed after capture. Captured IDs are examples, not reusable IDs in your project.

## Optional native engine

Review an installed RF² executable, calculate its SHA-256 and configure its exact absolute path:

```sh
python3 -m bastion --workspace PROJECT native-configure ABSOLUTE_ENGINE_PATH SHA256
```

The native engine supplies bounded decisions and checked sums. It does not add model inference, shell authority or an OS sandbox. Configuration changes require new plans. Do not copy a qualified executable path from another user's machine.

## MCP host setup

Launch the stdio server with:

```sh
/absolute/path/to/bastion/bin/bastion --workspace /absolute/path/to/project mcp
```

Configure that command in your host's supported MCP settings after reviewing the code and project scope. This guide does not write host settings. Approval, code execution, mission workers, native configuration and cache deletion remain operator-only actions.

## Common problems

| Message or condition | Action |
|---|---|
| Wrong digest or changed runtime/source | Inspect the change and create a new plan; do not weaken the identity check |
| State directory must be private | Use a project owned by your user; inspect permissions before changing anything |
| Native executable unavailable | Use the base Python demo or explicitly configure a reviewed installed engine |
| Check failed or interrupted | Inspect retained evidence; never infer success or rerun code implicitly |
| Mission blocked | Inspect the mission and job receipts; a code correction requires a fresh check and newly approved replacement |
| Readiness reports no planner or sandbox | The capability is unavailable/unqualified; a present executable alone would not certify integration |
