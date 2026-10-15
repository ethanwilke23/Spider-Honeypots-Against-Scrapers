"""
Clearing the server logs and exporting each run's server-side records.

The server logs every request. Because the scheduler runs one agent at a time
against its own server, all requests between a run's start and finish times
belong to that run. Each export file holds those requests, flagged by whether
they came from the agent's own session (the Playwright baseline also fetches
robots.txt in a separate one-request session, which is kept but flagged).
"""
from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from experiment.config import RESULTS_DIR
from experiment.runner import load_manifest, manifest_path

# A request is logged before its response is sent, so the end of the window
# only needs a small margin.
WINDOW_MARGIN = timedelta(seconds=1)

SUMMARY_COLUMNS = [
    "label", "agent", "condition", "repetition", "requests", "agent_session_requests",
    "trap_hits", "first_trap_hit_at", "max_graph_depth", "unexpected_trap_hits",
]


# Pure helpers (no database)

def run_window(entry: dict) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(entry["started_at"])
    end = datetime.fromisoformat(entry["finished_at"]) + WINDOW_MARGIN
    return start, end


def build_export(entry: dict, rows: list[dict]) -> dict:
    """rows: one dict per request, with the trap fields, oldest first."""
    agent_session = entry.get("session_id")
    requests = [{**r, "in_agent_session": (r["session_id"] == agent_session) if agent_session else None} for r in rows]
    hits = [r for r in requests if r["trap_variant"]]
    unexpected = [r["id"] for r in hits if r["trap_variant"] != _variant_id_for(entry["condition"])]
    start, end = run_window(entry)
    return {
        "label": entry["label"],
        "agent": entry["agent"],
        "condition": entry["condition"],
        "repetition": entry["repetition"],
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "agent_session_id": agent_session,
        "request_count": len(requests),
        "trap_hit_count": len(hits),
        "unexpected_trap_hit_request_ids": unexpected,
        "requests": requests,
    }


def _variant_id_for(condition: str) -> str | None:
    """The variant_id the server logs for a condition (None for the control)."""
    from app.honeypots.specs import DYNAMIC_LINK_GRAPH_TRAP, PROMPT_INJECTION_TRAP, SEMANTIC_TRAP

    return {
        "semantic": SEMANTIC_TRAP.variant_id,
        "prompt_injection": PROMPT_INJECTION_TRAP.variant_id,
        "link_graph": DYNAMIC_LINK_GRAPH_TRAP.variant_id,
    }.get(condition)


def summary_row(export: dict) -> dict:
    hits = [r for r in export["requests"] if r["trap_variant"]]
    depths = [r["graph_depth"] for r in hits if r["graph_depth"] is not None]
    return {
        "label": export["label"],
        "agent": export["agent"],
        "condition": export["condition"],
        "repetition": export["repetition"],
        "requests": export["request_count"],
        "agent_session_requests": sum(1 for r in export["requests"] if r["in_agent_session"]),
        "trap_hits": export["trap_hit_count"],
        "first_trap_hit_at": hits[0]["timestamp"] if hits else "",
        "max_graph_depth": max(depths) if depths else "",
        "unexpected_trap_hits": len(export["unexpected_trap_hit_request_ids"]),
    }


# Database access

async def count_rows() -> dict[str, int]:
    from app.db import AsyncSessionLocal
    from app.models.logging_models import RequestLog, TrapHitEvent

    async with AsyncSessionLocal() as db:
        requests = (await db.execute(select(func.count()).select_from(RequestLog))).scalar_one()
        hits = (await db.execute(select(func.count()).select_from(TrapHitEvent))).scalar_one()
    return {"request_log": requests, "trap_hit_event": hits}


async def reset_logs() -> None:
    from app.db import AsyncSessionLocal
    from app.models.logging_models import RequestLog, TrapHitEvent

    async with AsyncSessionLocal() as db:
        await db.execute(delete(TrapHitEvent))
        await db.execute(delete(RequestLog))
        await db.commit()


async def fetch_window(start: datetime, end: datetime) -> list[dict]:
    from app.db import AsyncSessionLocal
    from app.models.logging_models import RequestLog

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RequestLog)
            .options(selectinload(RequestLog.trap_hit))
            .where(RequestLog.timestamp >= start, RequestLog.timestamp <= end)
            .order_by(RequestLog.timestamp, RequestLog.id)
        )
        rows = []
        for r in result.scalars():
            rows.append(
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "timestamp": r.timestamp.isoformat(),
                    "method": r.method,
                    "path": r.path,
                    "user_agent": r.user_agent,
                    "trap_variant": r.trap_hit.variant_id if r.trap_hit else None,
                    "graph_depth": r.trap_hit.graph_depth if r.trap_hit else None,
                }
            )
    return rows


async def export_plan(plan_name: str, results_dir: Path = RESULTS_DIR, only_missing: bool = False) -> list[dict]:
    """Write server_records/<label>.json for every finished run, plus summary.csv. Returns the summary rows."""
    manifest_file = manifest_path(plan_name, results_dir)
    manifest = load_manifest(manifest_file, plan_name)
    out_dir = manifest_file.parent / "server_records"
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for entry in sorted(manifest["runs"].values(), key=lambda e: e["order"]):
        if entry["status"] != "done":
            continue
        target = out_dir / f"{entry['label']}.json"
        if only_missing and target.exists():
            export = json.loads(target.read_text(encoding="utf-8"))
        else:
            start, end = run_window(entry)
            export = build_export(entry, await fetch_window(start, end))
            target.write_text(json.dumps(export, indent=2), encoding="utf-8")
        summaries.append(summary_row(export))

    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(summaries)
    return summaries


def run_async(coro):
    """Run one coroutine and release the database connections afterwards."""
    from app.db import engine

    engine.echo = False  # the app logs every SQL statement in development; keep this command readable

    async def wrapper():
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(wrapper())