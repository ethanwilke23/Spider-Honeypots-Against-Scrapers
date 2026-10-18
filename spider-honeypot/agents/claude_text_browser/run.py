"""
Command-line entry point for Claude with the text browser (a paid run is opt-in).

    python -m agents.claude_text_browser.run --env-check
        Free. Opens the homepage and prints exactly what the model would be shown. No API call.

    python -m agents.claude_text_browser.run --confirm-spend --max-iterations 3
        A real, paid run. Needs `pip install anthropic` and the ANTHROPIC_API_KEY environment variable.

A real run writes a JSON record, including the transcript, to
agent_runs/claude_text_browser/<timestamp>.json. Its session_id joins to the server logs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agents.claude_text_browser.agent_loop import DEFAULT_MODEL, SpendNotConfirmedError, run_agent
from agents.claude_text_browser.browser import TextBrowser

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "agent_runs" / "claude_text_browser"

NO_SPEND_MESSAGE = """\
Nothing was run and nothing was spent.

To see what the model would be shown (free, no API key):

    python -m agents.claude_text_browser.run --env-check

To do the real PAID run (only when you are ready to spend):

    python -m agents.claude_text_browser.run --confirm-spend --max-iterations 3
"""


async def env_check(base_url: str) -> None:
    browser = TextBrowser(base_url)
    try:
        print(await browser.start())
        print("\n--- opening the Blog link, then going back, then an outside address ---")
        number = next((l.number for _, l in browser._links if l.text.lower() == "blog"), 1)
        print((await browser.open_link(number))[:300])
        print("Back:", (await browser.go_back()).splitlines()[0])
        try:
            await browser.open_url("http://example.com/")
            print("Outside address: NOT blocked (this is a problem)")
        except ValueError as exc:
            print(f"Outside address blocked: {exc}")
        print(f"\nSession cookie (hp_session): {await browser.get_session_cookie()}")
        print("Environment OK.")
    finally:
        await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude with a text browser (paid run is opt-in).")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-iterations", type=int, default=15)
    parser.add_argument("--env-check", action="store_true", help="Free: show the page view the model receives (no API call).")
    parser.add_argument("--confirm-spend", action="store_true", help="REQUIRED for a real run: it makes paid API calls.")
    args = parser.parse_args()

    if args.env_check:
        asyncio.run(env_check(args.base_url))
        return 0
    if not args.confirm_spend:
        print(NO_SPEND_MESSAGE)
        return 2

    try:
        transcript = asyncio.run(run_agent(base_url=args.base_url, model=args.model, max_iterations=args.max_iterations, confirm_spend=True))
    except SpendNotConfirmedError as exc:  # cannot happen from the command line; kept as a second lock
        print(exc)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"{timestamp}.json"
    record = {
        "agent": "claude-text-browser",
        "run_at": timestamp,
        "base_url": transcript.base_url,
        "task_instruction": transcript.task_instruction,
        "model": transcript.model,
        "session_id": transcript.session_id,
        "environment": transcript.environment,
        "final_url": transcript.final_url,
        "iterations_used": transcript.iterations_used,
        "pages_viewed": transcript.pages_viewed,
        "final_text": transcript.final_text,
        "turns": transcript.turns,
    }
    out_path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

    print(f"Finished after {transcript.iterations_used} iteration(s). Session: {transcript.session_id}")
    print(f"Final response: {transcript.final_text}")
    print(f"Run record written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())