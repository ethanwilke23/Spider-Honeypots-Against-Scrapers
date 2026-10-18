"""
Command-line entry point for the Crawl4AI harness.

Setup:
    pip install crawl4ai
    crawl4ai-setup            # run crawl4ai-doctor if pages still fail to load
    Install Ollama (https://ollama.com/download), then: ollama pull llama3.2
    Make sure Ollama is running (`ollama serve`, or open the app).

Usage (the server and Ollama must already be running):
    python -m agents.crawl4ai_scraper.run
    python -m agents.crawl4ai_scraper.run --input-format html --max-pages 5

Each run writes agent_runs/crawl4ai/<input_format>_<timestamp>.json, so
markdown and html runs are easy to tell apart.

Crawl4AI does not expose the browser's cookies, so its runs cannot be
joined to the server logs by session_id. Join them by time window instead.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from agents.crawl4ai_scraper.scraper import DEFAULT_OLLAMA_BASE_URL, run_crawl
from agents.shared.record_checks import crawl4ai_problem

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "agent_runs" / "crawl4ai"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Crawl4AI harness against the testbed.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--model",
        default="llama3.2",
        help="Ollama model tag, e.g. llama3.2 or mistral. It must already be pulled (`ollama pull <model>`).",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help="Only needed if Ollama is not running on its default port.",
    )
    parser.add_argument(
        "--input-format",
        default="markdown",
        choices=["markdown", "html"],
        help="What the model reads: the page markdown or the raw HTML (see scraper.py).",
    )
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--max-depth", type=int, default=4)
    args = parser.parse_args()

    result = asyncio.run(
        run_crawl(
            base_url=args.base_url,
            model=args.model,
            ollama_base_url=args.ollama_base_url,
            input_format=args.input_format,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
        )
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"{args.input_format}_{timestamp}.json"
    record = {
        "agent": "crawl4ai",
        "run_at": timestamp,
        "base_url": result.base_url,
        "task_instruction": result.task_instruction,
        "input_format": result.input_format,
        "model": args.model,
        "pages_visited": len(result.pages),
        "pages": [dataclasses.asdict(p) for p in result.pages],
    }
    out_path.write_text(json.dumps(record, indent=2))

    problem = crawl4ai_problem(record["pages"])
    print(f"Visited {len(result.pages)} pages (input_format={result.input_format}).")
    for p in result.pages:
        line = f"  {p.url} (success={p.success})"
        if not p.success and p.error_message:
            line += f"\n    error: {p.error_message}"
        print(line)
    if problem:
        # No "Run record written" line, so the scheduler marks the run as failed and it can be rerun.
        print(f"INVALID RUN: {problem}. The record was saved to {out_path} for inspection.")
        raise SystemExit(3)
    print(f"Run record written to {out_path}")


if __name__ == "__main__":
    main()