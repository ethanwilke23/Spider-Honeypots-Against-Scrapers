"""
Checks that an agent's run record shows a run that actually took place.

An agent can exit normally and still have done nothing: Crawl4AI, for example,
returns "failed" pages (and exits with code 0) when its own scheduler judges
that the computer is short of memory. Counting such a run as "the agent did not
find the trap" would be wrong, so the harness and the scheduler both use these
checks to mark the run as failed so that it is rerun.

Each function returns a short description of the problem, or None if the record
looks like a real run. They work on the plain dict that is saved as the record.
"""
from __future__ import annotations

MEMORY_PRESSURE_TEXT = "memory pressure"


def crawl4ai_problem(pages: list[dict]) -> str | None:
    """pages: the "pages" list of a Crawl4AI record (each has url, success, error_message)."""
    if not pages:
        return "the crawl returned no pages"
    memory_failures = [p for p in pages if MEMORY_PRESSURE_TEXT in (p.get("error_message") or "")]
    if memory_failures:
        return (
            f"{len(memory_failures)} of {len(pages)} page(s) were not fetched because Crawl4AI judged the computer "
            "to be short of memory"
        )
    if not pages[0].get("success"):
        return f"the start page was not fetched: {(pages[0].get('error_message') or 'no error given')[:120]}"
    if not any(p.get("success") for p in pages):
        return "no page was fetched successfully"
    return None


def record_problem(agent: str, record: dict) -> str | None:
    """The problem with a saved run record for the named agent (see experiment/config.py), if any."""
    if agent.startswith("crawl4ai"):
        return crawl4ai_problem(record.get("pages", []))
    if agent.startswith("playwright") and record.get("pages_visited") == 0:
        return "the crawler visited no pages"
    if agent in ("claude_computer_use", "claude_text_browser") and record.get("iterations_used") == 0:
        return "the agent made no model call"
    return None