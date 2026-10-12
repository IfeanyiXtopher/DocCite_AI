"""Database engine and schema bootstrap."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import settings

_engine: Engine | None = None

# Lightweight SQLite column adds for existing local DBs (no Alembic yet).
_USER_PROFILE_COLUMNS = (
    ("display_name", "VARCHAR(120)"),
    ("title", "VARCHAR(160)"),
    ("company", "VARCHAR(160)"),
)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, connect_args=connect_args)
    return _engine


def _ensure_sqlite_user_profile_columns(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
        existing = {r[1] for r in rows}
        for name, col_type in _USER_PROFILE_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {col_type}"))


def init_db() -> None:
    """Create tables if missing (SQLite-first equivalent of an initial migration)."""
    from src.db import models  # noqa: F401 — register models
    from src.db.models import Base

    settings.ensure_data_dirs()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_user_profile_columns(engine)
