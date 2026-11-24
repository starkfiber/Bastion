import argparse
import json
import sys
from . import __version__
from .adapters import proposal
from .core import BastionError, canonical
from .lab import run_campaign, verify_campaign, replay_trial
from .mcp import catalog, serve
from .runtime import Runtime
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="BASTION model-neutral local harness foundation")
    parser.add_argument("--workspace", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    task = commands.add_parser("task").add_subparsers(dest="task_command", required=True)
    task.add_parser("plan").add_argument("path")
    task.add_parser("inspect").add_argument("id")
    command=task.add_parser("report");command.add_argument("id");command.add_argument("--format",choices=("json","markdown","html"),default="json")
    for action in ("approve","run"):
        command=task.add_parser(action);command.add_argument("id");command.add_argument("digest")
    command=task.add_parser("export");command.add_argument("id");command.add_argument("receipt_digest");command.add_argument("destination");command.add_argument("--format",choices=("markdown","html"),default="markdown")
    command=commands.add_parser("metrics");command.add_argument("--limit",type=int,default=100)
    command=commands.add_parser("progress");command.add_argument("--cursor");command.add_argument("--limit",type=int,default=50)
    check = commands.add_parser("check").add_subparsers(dest="check_command", required=True)
    check.add_parser("plan").add_argument("path")
    for name in ("inspect", "verify"):
        check.add_parser(name).add_argument("id")
    for name in ("approve", "run"):
        command = check.add_parser(name)
        command.add_argument("id")
        command.add_argument("digest")
    for name in ("init", "capabilities", "mcp", "audit", "readiness"):
        commands.add_parser(name)
    command = commands.add_parser("native-configure")
    command.add_argument("path")
    command.add_argument("sha256")
    cache = commands.add_parser("cache").add_subparsers(dest="cache_command", required=True)
    command = cache.add_parser("stash")
    command.add_argument("path")
    command.add_argument("--ttl", type=int, default=3600)
    cache.add_parser("prune-plan")
    cache.add_parser("prune").add_argument("digest")
    mission = commands.add_parser("mission").add_subparsers(dest="mission_command", required=True)
    mission.add_parser("plan").add_argument("path")
    mission.add_parser("due")
    command=mission.add_parser("cancel");command.add_argument("id");command.add_argument("digest");command.add_argument("--reason",required=True)
    command = mission.add_parser("tick")
    command.add_argument("--limit", type=int, default=10)
    mission.add_parser("inspect").add_argument("id")
    command=mission.add_parser('replace-check')
    command.add_argument('id')
    command.add_argument('digest')
    command.add_argument('position',type=int)
    command.add_argument('replacement')
    command.add_argument('replacement_digest')
    command.add_argument('--reason',required=True)
    for name in ("approve", "work"):
        command = mission.add_parser(name)
        command.add_argument("id")
        command.add_argument("digest")
    for name in ("plan", "propose", "skill-register"):
        command = commands.add_parser(name)
        command.add_argument("path")
        if name == "propose":
            command.add_argument("--provider", default="external")
            command.add_argument("--model", default="unspecified")
    for name in ("approve", "run", "recover"):
        command = commands.add_parser(name)
        command.add_argument("run")
        command.add_argument("digest")
    for name in ("inspect", "verify", "map"):
        commands.add_parser(name).add_argument("run")
    for name in ("knowledge", "experience", "brain"):
        commands.add_parser(name).add_argument("query")
    command = commands.add_parser("lesson-propose")
    command.add_argument("source")
    command.add_argument("text")
    commands.add_parser("lesson-review").add_argument("id")
    command = commands.add_parser("handoff")
    command.add_argument("goal")
    command.add_argument("--query", required=True)
    commands.add_parser("handoff-inspect").add_argument("handoff")
    command = commands.add_parser("handoff-propose")
    command.add_argument("handoff")
    command.add_argument("path")
    command.add_argument("--provider", default="external")
    command.add_argument("--model", default="unspecified")
    cartridge = commands.add_parser("cartridge").add_subparsers(dest="cartridge_command", required=True)
    cartridge.add_parser("list")
    cartridge.add_parser("register").add_argument("path")
    for name in ("inspect", "qualify"):
        cartridge.add_parser(name).add_argument("id")
    command = cartridge.add_parser("activate")
    command.add_argument("id")
    command.add_argument("qualification")
    command = cartridge.add_parser("propose")
    command.add_argument("name")
    command.add_argument("path", help="project-relative JSON inputs file")
    command = cartridge.add_parser("compare")
    command.add_argument("baseline")
    command.add_argument("candidate")
    lab = commands.add_parser("lab").add_subparsers(dest="lab_command", required=True)
    command = lab.add_parser("run")
    command.add_argument("--trials", type=int, required=True)
    command.add_argument("--seed", type=int, default=1)
    command.add_argument("--max-seconds", type=int, default=60)
    lab.add_parser("verify").add_argument("id")
    command = lab.add_parser("replay")
    command.add_argument("id")
    command.add_argument("index", type=int)
    args = parser.parse_args()
    try:
        store = Store(args.workspace)
        if args.command == "native-configure":
            from .native import configure
            print(canonical(configure(store, args.path, args.sha256)))
            return 0
        if args.command == 'readiness':
            from .readiness import inspect
            print(canonical(inspect()))
            return 0
        runtime = Runtime(store)
        command = args.command
        if command == "progress":
            from .progress import changes
            print(canonical(changes(runtime,args.cursor,args.limit)));return 0
        if command == "metrics":
            from .metrics import summary
            print(canonical(summary(runtime,args.limit)))
            return 0
        if command == "task":
            from . import tasking,checks
            action=args.task_command
            if action=="plan": result=tasking.plan(runtime,json.loads(store.project_file(args.path).read_text()))
            elif action in ("inspect","approve"):
                result=checks.inspect(runtime,args.id) if action=="inspect" else checks.approve(runtime,args.id,args.digest)
            elif action=="run": result=tasking.run(runtime,args.id,args.digest)
            elif action=="export": result=tasking.export(runtime,args.id,args.receipt_digest,args.destination,args.format)
            else:
                result=tasking.report(runtime,args.id)
                if args.format in ("markdown","html"):
                    print((tasking.html_report if args.format=="html" else tasking.markdown)(result),end="")
                    return 0
            print(canonical(result))
            return 1 if action=="run" and not result['passed'] else 0
        if command == "check":
            from . import checks
            if args.check_command == "plan":
                result = checks.plan(runtime, json.loads(store.project_file(args.path).read_text()))
            elif args.check_command in ("approve", "run"):
                result = getattr(checks, args.check_command)(runtime, args.id, args.digest)
            else:
                result = getattr(checks, args.check_command)(runtime, args.id)
            print(canonical(result))
            return 0
        if command == "mcp":
            serve(runtime)
            return 0
        if command == "init":
            result = {"workspace": str(store.workspace), "state": str(store.root), "version": __version__}
        elif command == "native-configure":
            from .native import configure
            result = configure(store, args.path, args.sha256)
        elif command == "mission":
            from . import missions
            action = args.mission_command
            if action == "cancel":
                result=missions.cancel(runtime,args.id,args.digest,args.reason)
            elif action == "plan":
                result = missions.plan(runtime, json.loads(store.project_file(args.path).read_text()))
            elif action == "due":
                result = missions.due(runtime)
            elif action == "tick":
                result = missions.tick(runtime, args.limit)
            elif action == "inspect":
                result = missions.inspect(runtime, args.id)
            elif action == 'replace-check':
                result=missions.replace_check(runtime,args.id,args.digest,args.position,args.replacement,args.replacement_digest,args.reason)
            else:
                result = getattr(missions, action)(runtime, args.id, args.digest)
        elif command == "cache":
            from . import cache
            if args.cache_command == "stash":
                result = cache.stash(store, args.path, args.ttl)
            elif args.cache_command == "prune-plan":
                result = cache.prune_plan(store)
            else:
                result = cache.prune(store, args.digest)
        elif command == "capabilities":
            result = catalog()
        elif command in ("plan", "propose"):
            value = json.loads(store.project_file(args.path).read_text())
            if command == "propose":
                value = proposal(value, args.provider, args.model)
            result = runtime.plan(value)
        elif command in ("approve", "run", "recover"):
            result = getattr(runtime, command)(args.run, args.digest)
        elif command in ("inspect", "verify"):
            result = getattr(runtime, command)(args.run)
        elif command == "audit":
            result = store.verify_events()
        elif command == 'readiness':
            from . import readiness
            result=readiness.inspect()
        elif command == "brain":
            from .brain import context
            result = context(runtime, args.query)
        elif command in ("handoff", "handoff-inspect", "handoff-propose"):
            from .handoff import prepare, inspect, submit
            if command == "handoff":
                result = prepare(runtime, args.goal, args.query)
            elif command == "handoff-inspect":
                result = inspect(runtime, args.handoff)
            else:
                payload = json.loads(store.project_file(args.path).read_text())
                result = submit(runtime, args.handoff, payload, args.provider, args.model)
        elif command == "cartridge":
            from . import cartridges
            action = args.cartridge_command
            if action == "list":
                result = cartridges.listing(runtime)
            elif action == "register":
                result = cartridges.register(runtime, json.loads(store.project_file(args.path).read_text()))
            elif action == "inspect":
                result = cartridges.load(runtime, args.id)
            elif action == "qualify":
                result = cartridges.qualify(runtime, args.id)
            elif action == "activate":
                result = cartridges.activate(runtime, args.id, args.qualification)
            elif action == "compare":
                result = cartridges.compare(runtime, args.baseline, args.candidate)
            else:
                result = cartridges.propose(runtime, args.name, json.loads(store.project_file(args.path).read_text()))
        elif command in ("knowledge", "experience"):
            result = {"records": store.search(args.query, "knowledge" if command == "knowledge" else "experiences")}
        elif command == "skill-register":
            result = store.register_skill(args.path)
        elif command == "lesson-propose":
            result = {"id": store.propose_lesson(args.text, args.source), "state": "proposed"}
        elif command == "lesson-review":
            result = store.promote_lesson(args.id)
        elif command == "map":
            plan = runtime.inspect(args.run)["plan"]
            from .core import refs
            lines = ["flowchart TD"]
            for node in plan["workflow"]["nodes"]:
                # IDs are validated but use generated node aliases for Mermaid syntax.
                aliases = {n: "n%d" % i for i, n in enumerate(plan["order"])}
                lines.append('  %s["%s: %s"]' % (aliases[node["id"]], node["id"], node["capability"]))
                for dep in sorted(refs(node["params"]) | set(node.get("after", []))):
                    lines.append("  %s --> %s" % (aliases[dep], aliases[node["id"]]))
            print("\n".join(lines))
            return 0
        elif command == "lab":
            if args.lab_command == "run":
                result = run_campaign(store, args.trials, args.seed, args.max_seconds)
            elif args.lab_command == "verify":
                result = verify_campaign(store, args.id)
            else:
                result = replay_trial(store, args.id, args.index)
        else:
            raise BastionError("unsupported command")
        print(canonical(result))
        return 0
    except (BastionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(canonical({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
