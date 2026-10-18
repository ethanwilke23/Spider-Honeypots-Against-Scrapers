import json
from datetime import datetime, timezone

import pytest

from experiment import freeze
from experiment.__main__ import _check_main_seed


def _env(**over):
    env = {
        "chromium": "140.0", "ollama": {"digest": "abc"}, "docker_image": {"id": "sha256:1"},
        "git_commit": "deadbeef", "git_uncommitted_changes": False,
        "packages": {"playwright": "1.62.0", "Crawl4AI": "0.9.4", "anthropic": "1.0"},
    }
    env.update(over)
    return env


def test_seed_is_in_range_and_varies():
    seeds = {freeze.draw_seed() for _ in range(20)}
    assert all(0 <= s < 10**6 for s in seeds) and len(seeds) > 1


def test_missing_items_lists_what_is_absent():
    assert freeze.missing_items(_env()) == []
    problems = freeze.missing_items(_env(chromium=None, ollama={"digest": None}, git_uncommitted_changes=True))
    assert len(problems) == 3 and any("Ollama" in p for p in problems) and any("uncommitted" in p for p in problems)
    assert any("anthropic" in p for p in freeze.missing_items(_env(packages={"playwright": "1", "Crawl4AI": "1", "anthropic": None})))


def test_build_record_has_time_and_seed():
    record = freeze.build_record(123, {"x": 1}, datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc))
    assert record == {"frozen_at": "2026-10-19T08:00:00Z", "main_seed": 123, "environment": {"x": 1}}


def test_collect_environment_runs_without_services():
    env = freeze.collect_environment()
    assert env["claude_models"]["claude_text_browser"] == "claude-sonnet-5-5"
    assert len(env["task_text_sha256"]) == 3 and env["protocol_version"]
    assert set(env["ollama"]) >= {"model", "digest"}


def test_main_plan_requires_the_frozen_seed(tmp_path, monkeypatch):
    path = tmp_path / "freeze_record.json"
    monkeypatch.setattr(freeze, "FREEZE_PATH", path)
    _check_main_seed("pilot", 700)  # other plans are unconstrained
    with pytest.raises(ValueError):
        _check_main_seed("main", 5)
    path.write_text(json.dumps({"main_seed": 5}))
    _check_main_seed("main", 5)
    with pytest.raises(ValueError):
        _check_main_seed("main", 6)