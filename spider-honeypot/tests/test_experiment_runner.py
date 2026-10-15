"""Unit tests for the experiment runner. No server, database or agent is started."""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from experiment import runner
from experiment.config import AGENTS, AgentConfig
from experiment.plan import build_plan
from experiment.runner import execute, load_manifest, parse_record_path, select_runs

PLAN = build_plan("t", 1, {"playwright_baseline": 2, "claude_computer_use": 1})


def test_paid_agent_is_held_back_unless_allowed():
    runs, held_back = select_runs(PLAN, {"runs": {}})
    assert all(r["agent"] == "playwright_baseline" for r in runs)
    assert held_back == 4

    runs, held_back = select_runs(PLAN, {"runs": {}}, allow_paid=True)
    assert held_back == 0
    assert {r["agent"] for r in runs} == {"playwright_baseline", "claude_computer_use"}


def test_finished_runs_are_skipped_and_failed_ones_only_retried_on_request():
    first, second = PLAN["runs"][0]["label"], PLAN["runs"][1]["label"]
    manifest = {"runs": {first: {"status": "done"}, second: {"status": "failed"}}}
    labels = lambda **kw: [r["label"] for r in select_runs(PLAN, manifest, allow_paid=True, **kw)[0]]
    assert first not in labels() and second not in labels()
    assert second in labels(retry_failed=True) and first not in labels(retry_failed=True)


def test_agent_filter_and_limit():
    runs, _ = select_runs(PLAN, {"runs": {}}, agents={"playwright_baseline"}, limit=3)
    assert len(runs) == 3
    assert [r["order"] for r in runs] == sorted(r["order"] for r in runs)


def test_every_agent_command_is_a_python_module_call_with_the_base_url():
    for config in AGENTS.values():
        command = config.command("http://127.0.0.1:9")
        assert command[:3] == [sys.executable, "-m", config.module]
        assert command[command.index("--base-url") + 1] == "http://127.0.0.1:9"


def test_only_the_claude_agent_costs_money_and_it_confirms_spend_itself():
    assert [name for name, c in AGENTS.items() if c.costs_money] == ["claude_computer_use"]
    assert "--confirm-spend" in AGENTS["claude_computer_use"].extra_args


def test_parse_record_path():
    assert parse_record_path("Visited 8 pages.\nRun record written to /a/b/c.json\n") == Path("/a/b/c.json")
    assert parse_record_path("nothing here") is None


def test_execute_saves_manifest_after_each_run_and_resumes(tmp_path):
    manifest_file = tmp_path / "t" / "manifest.json"
    calls = []

    def fake(run, out_dir, port):
        calls.append(run["label"])
        status = "failed" if len(calls) == 2 else "done"
        return {"label": run["label"], "status": status, "error": "boom" if status == "failed" else None}

    runs, _ = select_runs(PLAN, {"runs": {}}, limit=3)
    execute(PLAN, runs, manifest_file, 8000, runner=fake, progress=lambda _: None)
    saved = load_manifest(manifest_file, "t")
    assert list(saved["runs"]) == calls
    assert [e["status"] for e in saved["runs"].values()] == ["done", "failed", "done"]

    # A second pass does the remaining runs and none of the finished or failed ones.
    runs, _ = select_runs(PLAN, saved)
    assert not set(calls) & {r["label"] for r in runs}


FAKE_AGENT = """
import json, pathlib, sys
out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
out.write_text(json.dumps({"session_id": "abc123"}))
print("Run record written to", out)
"""


@pytest.fixture
def fake_server(monkeypatch):
    @contextmanager
    def server(condition, port, log_path):
        yield "http://127.0.0.1:9"

    monkeypatch.setattr(runner, "running_server", server)


def _use_fake_agent(monkeypatch, tmp_path, script):
    path = tmp_path / "fake_agent.py"
    path.write_text(script)
    record = tmp_path / "source.json"

    class Fake(AgentConfig):
        def command(self, base_url):
            return [sys.executable, str(path), "--out", str(record)]

    fake = Fake(name="playwright_baseline", module="x", extra_args=(), default_repetitions=1, timeout_seconds=30)
    monkeypatch.setitem(AGENTS, "playwright_baseline", fake)
    return record


def test_run_one_moves_the_record_to_a_file_named_after_the_label(tmp_path, monkeypatch, fake_server):
    source = _use_fake_agent(monkeypatch, tmp_path, FAKE_AGENT)
    run = next(r for r in PLAN["runs"] if r["agent"] == "playwright_baseline")
    out_dir = tmp_path / "results"
    entry = runner.run_one(run, out_dir, 8000)

    assert entry["status"] == "done"
    assert entry["session_id"] == "abc123"
    assert (out_dir / "records" / f"{run['label']}.json").exists()
    assert not source.exists()
    assert entry["started_at"] and entry["finished_at"]


def test_run_one_reports_failure_when_the_agent_fails(tmp_path, monkeypatch, fake_server):
    _use_fake_agent(monkeypatch, tmp_path, "import sys; print('it broke'); sys.exit(3)")
    run = next(r for r in PLAN["runs"] if r["agent"] == "playwright_baseline")
    entry = runner.run_one(run, tmp_path / "results", 8000)
    assert entry["status"] == "failed"
    assert entry["returncode"] == 3
    assert "it broke" in entry["error"]


def test_a_server_problem_stops_the_experiment_without_recording_a_failed_run(tmp_path, monkeypatch):
    @contextmanager
    def broken(condition, port, log_path):
        raise runner.ServerError("Port 8000 is already in use.")
        yield

    monkeypatch.setattr(runner, "running_server", broken)
    manifest_file = tmp_path / "t" / "manifest.json"
    runs, _ = select_runs(PLAN, {"runs": {}})
    with pytest.raises(runner.ServerError):
        execute(PLAN, runs, manifest_file, 8000, progress=lambda _: None)
    assert not manifest_file.exists()