"""
Command line for the experiment scheduler.

    python -m experiment plan --name pilot --agents playwright_baseline,crawl4ai_html --reps 2
    python -m experiment run --plan pilot                # shows what would run
    python -m experiment run --plan pilot --execute      # runs the free agents
    python -m experiment status --plan pilot
    python -m experiment check --plan pilot              # finds runs that did not really take place
    python -m experiment logs export --plan pilot        # save each run's server-side records
    python -m experiment logs reset --yes                # empty the server logs
    python -m experiment analyse --plan main             # tables, charts and the hand-coding sheet
    python -m experiment freeze                          # draw the main seed once and record the environment
    python -m experiment plan --name main --seed <frozen seed>

Paid Claude runs need both --execute and --confirm-spend.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

from experiment.config import AGENTS, DEFAULT_PORT, DEFAULT_SEED
from experiment.plan import build_plan, load_plan, plan_path, save_plan
from experiment.runner import ServerError, execute, load_manifest, manifest_path, select_runs


def _agent_list(text: str | None) -> list[str] | None:
    if not text:
        return None
    names = [n.strip() for n in text.split(",") if n.strip()]
    unknown = [n for n in names if n not in AGENTS]
    if unknown:
        raise SystemExit(f"Unknown agent(s): {', '.join(unknown)}. Choose from: {', '.join(AGENTS)}")
    return names


def _check_main_seed(name: str, seed: int) -> None:
    """The plan called "main" must use the seed recorded by `freeze`, so it cannot be tuned afterwards."""
    from experiment import freeze

    if name != "main":
        return
    record = freeze.load_freeze()
    if record is None:
        raise ValueError("The main plan needs the frozen seed. Run `python -m experiment freeze` first.")
    if record["main_seed"] != seed:
        raise ValueError(f"The main plan must use the frozen seed {record['main_seed']} (you gave {seed}).")


def cmd_plan(args: argparse.Namespace) -> int:
    _check_main_seed(args.name, args.seed)
    names = _agent_list(args.agents) or list(AGENTS)
    repetitions = {n: (args.reps if args.reps else AGENTS[n].default_repetitions) for n in names}
    plan = build_plan(args.name, args.seed, repetitions)
    save_plan(plan, plan_path(args.name), overwrite=args.force)
    print(f"Wrote {plan_path(args.name)}: {len(plan['runs'])} runs, seed {args.seed}.")
    for agent, n in repetitions.items():
        print(f"  {agent}: {n} per condition x {len(plan['conditions'])} conditions = {n * len(plan['conditions'])} runs")
    print("First runs in order:")
    for run in plan["runs"][:5]:
        print(f"  {run['order']:>3}  {run['label']}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    plan = load_plan(plan_path(args.plan))
    manifest_file = manifest_path(plan["name"])
    manifest = load_manifest(manifest_file, plan["name"])
    agents = set(_agent_list(args.agents) or []) or None
    runs, held_back = select_runs(
        plan, manifest, agents=agents, allow_paid=args.confirm_spend, retry_failed=args.retry_failed, limit=args.limit
    )
    if held_back:
        print(f"{held_back} run(s) with a paid agent are being skipped. They need --confirm-spend.")
    if not runs:
        print("Nothing to run.")
        return 0

    if not args.execute:
        print(f"Dry run: {len(runs)} run(s) would be done. Add --execute to run them.")
        for run in runs:
            command = " ".join(AGENTS[run["agent"]].command(f"http://127.0.0.1:{args.port}", run["run_seed"])[1:])
            print(f"  {run['order']:>3}  {run['label']}  HONEYPOT_VARIANT={run['condition']}  python {command}")
        return 0

    paid = sum(AGENTS[r["agent"]].costs_money for r in runs)
    if paid:
        print(f"WARNING: {paid} of these runs call the paid Anthropic API.")
    try:
        manifest = execute(plan, runs, manifest_file, args.port)
    except ServerError as exc:
        print(f"\nStopped: {exc}\nRuns finished before this are saved; run the same command again to continue.")
        return 2
    counts = Counter(entry["status"] for entry in manifest["runs"].values())
    print(f"Finished. Totals so far: {dict(counts)}. Manifest: {manifest_file}")
    return 0 if not any(manifest["runs"].get(r["label"], {}).get("status") != "done" for r in runs) else 1


def cmd_status(args: argparse.Namespace) -> int:
    plan = load_plan(plan_path(args.plan))
    manifest = load_manifest(manifest_path(plan["name"]), plan["name"])
    done: Counter = Counter()
    failed: Counter = Counter()
    planned: Counter = Counter()
    for run in plan["runs"]:
        key = (run["agent"], run["condition"])
        planned[key] += 1
        status = manifest["runs"].get(run["label"], {}).get("status")
        if status == "done":
            done[key] += 1
        elif status == "failed":
            failed[key] += 1
    print(f"Plan {plan['name']} (seed {plan['seed']}): {sum(done.values())}/{len(plan['runs'])} done, {sum(failed.values())} failed")
    print(f"{'agent':<22}{'condition':<18}{'done':>5}{'failed':>8}{'planned':>9}")
    for (agent, cond), total in sorted(planned.items()):
        print(f"{agent:<22}{cond:<18}{done[(agent, cond)]:>5}{failed[(agent, cond)]:>8}{total:>9}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Look through the records of finished runs for runs that did not really take place."""
    import json

    from agents.shared.record_checks import record_problem

    plan = load_plan(plan_path(args.plan))
    manifest_file = manifest_path(plan["name"])
    manifest = load_manifest(manifest_file, plan["name"])
    out_dir = manifest_file.parent
    problems = []
    for entry in sorted(manifest["runs"].values(), key=lambda e: e["order"]):
        if entry["status"] != "done" or not entry.get("record"):
            continue
        record = json.loads((out_dir / entry["record"]).read_text(encoding="utf-8"))
        problem = record_problem(entry["agent"], record)
        if problem:
            problems.append((entry, problem))
    if not problems:
        print("All finished runs look like real runs.")
        return 0
    for entry, problem in problems:
        print(f"  {entry['label']}: {problem}")
        if args.apply:
            entry["status"] = "failed"
            entry["error"] = f"Invalid run (it will be rerun with --retry-failed): {problem}."
    if args.apply:
        from experiment.runner import save_manifest

        save_manifest(manifest_file, manifest)
        print(f"{len(problems)} run(s) marked as failed. Rerun them with: python -m experiment run --plan {plan['name']} --execute --retry-failed")
    else:
        print(f"{len(problems)} run(s) are not real runs. Add --apply to mark them as failed so they can be rerun.")
    return 1


