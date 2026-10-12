"""Owner-scoped library operations for the API (DB + Chroma + disk)."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import ChatMessage, ChatThread, DocumentRow, LibrarySummary
from src.ingest.chunk import chunk_document
from src.ingest.extract import ExtractError, detect_file_type, extract_file
from src.rag.qa import answer as rag_answer
from src.rag.retrieve import retrieve
from src.store.chroma_store import ChromaStore

logger = logging.getLogger(__name__)
MAX_FILE_BYTES = 25 * 1024 * 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_filename(name: str) -> str:
    return Path(name).name.replace("/", "_").replace("\\", "_")


def _owner_upload_dir(owner_id: str) -> Path:
    # Avoid path separators in owner ids
    safe = owner_id.replace(":", "_").replace("/", "_")
    path = settings.upload_dir / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_documents(db: Session, owner_id: str) -> list[DocumentRow]:
    return (
        db.query(DocumentRow)
        .filter(DocumentRow.owner_id == owner_id)
        .order_by(DocumentRow.filename)
        .all()
    )


def ingest_for_owner(
    db: Session,
    owner_id: str,
    source_path: Path,
    *,
    original_filename: str | None = None,
) -> DocumentRow:
    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"File not found: {source_path}")
    size = source_path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds 25 MB limit ({size} bytes).")

    filename = _safe_filename(original_filename or source_path.name)
    try:
        file_type = detect_file_type(Path(filename))
    except ExtractError as exc:
        raise ValueError(str(exc)) from exc

    store = ChromaStore()
    existing = (
        db.query(DocumentRow)
        .filter(DocumentRow.owner_id == owner_id, DocumentRow.filename == filename)
        .first()
    )
    if existing:
        store.delete_by_doc_id(existing.id, owner_id=owner_id)
        Path(existing.stored_path).unlink(missing_ok=True)
        db.delete(existing)
        db.commit()

    doc_id = str(uuid.uuid4())
    stored_path = _owner_upload_dir(owner_id) / f"{doc_id}_{filename}"
    shutil.copy2(source_path, stored_path)

    row = DocumentRow(
        id=doc_id,
        owner_id=owner_id,
        filename=filename,
        stored_path=str(stored_path),
        file_type=file_type,
        size_bytes=size,
        status="processing",
        uploaded_at=_utcnow(),
    )
    db.add(row)
    db.commit()

    try:
        extracted = extract_file(stored_path)
        chunks = chunk_document(extracted, doc_id=doc_id, filename=filename)
        for c in chunks:
            c.owner_id = owner_id
        store.add_chunks(chunks, owner_id=owner_id)
        row.page_count = extracted.page_count
        row.chunk_count = len(chunks)
        row.status = "ready"
        row.ingested_at = _utcnow()
        row.error = None
        db.add(row)
        # invalidate summary
        db.query(LibrarySummary).filter(LibrarySummary.owner_id == owner_id).delete()
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:  # noqa: BLE001
        logger.exception("Owner ingest failed owner=%s file=%s", owner_id, filename)
        try:
            store.delete_by_doc_id(doc_id, owner_id=owner_id)
        except Exception:  # noqa: BLE001
            pass
        stored_path.unlink(missing_ok=True)
        row.status = "failed"
        row.error = str(exc)
        db.add(row)
        db.commit()
        raise


def clear_library(db: Session, owner_id: str) -> dict[str, int]:
    store = ChromaStore()
    docs = list_documents(db, owner_id)
    for doc in docs:
        Path(doc.stored_path).unlink(missing_ok=True)
        db.delete(doc)
    store.delete_by_owner(owner_id)
    threads = db.query(ChatThread).filter(ChatThread.owner_id == owner_id).all()
    for thread in threads:
        db.delete(thread)
    db.query(LibrarySummary).filter(LibrarySummary.owner_id == owner_id).delete()
    db.commit()
    return {"documents_removed": len(docs), "chroma_remaining": store.count(owner_id=owner_id)}


def summarize_for_owner(db: Session, owner_id: str, *, force: bool = False) -> dict:
    from langchain_openai import ChatOpenAI

    ready = [d for d in list_documents(db, owner_id) if d.status == "ready"]
    if not ready:
        return {"text": "No documents uploaded.", "cached": False, "library_hash": ""}

    digest = hashlib.sha256(
        ",".join(sorted(d.id for d in ready)).encode("utf-8")
    ).hexdigest()[:16]
    cached = db.get(LibrarySummary, owner_id)
    if not force and cached and cached.library_hash == digest and cached.text:
        return {"text": cached.text, "cached": True, "library_hash": digest}

    store = ChromaStore()
    lines = ["Documents:"]
    for doc in ready:
        pages = doc.page_count if doc.page_count is not None else "n/a"
        lines.append(
            f"- {doc.filename} (type={doc.file_type}, pages={pages}, chunks={doc.chunk_count})"
        )
        chunks = store.get_chunks_for_doc(doc.id, owner_id=owner_id)
        if chunks:
            lines.append(f"  sample 1: {' '.join(chunks[0].text.split())[:500]}")
            if len(chunks) > 1:
                mid = chunks[len(chunks) // 2]
                lines.append(f"  sample 2: {' '.join(mid.text.split())[:500]}")

    llm = ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    response = llm.invoke(
        [
            (
                "system",
                "Summarize the user's document library in 5–8 bullets. "
                "Use only the provided samples. Do not invent facts.",
            ),
            ("human", "\n".join(lines) + "\n\nWrite the library summary bullets now."),
        ]
    )
    text = (getattr(response, "content", None) or str(response)).strip()
    row = cached or LibrarySummary(owner_id=owner_id)
    row.library_hash = digest
    row.text = text
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    return {"text": text, "cached": False, "library_hash": digest}


class OwnerStore:
    """ChromaStore facade that always filters by owner_id."""

    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id
        self._store = ChromaStore()

    def count(self) -> int:
        return self._store.count(owner_id=self.owner_id)

    def query(self, query_text: str, k: int | None = None):
        return self._store.query(query_text, k=k, owner_id=self.owner_id)


def ask_for_owner(
    db: Session,
    owner_id: str,
    question: str,
    *,
    thread_id: str | None = None,
) -> dict:
    store = OwnerStore(owner_id)
    result = rag_answer(question, store=store)  # type: ignore[arg-type]

    thread: ChatThread | None = None
    if thread_id:
        thread = (
            db.query(ChatThread)
            .filter(ChatThread.id == thread_id, ChatThread.owner_id == owner_id)
            .first()
        )
    if thread is None:
        thread = ChatThread(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            title=(question[:60] or "Chat"),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(thread)
        db.flush()

    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        thread_id=thread.id,
        owner_id=owner_id,
        role="user",
        content=question,
        created_at=_utcnow(),
    )
    asst_msg = ChatMessage(
        id=str(uuid.uuid4()),
        thread_id=thread.id,
        owner_id=owner_id,
        role="assistant",
        content=result.text,
        citations_json=json.dumps([c.model_dump() for c in result.citations]),
        refused=result.refused,
        created_at=_utcnow(),
    )
    thread.updated_at = _utcnow()
    db.add(user_msg)
    db.add(asst_msg)
    db.add(thread)
    db.commit()

    return {
        "thread_id": thread.id,
        "answer": result.model_dump(),
    }


def list_messages(db: Session, owner_id: str, *, limit: int = 50) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.owner_id == owner_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )


def clear_chats(db: Session, owner_id: str) -> int:
    threads = db.query(ChatThread).filter(ChatThread.owner_id == owner_id).all()
    n = len(threads)
    for thread in threads:
        db.delete(thread)
    db.commit()
    return n
