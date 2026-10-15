"""
Command-line entry point for the Playwright baseline crawl.

Usage (the server must already be running):
    python -m agents.playwright_baseline.run
    python -m agents.playwright_baseline.run --base-url http://127.0.0.1:8000 --headed

Setup:
    pip install playwright
    playwright install chromium

Each run writes a JSON record to agent_runs/playwright/<timestamp>.json.
Its session_id matches the hp_session cookie set by the server, so the run
can be joined to request_log and trap_hit_event by session_id.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from agents.playwright_baseline.crawler import crawl

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "agent_runs" / "playwright"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Playwright baseline crawl against the testbed.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--max-pages", type=int, default=60)
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Do not obey robots.txt (the baseline obeys it by default).",
    )
    parser.add_argument(
        "--headed", action="store_true", help="Show the browser window instead of running headless."
    )
    args = parser.parse_args()

    result = crawl(
        base_url=args.base_url,
        max_pages=args.max_pages,
        respect_robots_txt=not args.ignore_robots,
        headless=not args.headed,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"{timestamp}.json"
    record = {
        "agent": "playwright-baseline",
        "run_at": timestamp,
        "base_url": result.base_url,
        "session_id": result.session_id,
        "pages_visited": len(result.visited),
        "visited": [dataclasses.asdict(v) for v in result.visited],
        "skipped_disallowed": result.skipped_disallowed,
    }
    out_path.write_text(json.dumps(record, indent=2))

    print(f"Visited {len(result.visited)} pages. Session: {result.session_id}")
    print(f"Skipped (disallowed by robots.txt): {result.skipped_disallowed}")
    print(f"Run record written to {out_path}")


if __name__ == "__main__":
    main()