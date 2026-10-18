"""Tests for the checks that a saved run record shows a real run, and for `experiment check`."""
import json

from agents.shared.record_checks import crawl4ai_problem, record_problem

OK = {"url": "http://x/", "success": True, "error_message": None}
MEMORY = {"url": "http://x/blog", "success": False, "error_message": "Requeued due to critical memory pressure"}


def test_a_crawl4ai_run_with_all_pages_fetched_is_fine():
    assert crawl4ai_problem([OK, OK]) is None


def test_pages_refused_for_lack_of_memory_make_the_run_invalid_even_if_some_pages_worked():
    problem = crawl4ai_problem([OK, OK, MEMORY, MEMORY])
    assert "2 of 4" in problem and "memory" in problem


def test_a_crawl_with_no_pages_or_a_failed_start_page_is_invalid():
    assert "no pages" in crawl4ai_problem([])
    assert "start page" in crawl4ai_problem([{"url": "http://x", "success": False, "error_message": "refused"}, OK])


def test_other_failed_pages_do_not_invalidate_the_run():
    assert crawl4ai_problem([OK, {"url": "http://x/gone", "success": False, "error_message": "404"}]) is None


def test_record_problem_dispatches_on_the_agent_name():
    assert record_problem("crawl4ai_html", {"pages": [MEMORY]}) is not None
    assert record_problem("playwright_ignore_robots", {"pages_visited": 0}) is not None
    assert record_problem("playwright_baseline", {"pages_visited": 9}) is None
    assert record_problem("playwright_baseline", {}) is None
    assert record_problem("human_baseline", {}) is None
    assert record_problem("claude_computer_use", {"iterations_used": 0}) is not None


def test_the_check_command_marks_invalid_runs_as_failed(tmp_path, monkeypatch, capsys):
    from experiment import __main__ as cli
    from experiment import runner
    from experiment.plan import build_plan, plan_path, save_plan

    monkeypatch.setattr("experiment.config.PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr("experiment.plan.PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr("experiment.config.RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr("experiment.runner.RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(cli, "plan_path", lambda name: tmp_path / "plans" / f"{name}.json")
    monkeypatch.setattr(cli, "manifest_path", lambda name: tmp_path / "results" / name / "manifest.json")

    plan = build_plan("t", 1, {"crawl4ai_html": 1})
    save_plan(plan, tmp_path / "plans" / "t.json")
    out_dir = tmp_path / "results" / "t"
    (out_dir / "records").mkdir(parents=True)
    runs = {}
    for i, run in enumerate(plan["runs"][:2]):
        pages = [MEMORY] if i == 0 else [OK]
        (out_dir / "records" / f"{run['label']}.json").write_text(json.dumps({"pages": pages}))
        runs[run["label"]] = {**run, "status": "done", "record": f"records/{run['label']}.json", "error": None}
    runner.save_manifest(out_dir / "manifest.json", {"plan": "t", "runs": runs})

    import argparse

    assert cli.cmd_check(argparse.Namespace(plan="t", apply=True)) == 1
    manifest = json.loads((out_dir / "manifest.json").read_text())
    statuses = [manifest["runs"][r["label"]]["status"] for r in plan["runs"][:2]]
    assert statuses == ["failed", "done"]
    assert "memory" in capsys.readouterr().out


def test_crawl4ai_memory_guard_is_switched_off_for_page_fetches():
    import pytest

    pytest.importorskip("crawl4ai")
    from agents.crawl4ai_scraper.scraper import _dispatcher_without_memory_limit

    dispatcher = _dispatcher_without_memory_limit()
    # Memory use is reported as at most 100%, so thresholds above that can never be reached.
    assert dispatcher.memory_threshold_percent > 100
    assert dispatcher.critical_threshold_percent > 100