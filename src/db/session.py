"""DB session helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from src.db.engine import get_engine

SessionLocal = sessionmaker(autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    SessionLocal.configure(bind=get_engine())
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def session_scope() -> Session:
    SessionLocal.configure(bind=get_engine())
    return SessionLocal()
