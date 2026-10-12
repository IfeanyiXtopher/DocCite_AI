"""Guest inactivity purge — never touches logged-in users."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import Session as AuthSession
from src.services.library import clear_library

logger = logging.getLogger(__name__)


def purge_expired_guests(
    db: Session,
    *,
    ttl_hours: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Delete guest owners idle longer than TTL (files + vectors + DB rows)."""
    ttl = settings.guest_inactivity_ttl_hours if ttl_hours is None else ttl_hours
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=ttl)

    expired = (
        db.query(AuthSession)
        .filter(AuthSession.is_guest.is_(True), AuthSession.last_active_at < cutoff)
        .all()
    )
    purged = 0
    for session in expired:
        owner_id = session.owner_id
        logger.info("Purging guest owner=%s last_active=%s", owner_id, session.last_active_at)
        clear_library(db, owner_id)
        # remove leftover owner upload dir if empty
        safe = owner_id.replace(":", "_").replace("/", "_")
        owner_dir = settings.upload_dir / safe
        if owner_dir.is_dir() and not any(owner_dir.iterdir()):
            owner_dir.rmdir()
        db.delete(session)
        purged += 1
    db.commit()
    return {"guests_purged": purged, "ttl_hours": ttl}
