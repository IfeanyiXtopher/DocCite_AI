"""Guest TTL purge removes guest data; logged-in users survive."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config import settings
from src.db.engine import init_db
from src.db.models import DocumentRow, Session as AuthSession
from src.db.session import session_scope
from src.services.purge import purge_expired_guests
from src.store.chroma_store import ChromaStore


@pytest.fixture()
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "purge.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "guest_inactivity_ttl_hours", 24)
    import src.db.engine as eng

    eng._engine = None
    init_db()
    yield
    eng._engine = None


def test_purge_expired_guests_only(db_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    deleted_owners: list[str] = []

    def fake_delete_owner(self, owner_id):  # noqa: ANN001
        deleted_owners.append(owner_id)

    monkeypatch.setattr(ChromaStore, "delete_by_owner", fake_delete_owner)
    monkeypatch.setattr(ChromaStore, "count", lambda self, *, owner_id=None: 0)

    now = datetime.now(timezone.utc)
    db = session_scope()
    try:
        guest_old = AuthSession(
            id="g-old",
            token="tok-old",
            owner_id="guest:g-old",
            is_guest=True,
            created_at=now - timedelta(days=3),
            last_active_at=now - timedelta(hours=48),
        )
        guest_new = AuthSession(
            id="g-new",
            token="tok-new",
            owner_id="guest:g-new",
            is_guest=True,
            created_at=now,
            last_active_at=now,
        )
        user_sess = AuthSession(
            id="u1",
            token="tok-user",
            owner_id="user:u1",
            is_guest=False,
            created_at=now - timedelta(days=10),
            last_active_at=now - timedelta(days=10),
        )
        db.add_all([guest_old, guest_new, user_sess])
        # document for old guest
        doc_path = tmp_path / "uploads" / "guest_g-old"
        doc_path.mkdir(parents=True)
        f = doc_path / "x.txt"
        f.write_text("bye", encoding="utf-8")
        db.add(
            DocumentRow(
                id="d1",
                owner_id="guest:g-old",
                filename="x.txt",
                stored_path=str(f),
                file_type="txt",
                size_bytes=3,
                status="ready",
                chunk_count=1,
            )
        )
        db.commit()

        result = purge_expired_guests(db, now=now)
        assert result["guests_purged"] == 1
        assert "guest:g-old" in deleted_owners

        remaining = {s.owner_id for s in db.query(AuthSession).all()}
        assert "guest:g-old" not in remaining
        assert "guest:g-new" in remaining
        assert "user:u1" in remaining
        assert db.query(DocumentRow).filter(DocumentRow.owner_id == "guest:g-old").count() == 0
    finally:
        db.close()
