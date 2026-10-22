"""
Experiment settings: which agents are run, under which conditions, and how.

A condition is a value of HONEYPOT_VARIANT. The three honeypot variants are
tested one at a time, plus a control with no honeypots.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANS_DIR = PROJECT_ROOT / "experiment" / "plans"
RESULTS_DIR = PROJECT_ROOT / "agent_runs" / "experiment"

CONDITIONS = ("semantic", "prompt_injection", "link_graph", "none")


@dataclass(frozen=True)
class AgentConfig:
    name: str
    module: str  # run with: python -m <module>
    extra_args: tuple[str, ...]
    default_repetitions: int
    timeout_seconds: int
    costs_money: bool = False
    uses_seed: bool = False  # pass the run's own seed to the agent as --seed

    def command(self, base_url: str, seed: int | None = None) -> list[str]:
        command = [sys.executable, "-m", self.module, "--base-url", base_url, *self.extra_args]
        if self.uses_seed and seed is not None:
            command += ["--seed", str(seed)]
        return command


AGENTS: dict[str, AgentConfig] = {
    "playwright_baseline": AgentConfig(
        name="playwright_baseline",
        module="agents.playwright_baseline.run",
        extra_args=(),
        default_repetitions=10,
        timeout_seconds=300,
    ),
    # The same crawler with robots.txt ignored, as a traditional scraper that
    # does not honour it would behave. The link-graph trap is disallowed in
    # robots.txt, so this is the configuration that can reach it mechanically.
    "playwright_ignore_robots": AgentConfig(
        name="playwright_ignore_robots",
        module="agents.playwright_baseline.run",
        extra_args=("--ignore-robots",),
        default_repetitions=10,
        timeout_seconds=300,
    ),
    # Crawl4AI is run in both input modes. The markdown mode removes HTML
    # comments, so the prompt-injection trap can only be seen in the html mode.
    "crawl4ai_markdown": AgentConfig(
        name="crawl4ai_markdown",
        module="agents.crawl4ai_scraper.run",
        extra_args=("--input-format", "markdown"),
        default_repetitions=10,
        timeout_seconds=1800,
    ),
    "crawl4ai_html": AgentConfig(
        name="crawl4ai_html",
        module="agents.crawl4ai_scraper.run",
        extra_args=("--input-format", "html"),
        default_repetitions=10,
        timeout_seconds=1800,
    ),
    # Scripted browsing that behaves like a person; used to measure false positives.
    "human_baseline": AgentConfig(
        name="human_baseline",
        module="agents.human_baseline.run",
        extra_args=(),
        default_repetitions=10,
        timeout_seconds=600,
        uses_seed=True,
    ),
    "claude_computer_use": AgentConfig(
        name="claude_computer_use",
        # Runs in Docker: a real browser window on a virtual screen (see docker/claude-desktop/).
        module="agents.claude_computer_use.docker_run",
        extra_args=("--require-image", "--confirm-spend", "--max-iterations", "15"),
        default_repetitions=5,
        timeout_seconds=900,
        costs_money=True,
    ),
    # The same model as claude_computer_use, but it reads each page as text with the link
    # addresses instead of looking at screenshots, so the two differ only in perception.
    "claude_text_browser": AgentConfig(
        name="claude_text_browser",
        module="agents.claude_text_browser.run",
        extra_args=("--confirm-spend", "--max-iterations", "15"),
        default_repetitions=5,
        timeout_seconds=900,
        costs_money=True,
    ),
}

# Supplementary agents (protocol version 1.8). They are NOT part of AGENTS, so a default plan, and the 240-run main plan
# that can be regenerated from the frozen seed, are exactly as before. Name them with --agents to use them.
SUPPLEMENTARY_AGENTS: dict[str, AgentConfig] = {
    # Crawl4AI as in the main run, except that the model fills a one-field "summary" schema (see
    # agents/crawl4ai_scraper/scraper.py) instead of inferring its own, so the instruction on the
    # prompt-injection page has somewhere to be obeyed.
    "crawl4ai_markdown_summary": AgentConfig(
        name="crawl4ai_markdown_summary",
        module="agents.crawl4ai_scraper.run",
        extra_args=("--input-format", "markdown", "--summary"),
        default_repetitions=10,
        timeout_seconds=1800,
    ),
    "crawl4ai_html_summary": AgentConfig(
        name="crawl4ai_html_summary",
        module="agents.crawl4ai_scraper.run",
        extra_args=("--input-format", "html", "--summary"),
        default_repetitions=10,
        timeout_seconds=1800,
    ),
}


def agent_config(name: str) -> AgentConfig:
    """The settings of a main or supplementary agent."""
    if name in AGENTS:
        return AGENTS[name]
    return SUPPLEMENTARY_AGENTS[name]


def known_agents() -> list[str]:
    return list(AGENTS) + [n for n in SUPPLEMENTARY_AGENTS if n not in AGENTS]


DEFAULT_PORT = 8000
DEFAULT_SEED = 700