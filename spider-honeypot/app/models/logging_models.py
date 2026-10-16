"""
ORM models for request logging.

RequestLog holds one row per HTTP request served. TrapHitEvent holds one
row per request that matched a honeypot path, linked to its RequestLog row.
ClientEvent holds one row per event reported by the script on each page
(view, click, leave).
Tables are created at start-up with Base.metadata.create_all() (see
app/main.py); there are no migrations.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RequestLog(Base):
    """One row per HTTP request served by the app."""

    __tablename__ = "request_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(512), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    client_host: Mapped[str | None] = mapped_column(String(64), nullable=True)

    trap_hit: Mapped["TrapHitEvent | None"] = relationship(
        back_populates="request", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_request_log_session_timestamp", "session_id", "timestamp"),)


class TrapHitEvent(Base):
    """
    One row per request that matched a honeypot path. Kept separate from
    RequestLog so trap-specific fields (which variant, how deep into a
    link chain) do not clutter every request row.
    """

    __tablename__ = "trap_hit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("request_log.id"), unique=True)
    variant_id: Mapped[str] = mapped_column(String(64), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    graph_depth: Mapped[int | None] = mapped_column(
        nullable=True, doc="Populated only for dynamic-link-graph-trap hits."
    )

    request: Mapped[RequestLog] = relationship(back_populates="trap_hit")


class ClientEvent(Base):
    """One row per event reported by the browser (see app/events.py)."""

    __tablename__ = "client_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(512))
    client_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


def new_session_id() -> str:
    """Return a random session id (UUID hex). It contains no personal information."""
    return uuid.uuid4().hex