def cmd_freeze(args: argparse.Namespace) -> int:
    import json

    from experiment import freeze

    existing = freeze.load_freeze()
    if existing and not args.force:
        print(f"Already frozen on {existing['frozen_at']} with main seed {existing['main_seed']}.")
        print(f"The record is {freeze.FREEZE_PATH}. The seed is drawn only once; use --force only if the protocol allows a redraw.")
        return 2
    environment = freeze.collect_environment()
    problems = freeze.missing_items(environment)
    if problems:
        print("NOT FROZEN. Fix these first, then run the command again (no seed has been drawn):")
        for problem in problems:
            print(f"  - {problem}")
        return 2
    seed = existing["main_seed"] if existing and args.keep_seed else freeze.draw_seed()
    record = freeze.build_record(seed, environment)
    print(json.dumps(record, indent=2))
    freeze.FREEZE_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"\nWritten to {freeze.FREEZE_PATH}. Commit it before the main run.")
    print(f"Create the main plan with:\n  python -m experiment plan --name main --seed {record['main_seed']}")
    return 0


def cmd_analyse(args: argparse.Namespace) -> int:
    from experiment.analysis import run_analysis

    out_dir = run_analysis(args.plan)
    print(f"Analysis written to {out_dir}")
    print(f"Start with {out_dir / 'results.md'}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    try:
        return _logs_command(args)
    except (OSError, ConnectionError) as exc:
        print(f"Could not reach the database: {exc}\nIs Postgres running (docker compose up -d)?")
        return 2


def _logs_command(args: argparse.Namespace) -> int:
    from experiment import logs

    if args.action == "status":
        counts = logs.run_async(logs.count_rows())
        print(f"request_log: {counts['request_log']} rows, trap_hit_event: {counts['trap_hit_event']} rows, client_event: {counts['client_event']} rows")
        return 0

    if args.action == "export":
        if not args.plan:
            raise ValueError("--plan is required for export.")
        rows = logs.run_async(logs.export_plan(args.plan, only_missing=args.only_missing))
        print(f"Exported {len(rows)} run(s) to agent_runs/experiment/{args.plan}/server_records/ (summary.csv included).")
        for row in rows:
            flag = f"  UNEXPECTED trap hits: {row['unexpected_trap_hits']}" if row["unexpected_trap_hits"] else ""
            if row["requests"] == 0:
                flag += "  NO REQUESTS RECORDED: not a real run"
            print(f"  {row['label']}: {row['requests']} requests, {row['trap_hits']} trap hit(s){flag}")
        return 0

    counts = logs.run_async(logs.count_rows())
    print(f"The server logs hold {counts['request_log']} request rows, {counts['trap_hit_event']} trap hits and {counts['client_event']} page events.")
    if not args.yes:
        print("Nothing deleted. Export any runs you want to keep first, then add --yes to empty the logs.")
        return 0
    logs.run_async(logs.reset_logs())
    print("Server logs emptied.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m experiment", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="Create a run plan (the randomised order of runs).")
    p.add_argument("--name", required=True, help="Used for the plan file name, e.g. pilot or main.")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--agents", help=f"Comma-separated. Default: all of {', '.join(AGENTS)}")
    p.add_argument("--reps", type=int, help="Repetitions per condition for every agent. Default: each agent's own default.")
    p.add_argument("--force", action="store_true", help="Replace an existing plan file.")
    p.set_defaults(func=cmd_plan)

    r = sub.add_parser("run", help="Run the pending runs of a plan (dry run unless --execute).")
    r.add_argument("--plan", required=True)
    r.add_argument("--agents", help="Only run these agents (comma-separated).")
    r.add_argument("--limit", type=int, help="Do at most this many runs now.")
    r.add_argument("--port", type=int, default=DEFAULT_PORT)
    r.add_argument("--execute", action="store_true", help="Actually run. Without it, only prints what would happen.")
    r.add_argument("--confirm-spend", action="store_true", help="Also run the paid Claude agent (makes paid API calls).")
    r.add_argument("--retry-failed", action="store_true")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("status", help="Show progress for a plan.")
    s.add_argument("--plan", required=True)
    s.set_defaults(func=cmd_status)

    c = sub.add_parser("check", help="Find finished runs that did not really take place (for example a crawl that fetched nothing).")
    c.add_argument("--plan", required=True)
    c.add_argument("--apply", action="store_true", help="Mark them as failed so --retry-failed reruns them.")
    c.set_defaults(func=cmd_check)

    f = sub.add_parser("freeze", help="Draw the main seed once and record the environment (docs/freeze_record.json).")
    f.add_argument("--force", action="store_true", help="Replace an existing freeze record (draws a new seed unless --keep-seed).")
    f.add_argument("--keep-seed", action="store_true", help="With --force: keep the recorded seed and refresh only the environment.")
    f.set_defaults(func=cmd_freeze)

    a = sub.add_parser("analyse", help="Compute the measures, tables and charts for a finished plan (reads files only).")
    a.add_argument("--plan", required=True)
    a.set_defaults(func=cmd_analyse)

    g = sub.add_parser("logs", help="Show, export or empty the server logs.")
    g.add_argument("action", choices=["status", "export", "reset"])
    g.add_argument("--plan", help="Plan to export (export only).")
    g.add_argument("--only-missing", action="store_true", help="Export: keep files that already exist.")
    g.add_argument("--yes", action="store_true", help="Reset: really delete the rows.")
    g.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())