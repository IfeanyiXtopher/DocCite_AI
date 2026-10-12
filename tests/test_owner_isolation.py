"""Owner scoping: guests/users cannot see each other's data."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.db.engine import init_db
from src.db.session import session_scope
from src.services.library import clear_library, ingest_for_owner, list_documents
from src.store.chroma_store import ChromaStore


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    chroma_dir = tmp_path / "chroma"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "chroma_dir", chroma_dir)
    monkeypatch.setattr(settings, "upload_dir", upload_dir)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_secret", "test-secret")
    # Reset engine singleton
    import src.db.engine as eng

    eng._engine = None
    init_db()

    from api.main import app

    with TestClient(app) as client:
        yield client

    eng._engine = None


def test_guest_sessions_are_isolated(api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Avoid live embeddings: stub ChromaStore.add_chunks / query / delete
    added: dict[str, list[str]] = {}

    def fake_add(self, chunks, *, owner_id=None):  # noqa: ANN001
        added.setdefault(owner_id, [])
        added[owner_id].extend([c.chunk_id for c in chunks])

    def fake_count(self, *, owner_id=None, doc_ids=None):  # noqa: ANN001
        if owner_id is None:
            return sum(len(v) for v in added.values())
        return len(added.get(owner_id, []))

    def fake_query(self, query_text, k=None, *, owner_id=None, doc_ids=None):  # noqa: ANN001
        from src.store.chroma_store import QueryHit

        if not owner_id or owner_id not in added:
            return []
        return [
            QueryHit(
                chunk_id=added[owner_id][0],
                text=f"secret for {owner_id}",
                metadata={"owner_id": owner_id, "filename": "a.txt", "has_page": False, "page": 0},
                score=0.1,
            )
        ]

    def fake_delete_doc(self, doc_id, *, owner_id=None):  # noqa: ANN001
        return None

    def fake_delete_owner(self, owner_id):  # noqa: ANN001
        added.pop(owner_id, None)

    def fake_get_chunks(self, doc_id, *, owner_id=None):  # noqa: ANN001
        return []

    monkeypatch.setattr(ChromaStore, "add_chunks", fake_add)
    monkeypatch.setattr(ChromaStore, "count", fake_count)
    monkeypatch.setattr(ChromaStore, "query", fake_query)
    monkeypatch.setattr(ChromaStore, "delete_by_doc_id", fake_delete_doc)
    monkeypatch.setattr(ChromaStore, "delete_by_owner", fake_delete_owner)
    monkeypatch.setattr(ChromaStore, "get_chunks_for_doc", fake_get_chunks)

    g1 = api_client.post("/auth/guest").json()
    g2 = api_client.post("/auth/guest").json()
    assert g1["owner_id"] != g2["owner_id"]
    assert g1["is_guest"] is True

    txt = tmp_path / "note.txt"
    txt.write_text("Guest one private token GUEST-ONE-TOKEN only here.\n" * 2, encoding="utf-8")

    r1 = api_client.post(
        "/documents/upload",
        headers={"X-DocCite-Session": g1["token"]},
        files={"file": ("note.txt", txt.read_bytes(), "text/plain")},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "ready"

    docs2 = api_client.get("/documents", headers={"X-DocCite-Session": g2["token"]})
    assert docs2.status_code == 200
    assert docs2.json() == []

    # Guest2 cannot ask without attaching docs to a chat
    thread2 = api_client.post(
        "/chats/threads",
        headers={"X-DocCite-Session": g2["token"]},
    ).json()
    ask2 = api_client.post(
        "/ask",
        headers={"X-DocCite-Session": g2["token"]},
        json={"question": "GUEST-ONE-TOKEN", "thread_id": thread2["id"]},
    )
    assert ask2.status_code == 200, ask2.text
    body = ask2.json()["answer"]
    assert body["refused"] is True
    assert "attach" in body["text"].lower()


def test_logged_in_clear_only_own_data(api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store_data: dict[str, int] = {}

    def fake_add(self, chunks, *, owner_id=None):  # noqa: ANN001
        store_data[owner_id] = store_data.get(owner_id, 0) + len(chunks)

    def fake_count(self, *, owner_id=None, doc_ids=None):  # noqa: ANN001
        if owner_id is None:
            return sum(store_data.values())
        return store_data.get(owner_id, 0)

    def fake_delete_owner(self, owner_id):  # noqa: ANN001
        store_data.pop(owner_id, None)

    def fake_delete_doc(self, doc_id, *, owner_id=None):  # noqa: ANN001
        return None

    monkeypatch.setattr(ChromaStore, "add_chunks", fake_add)
    monkeypatch.setattr(ChromaStore, "count", fake_count)
    monkeypatch.setattr(ChromaStore, "delete_by_owner", fake_delete_owner)
    monkeypatch.setattr(ChromaStore, "delete_by_doc_id", fake_delete_doc)
    monkeypatch.setattr(ChromaStore, "get_chunks_for_doc", lambda *a, **k: [])
    monkeypatch.setattr(ChromaStore, "query", lambda *a, **k: [])

    a = api_client.post(
        "/auth/register", json={"email": "a@example.com", "password": "password123"}
    ).json()
    b = api_client.post(
        "/auth/register", json={"email": "b@example.com", "password": "password123"}
    ).json()

    txt = tmp_path / "sharedname.txt"
    txt.write_text("User library text for isolation testing here.\n", encoding="utf-8")

    assert (
        api_client.post(
            "/documents/upload",
            headers={"X-DocCite-Session": a["token"]},
            files={"file": ("sharedname.txt", txt.read_bytes(), "text/plain")},
        ).status_code
        == 200
    )
    assert (
        api_client.post(
            "/documents/upload",
            headers={"X-DocCite-Session": b["token"]},
            files={"file": ("sharedname.txt", txt.read_bytes(), "text/plain")},
        ).status_code
        == 200
    )

    cleared = api_client.delete("/library", headers={"X-DocCite-Session": a["token"]})
    assert cleared.status_code == 200
    assert cleared.json()["documents_removed"] == 1

    docs_a = api_client.get("/documents", headers={"X-DocCite-Session": a["token"]}).json()
    docs_b = api_client.get("/documents", headers={"X-DocCite-Session": b["token"]}).json()
    assert docs_a == []
    assert len(docs_b) == 1
