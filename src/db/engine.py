"""Database engine and schema bootstrap."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, connect_args=connect_args)
    return _engine


def init_db() -> None:
    """Create tables if missing (SQLite-first equivalent of an initial migration)."""
    from src.db import models  # noqa: F401 — register models
    from src.db.models import Base

    settings.ensure_data_dirs()
    Base.metadata.create_all(bind=get_engine())
