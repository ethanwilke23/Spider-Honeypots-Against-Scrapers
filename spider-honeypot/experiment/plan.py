"""
Builds and stores the run plan: the list of runs, in the order they will be done.

The plan is a randomised block design. Each block is one repetition round:
every agent that still needs repetitions appears once for every condition, in a
shuffled order. Stopping part-way through therefore leaves a balanced set of
runs, and slow drift over time (a warm Ollama model, for example) is spread
across conditions instead of piling up in one.

The same seed and settings always give the same plan, so the plan file can be
regenerated and compared.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from experiment.config import CONDITIONS, PLANS_DIR

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def make_label(agent: str, condition: str, repetition: int) -> str:
    """For example: crawl4ai_html__link_graph__r03. Safe to use as a file name."""
    return f"{agent}__{condition}__r{repetition:02d}"


def _run_seed(seed: int, label: str) -> int:
    """A stable per-run seed, for any run that needs its own random choices."""
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


def build_plan(
    name: str,
    seed: int,
    repetitions: dict[str, int],
    conditions: tuple[str, ...] = CONDITIONS,
) -> dict:
    """repetitions maps each agent name to the number of runs per condition."""
    if not _NAME_PATTERN.match(name):
        raise ValueError("Plan name may only contain letters, digits, '_' and '-'.")
    if not repetitions:
        raise ValueError("At least one agent is required.")
    if any(n < 1 for n in repetitions.values()):
        raise ValueError("Every agent needs at least one repetition.")
    if len(set(conditions)) != len(conditions):
        raise ValueError("Conditions must be unique.")

    runs: list[dict] = []
    for block in range(1, max(repetitions.values()) + 1):
        cells = [(agent, cond) for agent, n in repetitions.items() if n >= block for cond in conditions]
        random.Random(f"{seed}:block:{block}").shuffle(cells)
        for agent, cond in cells:
            label = make_label(agent, cond, block)
            runs.append(
                {
                    "order": len(runs) + 1,
                    "block": block,
                    "label": label,
                    "agent": agent,
                    "condition": cond,
                    "repetition": block,
                    "run_seed": _run_seed(seed, label),
                }
            )

    return {
        "name": name,
        "seed": seed,
        "conditions": list(conditions),
        "repetitions": dict(repetitions),
        "runs": runs,
    }


def plan_path(name: str, plans_dir: Path = PLANS_DIR) -> Path:
    return plans_dir / f"{name}.json"


def save_plan(plan: dict, path: Path, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists. Plans are a record of the experiment; use --force to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    labels = [r["label"] for r in plan["runs"]]
    if len(labels) != len(set(labels)):
        raise ValueError(f"{path} contains duplicate run labels.")
    return plan