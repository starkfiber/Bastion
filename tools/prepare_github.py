"""Prepare a local curated GitHub tree. Never commits, connects, pushes or publishes."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bastion.mcp import listing
from bastion.core import CAPABILITIES


def write(name,text):
    path=ROOT/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text.rstrip()+'\n')


def docs():
    perf=json.loads((ROOT/'docs/assets/performance.json').read_text())
    tour=json.loads((ROOT/'docs/assets/walkthrough.json').read_text())
    metrics=perf['metrics']
    timing_rows=[('Plan → approve → run → verify','four_process_workflow_cycle'),('Reuse verified receipt','verified_receipt_reuse'),('Brain query, no knowledge match','brain_context_query')]
    table='\n'.join('| '+label+' | '+f"{metrics[key]['medianMs']:.2f} ms"+' |' for label,key in timing_rows)
    write('README.md','''# BASTION

**Persistent work. Explicit authority. Evidence you can check.**

![Bastion concept illustration](docs/assets/hero.png)

*Concept illustration, not a product screenshot. Bastion currently operates through a CLI and MCP.*

Bastion is a project-owned AI harness that carries knowledge, skills, plans and receipts across model sessions. Models propose work; the harness controls approved execution and retains what actually happened.

**0.5.0 · Mixed Mission Edition · local candidate**

## Start in one minute

Requires Python 3.9+ and a POSIX host. The standard-library workflow demo needs no provider account, API key or RF² binary. Native-backed qualification was performed on macOS ARM64; Linux remains unqualified until CI runs.

From an extracted checkout:

```sh
python3 -m bastion --workspace demo plan workflow.json
```

Read the returned plan, then substitute its exact run ID and digest:

```sh
python3 -m bastion --workspace demo inspect RUN_ID
python3 -m bastion --workspace demo approve RUN_ID PLAN_DIGEST
python3 -m bastion --workspace demo run RUN_ID PLAN_DIGEST
python3 -m bastion --workspace demo verify RUN_ID
```

The bundled demo ingests its own brief, recalls project knowledge, checks `1 + 2 + 3 = 6`, and records a verified receipt. It makes no model call. Repeating a finished run reuses that receipt.

For a fully scripted synthetic walkthrough:

```sh
python3 tools/docs_demo.py --run
```

That flag approves only the bundled disposable demo. It is not permission to execute arbitrary project code.

## What you get

| Feature | Current behavior |
|---|---|
| Project brain | Hash-checked knowledge, skill metadata, experience and reviewed lessons |
| Model continuity | Retained provider-neutral planner handoffs; supported provider-shaped proposal formats |
| Work graphs | Typed dependencies, exact plan approval and independently checked outputs |
| Cartridges | Immutable pure-workflow templates with qualification and baseline regression gates |
| Reviewed code checks | Pinned Python unittest jobs in separate worktrees with explicit operator approval |
| Mixed missions | Sequence workflows and checks; failed code blocks downstream work |
| Recovery | Reuse committed receipts; recover bounded workflows; never silently retry uncertain code |
| RF² | Optional pinned native checked-sum and decision gates; Python retains host authority |
| Storage controls | Observed state budgets and quota/TTL cleanup for explicitly rebuildable cache |
| MCP | 23 model-facing planning, inspection and bounded workflow tools |

![Exact workflow and failure path](docs/assets/workflow.svg)

## A walkthrough you can inspect

![Rendered actual CLI transcript](docs/assets/walkthrough.svg)

This is a rendering of an actual synthetic CLI capture with workspace paths redacted. It is not a graphical application screenshot. [Read the walkthrough](docs/WALKTHROUGH.md) or inspect the [captured JSON](docs/assets/walkthrough.json).

## Measured local speed

| Operation | Median of 15 local samples |
|---|---:|
'''+table+'''

Measured on macOS ARM64, Python 3.9.6. These include CLI process startup and local journal work on tiny fixtures; no native engine or model was configured for this timing run. They do not establish AI inference speed, throughput, production capacity or an advantage over another harness. [Method, ranges and raw samples](docs/PERFORMANCE.md).

## Proof and limits

- The retained local 0.5 suite passed **82 tests**, including process loss, recovery, tampering, typed mission checks and concurrent migration.
- A native-backed mixed pipeline passed, blocked a deliberately regressed kernel, refused implicit retry, and required fresh approval for correction.
- A separate WhatIF fixture returned expected statuses for 12 loopback probes; this established neither capacity nor security.

Reviewed code checks **are not OS-sandboxed** and retain host permissions. The host refused nested sandbox application. No live planner, generic MVP builder, installed scheduler or other-chat dispatcher is implemented. The installed RF² plugin was not upgraded by this source candidate.

The long-term goal is reliable bounded overnight work. Arbitrary MVP-by-morning delivery, infinite memory and AGI are not current capabilities.

## Documentation

- [Browser overview](docs/index.html) · [Validation scope](docs/VALIDATION.md)
- [Quick start and installation](docs/QUICKSTART.md)
- [Guided walkthrough](docs/WALKTHROUGH.md)
- [Features and boundaries](docs/FEATURES.md)
- [CLI, capabilities and MCP functions](docs/FUNCTIONS.md)
- [Measured speed](docs/PERFORMANCE.md)
- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Architecture](architecture.md) · [0.5 release notes](RELEASE-0.5.0.md)
- [Contributing](CONTRIBUTING.md) · [Security boundaries](SECURITY.md)

## Local page preview

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open http://127.0.0.1:8000 . This serves the prepared overview locally; it does not publish a site.

## Development

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Native-engine checks are conditional on a separately installed local RF² executable. Prepared GitHub Actions configuration is not a claim that hosted CI has run. Licensed under [MIT](LICENSE); see [NOTICE](NOTICE.md) for bundled-material boundaries.
''')
    write('docs/QUICKSTART.md','''# Quick start

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
python3 /absolute/path/to/bastion/bin/bastion --workspace /absolute/path/to/project mcp
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
''')
    write('docs/WALKTHROUGH.md','''# Walkthrough

The illustrated capture uses the bundled six-node workflow. It is actual CLI output rendered as a terminal graphic, with workspace paths redacted. No model, browser or native engine is used in this demo.

![Actual synthetic CLI capture](assets/walkthrough.svg)

1. **Plan.** Validate a dependency graph and pin runtime, inputs and registered skills. Nothing executes yet.
2. **Inspect.** Review the exact effects and hash. A provider label is provenance, not permission.
3. **Approve.** Authorize that exact plan digest through the operator CLI.
4. **Run.** Execute supported handlers and retain task evidence.
5. **Verify.** Recheck outputs, receipt and event integrity. The demo's sum is 6.
6. **Repeat.** Reuse the completed receipt rather than executing the finished work again.
7. **Recall.** Query the project brain without making its text executable authority.

## Mixed missions

A 0.5 mission's `jobs` array references exact digests with `kind: workflow` or `kind: check`. Both use the common `run` field for their identifier. The plan exposes code source pins, budgets and the absence of OS isolation.

```mermaid
flowchart TD
  A["Reviewed mission"] --> B["Exact batch approval"]
  B --> C["Workflow prefix"]
  C --> D["Reviewed code check"]
  D -->|"Passing receipt"| E["Downstream work"]
  D -->|"Failure or unknown outcome"| F["Blocked mission"]
  F --> G["Operator investigation"]
  G --> H["Fresh check and draft mission"]
  H --> B
```

Failed checks block downstream work. A passing receipt committed before controller loss can be adopted without rerunning code. Without that receipt, an interrupted check requires investigation. A replacement is a new draft, requires new approval and cannot extend the original deadline/wall cutoff. The operator's reason does not prove external reconciliation.

```sh
python3 -m bastion --workspace PROJECT mission plan mission.json
python3 -m bastion --workspace PROJECT mission inspect MISSION_ID
python3 -m bastion --workspace PROJECT mission approve MISSION_ID DIGEST
python3 -m bastion --workspace PROJECT mission work MISSION_ID DIGEST
```

See the operator guide for the full JSON schema example and `mission replace-check` syntax. No scheduler or host-chat dispatcher is installed by these commands.

## What the images mean

The cover is generated concept artwork. The workflow graphic is an exact authored diagram. The terminal graphic is rendered from captured CLI results. None is presented as a native application UI screenshot.
''')
    write('docs/FEATURES.md','''# Features and current boundaries

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
''')
    write('docs/PERFORMANCE.md','''# Measured local speed

These results describe this machine and tiny synthetic fixtures. They are not model-inference, autonomous-MVP, concurrency, production-capacity or competitor benchmarks.

| Operation | Median | Minimum | Maximum |
|---|---:|---:|---:|
'''+ '\n'.join('| '+label+' | '+f"{metrics[key]['medianMs']:.2f} ms | {metrics[key]['minMs']:.2f} ms | {metrics[key]['maxMs']:.2f} ms |" for label,key in timing_rows)+'''

## Method

15 samples per operation, one unrecorded `init` warm-up, macOS ARM64 and Python 3.9.6. The workflow contains one checked sum over [1,2,3]. The full cycle launches four fresh CLI processes: plan, approve, run and verify. Receipt reuse launches another fresh process; brain retrieval queries an unmatched word with no stored knowledge. No native engine or provider is configured. Host load and caches are uncontrolled. No stable tail-latency or throughput conclusion is drawn.

The previously retained 82-test local run took 6.639 seconds; that is one suite observation, not a repeated benchmark. Native qualification and code-check performance depend on the actual workload and are not represented by the tiny timing fixture.

```sh
python3 tools/measure_cli.py --samples 15 --out docs/assets/performance.json
```

[Raw samples and environment](assets/performance.json). Rerunning replaces that local report intentionally; preserve the previous report if comparing revisions.
''')
    help_text=subprocess.run([sys.executable,'-m','bastion','--help'],cwd=str(ROOT),capture_output=True,text=True,check=True).stdout
    families=['mission','check','cartridge','lab','cache']
    help_sections='\n\n'.join('## '+name+'\n\n```text\n'+subprocess.run([sys.executable,'-m','bastion',name,'--help'],cwd=str(ROOT),capture_output=True,text=True,check=True).stdout.strip()+'\n```' for name in families)
    tools=listing()['tools']
    write('docs/FUNCTIONS.md','# Functions and commands\n\nGenerated from the current CLI parser and MCP catalog. Help output does not execute jobs.\n\n## CLI entry point\n\n```text\n'+help_text.strip()+'\n```\n\n'+help_sections+'\n\n## Built-in capability contracts\n\n| Capability | Effect | Required parameters |\n|---|---|---|\n'+'\n'.join('| `'+name+'` | '+value['effect']+' | '+', '.join(value['required'])+' |' for name,value in CAPABILITIES.items())+'\n\n## MCP functions\n\n| Tool | Required arguments | Behavior |\n|---|---|---|\n'+'\n'.join('| `'+t['name']+'` | '+(', '.join(t['inputSchema']['required']) or 'none')+' | '+t['description'].replace('|','/')+' |' for t in tools)+'\n\nApproval, mission work/tick, native configuration, check execution and cache deletion are operator CLI functions, not model-facing MCP tools. A valid evidence receipt can describe a failed check; inspect `passed`.\n')
    write('CONTRIBUTING.md','''# Contributing

Keep changes project-scoped, preserve exact approvals and distinguish observed tests from proposed behavior. Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`. Add regression tests for state/effect changes and include a failure boundary when relevant. Do not weaken an oracle to obtain a pass.

Never commit runtime journals, project inputs, credentials, private chat content, local fixtures or copied research repositories. Use the curated publication tool instead of `git add .`. Source changes invalidate execution approvals; preserve historical evidence and create fresh plans.

The project is MIT licensed. Public issue/PR policy has not yet been selected by the owner. Do not claim maintainer acceptance or permission to publish merely because local checks pass.
''')
    write('SECURITY.md','''# Security and execution boundaries

Bastion's workflow gate executes known built-ins under exact approvals. Separate reviewed code checks execute operator-authorized Python with host permissions; they are not a hostile-code sandbox. Same-user processes can modify code and state. Hash chains are local integrity evidence, not signatures or protection from an equally privileged adversary.

No source, skill, retrieved passage or provider label grants permission. Uncertain code does not retry implicitly. Resource guards are scoped: output bytes are bounded, filesystem use is observed between polls and CPU limits are per process. Group cleanup assumes code does not intentionally escape the group.

No remote reporting address is configured. Do not post secrets, private receipts or exploit-sensitive project content to a public issue. Report concerns through an owner-approved private channel once one is configured; no public security endorsement or certification is claimed.
''')
    write('NOTICE.md','''# Publication and rights notice

The Bastion source is distributed under the MIT License; see LICENSE. Copyright (c) 2026 Stark Fiber Enterprise.

The RF² native executable is not bundled. Upstream repositories studied during development are not bundled with the curated GitHub tree. Their licenses and notices remain applicable to their own material. The Bastion implementation is maintained separately from those reference snapshots.
''')
    write('docs/PUBLICATION.md','''# Publication preparation

This is a curated source/docs package for the owner-authorized public repository https://github.com/starkfiber/Bastion under the MIT License. Preparing the package does not itself publish it. No separate website or GitHub Pages deployment is configured.

The bundle includes original source, tests, demo inputs, documentation, generated illustration, exact diagram, sanitized CLI capture, measured timing samples and a manually triggered CI definition. It excludes Git history, runtime journals, SQLite databases, temporary evidence workspaces, absolute-path-rich qualification reports, copied research repositories and installed native binaries.

The curated source normalizes hardcoded optional engine paths in test/qualification helpers to Path.home(). Runtime code is copied unchanged. A file-hash manifest records the exact prepared contents. Link and credential-pattern checks are bounded heuristics, not a guarantee that publication has no risk. The owner selected public visibility and the MIT License for starkfiber/Bastion. Future publication to other destinations still requires owner authorization.

The CI file uses official actions/checkout@v7 and actions/setup-python@v7 examples, contents:read permissions, and workflow_dispatch only. It has not run on GitHub. Reference documentation: https://github.com/actions/checkout and https://github.com/actions/setup-python .
''')
    write('.github/workflows/ci.yml','''name: Local candidate checks
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ['3.9', '3.12']
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: ${{ matrix.python }}
      - run: python -m unittest discover -s tests -v
        env:
          PYTHONDONTWRITEBYTECODE: '1'
''')
    # Exact diagram, authored from current state semantics, not generated imagery.
    nodes=[('Plan','Pin inputs + runtime'),('Inspect','Review effects'),('Approve','Exact digest'),('Run','Budgeted jobs'),('Verify','Retained receipt')]
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="390" viewBox="0 0 1200 390"><defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="#55c9da"/></marker></defs><rect width="1200" height="390" rx="20" fill="#101923"/><g font-family="Arial,sans-serif"><text x="40" y="48" font-size="26" fill="#eef6fa">BASTION · execution with evidence</text>']
    for i,(title,sub) in enumerate(nodes):
        x=40+i*234
        svg.append(f'<rect x="{x}" y="92" width="188" height="94" rx="12" fill="#1b2b3a" stroke="#4c7180"/><text x="{x+18}" y="128" font-size="22" fill="#eff7fa">{title}</text><text x="{x+18}" y="158" font-size="15" fill="#b8ced7">{html.escape(sub)}</text>')
        if i<4: svg.append(f'<path d="M{x+190} 138h40" stroke="#55c9da" stroke-width="2" marker-end="url(#a)"/>')
    svg.append('<path d="M836 188v54H520" fill="none" stroke="#f0b56d" stroke-width="2"/><rect x="320" y="222" width="480" height="76" rx="12" fill="#392d24"/><text x="345" y="251" font-size="18" fill="#ffd7a7">Failed / uncertain code → blocked</text><text x="345" y="277" font-size="15" fill="#f5d7b6">Investigate → fresh check → new approval</text><text x="40" y="350" font-size="16" fill="#a9c2ce">Workflow recovery is scoped. Code never retries implicitly. OS isolation remains open.</text></g></svg>')
    write('docs/assets/workflow.svg',''.join(svg))
    lines=['BASTION 0.5.0 · captured synthetic CLI walkthrough','Workspace paths redacted · no model call','']
    for step in tour['trace'][:6]:
        argv=step['command']; action=argv[5]
        response=step['response']
        lines.append('$ '+ ' '.join(argv[:6])+ (' '+argv[6] if len(argv)>6 and action=='plan' else ' …'))
        if action=='plan': lines.append('  state: draft | run: '+response['run'][:12]+'… | plan pinned')
        elif action=='inspect': lines.append('  state: '+response['state']+' | approved: '+str(response['approved']).lower())
        elif action=='approve': lines.append('  state: '+response['state']+' | exact digest accepted')
        else: lines.append('  state: '+response['state']+' | receipt: '+response['receiptDigest'][:16]+'…')
        lines.append('')
    lines.append('Observed sum: 6 · receipt reused: true')
    height=58+len(lines)*25
    graphic=f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}"><rect width="1200" height="{height}" rx="16" fill="#111820"/><circle cx="25" cy="24" r="5" fill="#f27972"/><circle cx="44" cy="24" r="5" fill="#eec365"/><circle cx="63" cy="24" r="5" fill="#70c294"/>'
    graphic+=''.join(f'<text x="28" y="{70+i*25}" font-family="Menlo,Consolas,monospace" font-size="16" fill="'+('#74d6df' if line.startswith('$') else '#d3e3ed')+'">'+html.escape(line)+'</text>' for i,line in enumerate(lines))+'</svg>'
    write('docs/assets/walkthrough.svg',graphic)
    from tools.render_page import render
    render()


def stage(destination):
    if destination.exists(): raise RuntimeError('Publication destination exists; preserve it before rebuilding')
    destination.mkdir(parents=True)
    originals=[Path(x) for x in ['README.md','architecture.md','ACCEPTANCE.md','RELEASE-0.4.0.md','RELEASE-0.5.0.md','pyproject.toml','LICENSE','bin/bastion','CONTRIBUTING.md','SECURITY.md','NOTICE.md','.github/workflows/ci.yml']]
    originals+=list(Path('bastion').glob('*.py'))+list(Path('tests').glob('*.py'))
    originals+=[p.relative_to(ROOT) for p in (ROOT/'docs').rglob('*') if p.is_file()]
    originals+=[p.relative_to(ROOT) for p in (ROOT/'demo').rglob('*') if p.is_file() and '.bastion' not in p.parts and '__pycache__' not in p.parts]
    originals+=[Path('tools')/n for n in ['docs_demo.py','measure_cli.py','prepare_github.py','render_page.py','qualify_checks.py','qualify_mixed_missions.py']]
    old="Path("+repr(str(Path.home() / ".codex/plugins/cache/rf2-harness-local/local-ai-harness/0.3.0/bin/rf2-harness"))+")"
    new="(Path.home() / '.codex/plugins/cache/rf2-harness-local/local-ai-harness/0.3.0/bin/rf2-harness')"
    transforms=[]
    for relative in originals:
        source=ROOT/relative; target=destination/relative; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        if relative.suffix=='.py':
            text=target.read_text()
            if old in text: target.write_text(text.replace(old,new)); transforms.append(str(relative))
    (destination/'.gitignore').write_text('.bastion/\n__pycache__/\n*.pyc\n*.egg-info/\ndist/\nbuild/\n.whatif/\nevidence/\nresearch/\n')
    manifest={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination/'PUBLICATION-MANIFEST.json').write_text(json.dumps({'version':'0.5.0','published':False,'portableEnginePathTransforms':transforms,'files':manifest},indent=2)+'\n')
    archive=destination.parent/'bastion-0.5.0-github-ready.tar.gz'
    with tarfile.open(archive,'w:gz') as tar: tar.add(destination,arcname='bastion')
    return {'tree':str(destination),'archive':str(archive),'files':len(manifest),'published':False,'portableEnginePathTransforms':transforms}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',default='dist/github-ready-0.5.0')
    args=parser.parse_args()
    docs()
    if not (ROOT/'docs/assets/hero.png').is_file(): raise SystemExit('Generate and save docs/assets/hero.png before staging')
    result=stage((ROOT/args.stage).resolve())
    print(json.dumps(result))


if __name__=='__main__': main()
