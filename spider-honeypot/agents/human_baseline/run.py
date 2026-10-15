"""
Command-line entry point for the synthetic human-behaviour baseline.

Usage (the server must already be running):
    python -m agents.human_baseline.run
    python -m agents.human_baseline.run --seed 42 --time-scale 0.2 --headed

--time-scale shortens or lengthens the pauses (0.2 means five times faster).
The same seed always makes the same choices. Each run writes a JSON record to
agent_runs/human_baseline/<timestamp>.json; its session_id matches the hp_session
cookie, so it can be joined to the server logs.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.human_baseline.simulator import run_session

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "agent_runs" / "human_baseline"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the synthetic human-behaviour baseline against the testbed.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--seed", type=int, help="Random seed. Default: taken from the clock and recorded.")
    parser.add_argument("--time-scale", type=float, default=1.0, help="Multiplies every pause. Default: 1.0.")
    parser.add_argument("--headed", action="store_true", help="Show the browser window.")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else int(time.time())
    result = run_session(args.base_url, seed=seed, time_scale=args.time_scale, headless=not args.headed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"{timestamp}.json"
    record = {
        "agent": "human-baseline-synthetic",
        "run_at": timestamp,
        "base_url": result.base_url,
        "seed": result.seed,
        "time_scale": result.time_scale,
        "profile": result.profile,
        "session_id": result.session_id,
        "target_pages": result.target_pages,
        "pages_viewed": len(result.views),
        "views": [dataclasses.asdict(v) for v in result.views],
    }
    out_path.write_text(json.dumps(record, indent=2))

    print(f"Viewed {len(result.views)} pages (seed {seed}). Session: {result.session_id}")
    print(f"Run record written to {out_path}")


if __name__ == "__main__":
    main()