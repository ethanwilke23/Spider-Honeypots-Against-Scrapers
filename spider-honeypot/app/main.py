"""
FastAPI application entry point.

Mounts the decoy site, the three honeypot routes, the page-event endpoint and
the request-logging middleware, and creates the database tables at start-up.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.db import Base, check_connection, engine, wait_for_database
from app.events import router as events_router
from app.honeypots.active import active_setting
from app.honeypots.routes import router as honeypots_router
from app.middleware import RequestLoggingMiddleware
from app.models import logging_models  # noqa: F401 (importing registers the models on Base)
from app.site.routes import router as site_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_for_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Spider Honeypot Research Testbed", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(site_router)
app.include_router(honeypots_router)
app.include_router(events_router)


@app.get("/health")
async def health() -> dict:
    try:
        await check_connection()
    except Exception as exc:  # report any connection failure as a 503
        raise HTTPException(status_code=503, detail=f"database unreachable: {exc}") from exc
    return {"status": "ok", "database": "reachable", "honeypot_variant": active_setting()}