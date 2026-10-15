"""Unit tests for the experiment run plan."""
import re
from collections import Counter

import pytest

from experiment.config import CONDITIONS
from experiment.plan import build_plan, load_plan, make_label, save_plan

REPS = {"playwright_baseline": 3, "crawl4ai_html": 3, "claude_computer_use": 2}


def test_same_seed_gives_same_plan():
    assert build_plan("t", 1, REPS) == build_plan("t", 1, REPS)


def test_different_seed_changes_the_order_but_not_the_runs():
    a, b = build_plan("t", 1, REPS), build_plan("t", 2, REPS)
    assert [r["label"] for r in a["runs"]] != [r["label"] for r in b["runs"]]
    assert sorted(r["label"] for r in a["runs"]) == sorted(r["label"] for r in b["runs"])


def test_every_agent_and_condition_gets_exactly_its_repetitions():
    plan = build_plan("t", 1, REPS)
    counts = Counter((r["agent"], r["condition"]) for r in plan["runs"])
    for agent, n in REPS.items():
        for condition in CONDITIONS:
            assert counts[(agent, condition)] == n
    assert len(plan["runs"]) == sum(REPS.values()) * len(CONDITIONS)


def test_blocks_are_complete_and_in_order():
    plan = build_plan("t", 1, REPS)
    blocks = [r["block"] for r in plan["runs"]]
    assert blocks == sorted(blocks)
    first_block = [(r["agent"], r["condition"]) for r in plan["runs"] if r["block"] == 1]
    assert len(first_block) == len(set(first_block)) == len(REPS) * len(CONDITIONS)
    # An agent with fewer repetitions is absent from the later blocks.
    last_agents = {r["agent"] for r in plan["runs"] if r["block"] == 3}
    assert last_agents == {"playwright_baseline", "crawl4ai_html"}


def test_labels_are_unique_ordered_and_file_name_safe():
    plan = build_plan("t", 1, REPS)
    labels = [r["label"] for r in plan["runs"]]
    assert len(labels) == len(set(labels))
    assert [r["order"] for r in plan["runs"]] == list(range(1, len(labels) + 1))
    assert all(re.fullmatch(r"[A-Za-z0-9_]+", label) for label in labels)
    assert make_label("crawl4ai_html", "link_graph", 3) == "crawl4ai_html__link_graph__r03"


def test_run_seeds_are_stable_and_differ_between_runs():
    a, b = build_plan("t", 1, REPS), build_plan("other_name", 1, REPS)
    assert [r["run_seed"] for r in a["runs"]] == [r["run_seed"] for r in b["runs"]]
    assert len({r["run_seed"] for r in a["runs"]}) == len(a["runs"])


@pytest.mark.parametrize(
    "name, reps",
    [("bad name", {"a": 1}), ("ok", {}), ("ok", {"a": 0})],
)
def test_invalid_plans_are_rejected(name, reps):
    with pytest.raises(ValueError):
        build_plan(name, 1, reps)


def test_save_and_load_round_trip_and_no_silent_overwrite(tmp_path):
    plan = build_plan("t", 1, REPS)
    path = tmp_path / "t.json"
    save_plan(plan, path)
    assert load_plan(path) == plan
    with pytest.raises(FileExistsError):
        save_plan(plan, path)
    save_plan(plan, path, overwrite=True)