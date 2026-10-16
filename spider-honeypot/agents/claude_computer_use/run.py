"""
Command-line entry point for the Claude computer-use harness.

The harness is built but has not yet been used against the paid API. There are
two environments. The default is a bare headless browser page with no address
bar. With --desktop Claude controls a real browser window on a virtual screen,
with a tab bar and an address bar; this needs Xvfb and is meant to run inside
the Docker image (see README.md), which the experiment
scheduler does through `python -m agents.claude_computer_use.docker_run`.

It has three modes:

    python -m agents.claude_computer_use.run
        Does nothing and prints how to proceed.

    python -m agents.claude_computer_use.run --env-check
        Free. Opens the browser on the running server and saves two
        screenshots to agent_runs/claude_computer_use/. No API call is made.
        The visit is logged by the server like any other request. With
        --desktop the screenshots show the whole browser window.

    python -m agents.claude_computer_use.run --confirm-spend --max-iterations 3
        A real, paid run. Needs `pip install anthropic` and the
        ANTHROPIC_API_KEY environment variable.

A real run writes a JSON record, including the full transcript, to
agent_runs/claude_computer_use/<timestamp>.json. Its session_id joins to
the server logs. Each iteration resends the whole conversation plus a new
screenshot, so the cost grows quickly with --max-iterations; start small.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from agents.claude_computer_use.agent_loop import DEFAULT_MODEL, SpendNotConfirmedError, run_agent
from agents.claude_computer_use.environment import ComputerEnvironment

# AGENT_OUTPUT_DIR lets the Docker wrapper point records at a mounted folder.
OUTPUT_DIR = Path(os.environ.get("AGENT_OUTPUT_DIR") or Path(__file__).resolve().parents[2] / "agent_runs" / "claude_computer_use")

NO_SPEND_MESSAGE = """\
Nothing was run and nothing was spent.

The Claude computer-use harness is built but switched off. To check that the
browser environment works (free, no API key):

    python -m agents.claude_computer_use.run --env-check

To do the real PAID run (only when you are ready to spend):

    python -m agents.claude_computer_use.run --confirm-spend --max-iterations 3
"""


async def env_check(base_url: str, desktop: bool = False) -> None:
    """Free check of the browser environment. No API call is made."""
    import base64

    if desktop:
        from agents.claude_computer_use.desktop import DesktopEnvironment

        env = DesktopEnvironment()
    else:
        env = ComputerEnvironment()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    await env.start(base_url)
    try:
        first = OUTPUT_DIR / "env_check_1_start.png"
        first.write_bytes(base64.b64decode(await env.screenshot_base64()))

        await env.execute("scroll", {"coordinate": [640, 400], "scroll_direction": "down", "scroll_amount": 3})
        second = OUTPUT_DIR / "env_check_2_scrolled.png"
        second.write_bytes(base64.b64decode(await env.screenshot_base64()))

        print(f"Start page: {env.current_url}")
        if desktop:
            # Prove that typing an address works and that the site is the only reachable place.
            await env.execute("key", {"text": "ctrl+l"})
            await env.execute("type", {"text": base_url.rstrip("/") + "/blog\n"})
            third = OUTPUT_DIR / "env_check_3_typed_address.png"
            third.write_bytes(base64.b64decode(await env.screenshot_base64()))
            print(f"Typed address worked: {env.current_url.endswith('/blog')}  (now at {env.current_url})")
            await env.execute("key", {"text": "ctrl+l"})
            await env.execute("type", {"text": "http://example.com/\n"})
            await asyncio.sleep(1.5)
            blocked = env.current_url.startswith("chrome-error://")
            print(f"Other websites blocked: {blocked}  (now at {env.current_url})")
        print(f"Session cookie (hp_session): {await env.get_session_cookie()}")
        print(f"Screenshots: {first}  and  {second}" + (f"  and  {third}" if desktop else ""))
        print("Environment OK.")
    finally:
        await env.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude computer-use harness (paid run is opt-in).")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=15,
        help="Maximum number of agent-loop turns.",
    )
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="Use the real browser window on a virtual screen (needs Xvfb; use the Docker image).",
    )
    parser.add_argument("--env-check", action="store_true", help="Free: check the browser environment only (no API call).")
    parser.add_argument(
        "--confirm-spend",
        action="store_true",
        help="REQUIRED for a real run. Acknowledges that this makes paid Anthropic API calls.",
    )
    args = parser.parse_args()

    if args.env_check:
        asyncio.run(env_check(args.base_url, desktop=args.desktop))
        return 0

    if not args.confirm_spend:
        print(NO_SPEND_MESSAGE)
        return 2

    try:
        transcript = asyncio.run(
            run_agent(
                base_url=args.base_url,
                model=args.model,
                max_iterations=args.max_iterations,
                confirm_spend=True,
                desktop=args.desktop,
            )
        )
    except SpendNotConfirmedError as exc:  # cannot happen from the command line; kept as a second lock
        print(exc)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"{timestamp}.json"
    record = {
        "agent": "claude-computer-use",
        "run_at": timestamp,
        "base_url": transcript.base_url,
        "task_instruction": transcript.task_instruction,
        "model": transcript.model,
        "session_id": transcript.session_id,
        "environment": transcript.environment,
        "final_url": transcript.final_url,
        "iterations_used": transcript.iterations_used,
        "final_text": transcript.final_text,
        "turns": transcript.turns,
    }
    out_path.write_text(json.dumps(record, indent=2, default=str))

    print(f"Finished after {transcript.iterations_used} iteration(s). Session: {transcript.session_id}")
    print(f"Final response: {transcript.final_text}")
    print(f"Run record written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())