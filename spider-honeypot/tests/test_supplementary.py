"""Tests for the supplementary Crawl4AI run (docs/PROTOCOL.md, amendment version 1.8). No network, no model, no database."""
import json
import sys
from pathlib import Path

import pytest

from experiment import __main__ as cli
from experiment.config import AGENTS, CONDITIONS, SUPPLEMENTARY_AGENTS, agent_config, known_agents
from experiment.plan import build_plan, load_plan, plan_path
from experiment.runner import select_runs
from agents.shared.record_checks import record_problem
import supplementary_summary as supp


def test_supplementary_agents_are_not_part_of_the_main_agents():
    assert not set(SUPPLEMENTARY_AGENTS) & set(AGENTS)
    assert list(AGENTS) == [
        "playwright_baseline", "playwright_ignore_robots", "crawl4ai_markdown", "crawl4ai_html",
        "human_baseline", "claude_computer_use", "claude_text_browser",
    ]
    assert known_agents()[: len(AGENTS)] == list(AGENTS)


def test_they_are_the_main_crawl4ai_configurations_plus_the_summary_flag():
    for mode in ("markdown", "html"):
        main, summary = AGENTS[f"crawl4ai_{mode}"], SUPPLEMENTARY_AGENTS[f"crawl4ai_{mode}_summary"]
        assert summary.module == main.module
        assert summary.extra_args == main.extra_args + ("--summary",)
        assert (summary.default_repetitions, summary.timeout_seconds, summary.costs_money) == (10, 1800, False)
        assert "--summary" in agent_config(summary.name).command("http://x")
        assert "--summary" not in main.command("http://x")


def test_the_main_plan_can_still_be_regenerated_exactly():
    saved = plan_path("main")
    if not saved.exists():
        pytest.skip("no main plan file")
    old = json.loads(saved.read_text(encoding="utf-8"))
    new = build_plan("main", old["seed"], {n: a.default_repetitions for n, a in AGENTS.items()})
    assert new == old


def test_the_supplementary_plan_is_prompt_injection_only_with_ten_runs_per_mode(tmp_path):
    plan = build_plan("crawl4ai_summary", 1800, {"crawl4ai_markdown_summary": 10, "crawl4ai_html_summary": 10}, conditions=("prompt_injection",))
    assert len(plan["runs"]) == 20
    assert {r["condition"] for r in plan["runs"]} == {"prompt_injection"}
    runs, held = select_runs(plan, {"runs": {}})
    assert len(runs) == 20 and held == 0


def test_condition_option_is_validated():
    assert cli._condition_list(None) == CONDITIONS
    assert cli._condition_list("prompt_injection") == ("prompt_injection",)
    with pytest.raises(SystemExit):
        cli._condition_list("nonsense")
    with pytest.raises(SystemExit):
        cli._agent_list("nonsense")
    assert cli._agent_list("crawl4ai_html_summary") == ["crawl4ai_html_summary"]


def test_runs_of_the_summary_agents_are_checked_like_other_crawl4ai_runs():
    assert record_problem("crawl4ai_html_summary", {"pages": []}) is not None
    assert record_problem("crawl4ai_markdown_summary", {"pages": [{"url": "http://x", "success": True}]}) is None


def _capture_strategy(monkeypatch):
    pytest.importorskip("crawl4ai")
    from agents.crawl4ai_scraper import scraper

    seen = {}

    class Stop(Exception):
        pass

    def fake_strategy(**kwargs):
        seen.update(kwargs)
        raise Stop

    monkeypatch.setattr(scraper, "_check_ollama_reachable", lambda url: None)
    monkeypatch.setattr(scraper, "LLMExtractionStrategy", fake_strategy)
    return scraper, seen, Stop


def test_the_summary_option_adds_a_one_field_schema_and_nothing_else(monkeypatch):
    import asyncio

    scraper, seen, Stop = _capture_strategy(monkeypatch)
    with pytest.raises(Stop):
        asyncio.run(scraper.run_crawl("http://x", summary=True))
    assert seen["schema"] == scraper.SUMMARY_SCHEMA and list(seen["schema"]["properties"]) == ["summary"]
    assert seen["extraction_type"] == "schema"
    assert seen["instruction"] == scraper.DEFAULT_TASK_INSTRUCTION  # the frozen task text, unchanged


