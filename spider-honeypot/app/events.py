"""
Receives the page events posted by the script in the page layout.

A view event is sent when a page loads, a click event for each click, and a
leave event when the visitor moves away (with time on the page, how far it was
scrolled, and counts of mouse movements and key presses). Events are stored
against the visitor's session cookie.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from app.db import AsyncSessionLocal
from app.models.logging_models import ClientEvent
from app.site.layout import EVENTS_PATH

SESSION_COOKIE_NAME = "hp_session"
EVENT_TYPES = {"view", "click", "leave"}
MAX_BODY_BYTES = 4096

router = APIRouter()


def parse_event(body: bytes) -> dict | None:
    """Return a cleaned event dict, or None if the body is not a valid event."""
    if len(body) > MAX_BODY_BYTES:
        return None
    try:
        raw = json.loads(body)
    except ValueError:
        return None
    if not isinstance(raw, dict) or raw.get("type") not in EVENT_TYPES:
        return None
    path = raw.get("path")
    if not isinstance(path, str):
        return None
    data = raw.get("data")
    client_time = None
    t = raw.get("t")
    if isinstance(t, (int, float)) and t > 0:
        try:
            client_time = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            client_time = None
    return {
        "event_type": raw["type"],
        "path": path[:512],
        "client_time": client_time,
        "payload": data if isinstance(data, dict) else {},
    }


@router.post(EVENTS_PATH, status_code=204)
async def receive_event(request: Request) -> Response:
    event = parse_event(await request.body())
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if event is not None and session_id:
        async with AsyncSessionLocal() as db:
            db.add(ClientEvent(session_id=session_id, **event))
            await db.commit()
    return Response(status_code=204)