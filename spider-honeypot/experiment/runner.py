"""
Runs the runs in a plan, one at a time, and keeps a manifest of what happened.

For each run it starts the server with the run's HONEYPOT_VARIANT, runs the
agent, stops the server, and moves the agent's run record to a file named after
the run label. The manifest is saved after every run, so an interrupted
experiment can be resumed: finished runs are skipped.

The server's database logs are not touched here. Each manifest entry stores the
start and finish time and, where the agent has one, the session id, so server
records can be matched to runs later.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from agents.shared.record_checks import record_problem
from experiment.config import AGENTS, PROJECT_ROOT, RESULTS_DIR

RECORD_LINE = re.compile(r"Run record written to (.+)")
SERVER_START_TIMEOUT = 90


class ServerError(RuntimeError):
    """The server could not be started for a run. This is a setup problem, not a result."""

OUTPUT_TAIL_CHARS = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Manifest

def manifest_path(plan_name: str, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / plan_name / "manifest.json"


def load_manifest(path: Path, plan_name: str) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"plan": plan_name, "runs": {}}


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# Choosing what to run

def select_runs(
    plan: dict,
    manifest: dict,
    agents: set[str] | None = None,
    allow_paid: bool = False,
    retry_failed: bool = False,
    limit: int | None = None,
) -> tuple[list[dict], int]:
    """
    Returns the runs to do, in plan order, and the number of runs left out only
    because they use a paid agent and allow_paid is False.
    """
    selected: list[dict] = []
    held_back = 0
    for run in plan["runs"]:
        if agents is not None and run["agent"] not in agents:
            continue
        status = manifest["runs"].get(run["label"], {}).get("status")
        if status == "done" or (status == "failed" and not retry_failed):
            continue
        if AGENTS[run["agent"]].costs_money and not allow_paid:
            held_back += 1
            continue
        selected.append(run)
    if limit is not None:
        selected = selected[:limit]
    return selected, held_back


def parse_record_path(output: str) -> Path | None:
    matches = RECORD_LINE.findall(output)
    return Path(matches[-1].strip()) if matches else None


# Server and agent processes

def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _health(base_url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=3) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


@contextmanager
def running_server(condition: str, port: int, log_path: Path) -> Iterator[str]:
    """Start the app with HONEYPOT_VARIANT=condition. Yields its base URL."""
    if _port_in_use(port):
        raise ServerError(
            f"Port {port} is already in use. Stop any running server (including 'uvicorn --reload') "
            "before running the experiment; it starts its own server for every run."
        )
    base_url = f"http://127.0.0.1:{port}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HONEYPOT_VARIANT": condition, "PYTHONUTF8": "1"}
    with open(log_path, "ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + SERVER_START_TIMEOUT
            health = None
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise ServerError(f"The server exited during start-up. See {log_path}")
                health = _health(base_url)
                if health:
                    break
                time.sleep(1)
            if not health:
                raise ServerError(f"The server did not become healthy within {SERVER_START_TIMEOUT}s. See {log_path}")
            if health.get("honeypot_variant") != condition:
                raise ServerError(
                    f"Server reports honeypot_variant={health.get('honeypot_variant')!r}, expected {condition!r}."
                )
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            time.sleep(1)  # let the port be released before the next run


def _record_problem(agent: str, record_path: Path) -> str | None:
    """Why a saved record is not a real run (see agents/shared/record_checks.py), or None."""
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except ValueError:
        return "the record is not valid JSON"
    return record_problem(agent, record)


def run_one(run: dict, out_dir: Path, port: int) -> dict:
    """
    Do a single run and return its manifest entry. An agent failure is recorded in the
    entry; a server problem raises ServerError, because the run never took place.
    """
    config = AGENTS[run["agent"]]
    label = run["label"]
    entry = {
        "label": label,
        "agent": run["agent"],
        "condition": run["condition"],
        "repetition": run["repetition"],
        "order": run["order"],
        "status": "failed",
        "started_at": None,
        "finished_at": None,
        "returncode": None,
        "session_id": None,
        "record": None,
        "error": None,
    }
    with running_server(run["condition"], port, out_dir / "server_logs" / f"{label}.log") as base_url:
        entry["started_at"] = _now()
        try:
            result = subprocess.run(
                config.command(base_url, run["run_seed"]),
                cwd=PROJECT_ROOT,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout_seconds,
            )
            output, entry["returncode"] = result.stdout or "", result.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout) or ""
            entry["error"] = f"Timed out after {config.timeout_seconds}s."
        entry["finished_at"] = _now()

    log_path = out_dir / "agent_logs" / f"{label}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")

    record_source = parse_record_path(output)
    if entry["returncode"] == 0 and record_source and record_source.exists():
        destination = out_dir / "records" / f"{label}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(record_source), destination)
        entry["record"] = str(destination.relative_to(out_dir))
        try:
            entry["session_id"] = json.loads(destination.read_text(encoding="utf-8")).get("session_id")
        except ValueError:
            pass
        entry["status"] = "done"
        problem = _record_problem(run["agent"], destination)
        if problem:
            entry["status"] = "failed"
            entry["error"] = f"Invalid run (it will be rerun with --retry-failed): {problem}."
    elif entry["error"] is None:
        entry["error"] = f"Agent exited with code {entry['returncode']} or wrote no run record. Output ended: " + output[-OUTPUT_TAIL_CHARS:]
    return entry


def execute(
    plan: dict,
    runs: list[dict],
    manifest_file: Path,
    port: int,
    runner: Callable[[dict, Path, int], dict] = run_one,
    progress: Callable[[str], None] = print,
) -> dict:
    """Run the selected runs in order, saving the manifest after each one."""
    manifest = load_manifest(manifest_file, plan["name"])
    out_dir = manifest_file.parent
    for index, run in enumerate(runs, start=1):
        progress(f"[{index}/{len(runs)}] {run['label']} (HONEYPOT_VARIANT={run['condition']}) ...")
        started = time.monotonic()
        entry = runner(run, out_dir, port)
        manifest["runs"][run["label"]] = entry
        save_manifest(manifest_file, manifest)
        note = "" if entry["status"] == "done" else f" - {entry['error']}"
        progress(f"    {entry['status']} in {time.monotonic() - started:.0f}s{note}")
    return manifest