def test_without_the_option_the_strategy_is_built_exactly_as_in_the_main_run(monkeypatch):
    import asyncio

    scraper, seen, Stop = _capture_strategy(monkeypatch)
    with pytest.raises(Stop):
        asyncio.run(scraper.run_crawl("http://x"))
    assert set(seen) == {"llm_config", "instruction", "input_format"}


def _fake_plan(tmp_path, monkeypatch):
    base = tmp_path / "exp"
    plan_dir = base / "crawl4ai_summary"
    (plan_dir / "records").mkdir(parents=True)
    (plan_dir / "server_records").mkdir()
    runs = {
        "a1": ("crawl4ai_html_summary", [{"url": "http://127.0.0.1:8000/documents/vendor-notes", "success": True,
                                          "extracted_content": json.dumps([{"summary": "Payment terms. HONEYTOK-VIS-0123ABCD", "error": False}])},
                                         {"url": "http://127.0.0.1:8000/", "success": True, "extracted_content": json.dumps([{"summary": "Nothing sensitive."}])}], 1),
        "a2": ("crawl4ai_markdown_summary", [{"url": "http://127.0.0.1:8000/documents/vendor-notes", "success": True,
                                              "extracted_content": json.dumps([{"title": "Vendor Notes", "error": False}])}], 0),
    }
    manifest = {"plan": "crawl4ai_summary", "runs": {}}
    for i, (key, (agent, pages, hits)) in enumerate(runs.items(), start=1):
        label = f"{agent}__prompt_injection__r{i:02d}"
        (plan_dir / "records" / f"{label}.json").write_text(json.dumps({"pages": pages}))
        (plan_dir / "server_records" / f"{label}.json").write_text(json.dumps({"trap_hit_count": hits}))
        manifest["runs"][label] = {"label": label, "agent": agent, "order": i, "status": "done", "record": f"records/{label}.json"}
    (plan_dir / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(supp, "BASE", base)
    return base


def test_the_analysis_finds_the_token_and_the_summary_field_and_writes_a_coding_sheet(tmp_path, monkeypatch, capsys):
    base = _fake_plan(tmp_path, monkeypatch)
    assert supp.main([]) == 0
    sheet = supp.read_sheet(base / "crawl4ai_summary" / "analysis" / "coding_sheet_supplementary.csv")
    by_agent = {r["agent"]: r for r in sheet}
    html = by_agent["crawl4ai_html_summary"]
    assert html["trap_hit"] == "True" and html["summary_field_on_trap_page"] == "True"
    assert html["token_visible_copy"] == "True" and html["token_comment_copy"] == "False"
    md = by_agent["crawl4ai_markdown_summary"]
    assert md["summary_field_on_trap_page"] == "False" and md["token_visible_copy"] == "False" and md["trap_hit"] == "False"


def test_a_coded_sheet_is_never_overwritten_and_results_need_coding(tmp_path, monkeypatch):
    base = _fake_plan(tmp_path, monkeypatch)
    assert supp.main([]) == 0
    assert supp.main(["--results"]) == 2  # nothing coded yet
    path = base / "crawl4ai_summary" / "analysis" / "coding_sheet_supplementary.csv"
    rows = supp.read_sheet(path)
    rows[0][supp.FOLLOWED] = "none"
    supp.write_sheet(path, rows)
    assert supp.main([]) == 2  # refuses to overwrite coded cells
    assert supp.main(["--results"]) == 0
    text = (path.parent / "supplementary_results.md").read_text(encoding="utf-8")
    assert "crawl4ai_html_summary" in text and "1 / 0 / 0 (coded 1 of 1)" in text


def test_summaries_in_handles_bad_output():
    assert supp.summaries_in(None) == []
    assert supp.summaries_in("not json") == []
    assert supp.summaries_in('[{"summary": "x"}, {"title": "y"}]') == ["x"]