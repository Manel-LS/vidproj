"""SQLAlchemy engine, session factory and the declarative base."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generator

from sqlalchemy import DateTime, JSON, MetaData, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator
from sqlalchemy.pool import StaticPool

from app.core.config import settings

# Explicit naming so Alembic autogenerate produces stable constraint names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class UtcDateTime(TypeDecorator):
    """A timestamp that is always UTC, whatever the database underneath.

    MySQL's `DATETIME` has no time zone, so an aware datetime written to it comes
    back naive and the client reads it as local time — which would show every
    project as created hours ago. Storing UTC and re-attaching the zone on the way
    out makes SQLite, PostgreSQL and MySQL behave identically.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        # MySQL's DATETIME stores the wall clock verbatim and rejects an offset, so
        # hand it a naive value that is already UTC. SQLite and PostgreSQL both keep
        # the zone, so they get the aware value unchanged.
        if dialect.name in ("mysql", "mariadb"):
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class IdMixin:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)


def _build_engine():
    url = settings.resolved_database_url
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        kwargs: dict[str, Any] = {"connect_args": connect_args}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, future=True, **kwargs)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine

    kwargs: dict[str, Any] = {
        "future": True,
        "pool_pre_ping": True,   # a connection idle past wait_timeout is replaced, not raised
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,    # MySQL closes idle connections after 8h by default
    }
    if url.startswith(("mysql", "mariadb")):
        # utf8mb4 end to end: captions and hashtags contain emoji, and MySQL's `utf8`
        # is a three-byte encoding that would silently drop them.
        kwargs["connect_args"] = {"charset": "utf8mb4"}
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def session_scope() -> Session:
    """A session for background workers, which own their own lifecycle."""
    return SessionLocal()
