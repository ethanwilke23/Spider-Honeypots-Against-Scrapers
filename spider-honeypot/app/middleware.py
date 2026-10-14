"""
Request-logging middleware.

Writes a RequestLog row for every request, and a TrapHitEvent row when the
path belongs to a honeypot. Each client receives a session cookie on its
first request, so one run's navigation can be reconstructed from the logs
without any cooperation from the client.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.db import AsyncSessionLocal
from app.honeypots.routes import graph_depth_for_path, is_honeypot_path
from app.models.logging_models import RequestLog, TrapHitEvent, new_session_id

SESSION_COOKIE_NAME = "hp_session"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        session_id = request.cookies.get(SESSION_COOKIE_NAME) or new_session_id()

        response = await call_next(request)

        if SESSION_COOKIE_NAME not in request.cookies:
            response.set_cookie(SESSION_COOKIE_NAME, session_id, httponly=True, samesite="lax")

        await self._log_request(request, session_id)
        return response

    async def _log_request(self, request: Request, session_id: str) -> None:
        path = request.url.path
        async with AsyncSessionLocal() as db:
            log_row = RequestLog(
                session_id=session_id,
                method=request.method,
                path=path,
                user_agent=request.headers.get("user-agent"),
                client_host=request.client.host if request.client else None,
            )
            db.add(log_row)
            await db.flush()  # assigns log_row.id, needed by the TrapHitEvent below

            variant_id = is_honeypot_path(path)
            if variant_id:
                db.add(
                    TrapHitEvent(
                        request_id=log_row.id,
                        variant_id=variant_id,
                        graph_depth=graph_depth_for_path(path),
                    )
                )

            await db.commit()