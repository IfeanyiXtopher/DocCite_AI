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
from src.db.models import (
    ChatMessage,
    ChatThread,
    ChatThreadDocument,
    DocumentRow,
    DocumentSummary,
    LibrarySummary,
)

NO_CHAT_DOCS_TEXT = "Attach a document to this chat before asking."
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
        # invalidate cached summaries for this library / document
        db.query(LibrarySummary).filter(LibrarySummary.owner_id == owner_id).delete()
        db.query(DocumentSummary).filter(DocumentSummary.doc_id == doc_id).delete()
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
        db.refresh(row)
        return row


def delete_document(db: Session, owner_id: str, doc_id: str) -> bool:
    """Remove one document (file + vectors + row). Returns False if missing."""
    row = (
        db.query(DocumentRow)
        .filter(DocumentRow.id == doc_id, DocumentRow.owner_id == owner_id)
        .first()
    )
    if not row:
        return False
    store = ChromaStore()
    store.delete_by_doc_id(doc_id, owner_id=owner_id)
    Path(row.stored_path).unlink(missing_ok=True)
    db.query(ChatThreadDocument).filter(
        ChatThreadDocument.doc_id == doc_id,
        ChatThreadDocument.owner_id == owner_id,
    ).delete()
    db.query(DocumentSummary).filter(DocumentSummary.doc_id == doc_id).delete()
    db.delete(row)
    db.query(LibrarySummary).filter(LibrarySummary.owner_id == owner_id).delete()
    db.commit()
    return True


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
    db.query(DocumentSummary).filter(DocumentSummary.owner_id == owner_id).delete()
    db.query(LibrarySummary).filter(LibrarySummary.owner_id == owner_id).delete()
    db.commit()
    return {"documents_removed": len(docs), "chroma_remaining": store.count(owner_id=owner_id)}


def _doc_content_hash(doc: DocumentRow) -> str:
    raw = f"{doc.id}|{doc.filename}|{doc.chunk_count}|{doc.ingested_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def summarize_for_document(
    db: Session, owner_id: str, doc_id: str, *, force: bool = False
) -> dict:
    """Return a short summary for one ready document (cached until the doc changes)."""
    from langchain_openai import ChatOpenAI

    doc = (
        db.query(DocumentRow)
        .filter(DocumentRow.id == doc_id, DocumentRow.owner_id == owner_id)
        .first()
    )
    if not doc:
        raise ValueError("Document not found")
    if doc.status != "ready":
        raise ValueError("Document is not ready yet")

    digest = _doc_content_hash(doc)
    cached = db.get(DocumentSummary, doc_id)
    if (
        not force
        and cached
        and cached.owner_id == owner_id
        and cached.content_hash == digest
        and cached.text
    ):
        return {
            "text": cached.text,
            "cached": True,
            "library_hash": digest,
            "doc_id": doc_id,
            "filename": doc.filename,
        }

    store = ChromaStore()
    pages = doc.page_count if doc.page_count is not None else "n/a"
    lines = [
        f"Document: {doc.filename}",
        f"type={doc.file_type}, pages={pages}, chunks={doc.chunk_count}",
    ]
    chunks = store.get_chunks_for_doc(doc.id, owner_id=owner_id)
    if chunks:
        lines.append(f"sample 1: {' '.join(chunks[0].text.split())[:700]}")
        if len(chunks) > 1:
            mid = chunks[len(chunks) // 2]
            lines.append(f"sample 2: {' '.join(mid.text.split())[:700]}")
        if len(chunks) > 2:
            lines.append(f"sample 3: {' '.join(chunks[-1].text.split())[:700]}")

    llm = ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    response = llm.invoke(
        [
            (
                "system",
                "Summarize this single document in 5–8 bullets. "
                "Use only the provided samples. Do not invent facts. "
                "Name the document in the first bullet.",
            ),
            ("human", "\n".join(lines) + "\n\nWrite the document summary bullets now."),
        ]
    )
    text = (getattr(response, "content", None) or str(response)).strip()
    row = cached or DocumentSummary(doc_id=doc_id, owner_id=owner_id)
    row.owner_id = owner_id
    row.content_hash = digest
    row.text = text
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    return {
        "text": text,
        "cached": False,
        "library_hash": digest,
        "doc_id": doc_id,
        "filename": doc.filename,
    }


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
    """ChromaStore facade filtered by owner_id and optional document ids."""

    def __init__(self, owner_id: str, doc_ids: list[str] | None = None) -> None:
        self.owner_id = owner_id
        self.doc_ids = list(doc_ids or [])
        self._store = ChromaStore()

    def count(self) -> int:
        return self._store.count(owner_id=self.owner_id, doc_ids=self.doc_ids or None)

    def query(self, query_text: str, k: int | None = None):
        return self._store.query(
            query_text,
            k=k,
            owner_id=self.owner_id,
            doc_ids=self.doc_ids or None,
        )


def create_thread(db: Session, owner_id: str, *, title: str = "New chat") -> ChatThread:
    thread = ChatThread(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        title=(title[:60] or "New chat"),
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


def get_thread(db: Session, owner_id: str, thread_id: str) -> ChatThread | None:
    return (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.owner_id == owner_id)
        .first()
    )


def list_thread_document_ids(db: Session, owner_id: str, thread_id: str) -> list[str]:
    rows = (
        db.query(ChatThreadDocument.doc_id)
        .filter(
            ChatThreadDocument.thread_id == thread_id,
            ChatThreadDocument.owner_id == owner_id,
        )
        .all()
    )
    return [r[0] for r in rows]


def list_thread_documents(
    db: Session, owner_id: str, thread_id: str
) -> list[DocumentRow]:
    ids = list_thread_document_ids(db, owner_id, thread_id)
    if not ids:
        return []
    return (
        db.query(DocumentRow)
        .filter(DocumentRow.owner_id == owner_id, DocumentRow.id.in_(ids))
        .order_by(DocumentRow.filename)
        .all()
    )


def attach_documents(
    db: Session,
    owner_id: str,
    thread_id: str,
    doc_ids: list[str],
) -> list[DocumentRow]:
    thread = get_thread(db, owner_id, thread_id)
    if not thread:
        raise ValueError("Chat not found.")
    attached: list[DocumentRow] = []
    for doc_id in doc_ids:
        doc = (
            db.query(DocumentRow)
            .filter(DocumentRow.id == doc_id, DocumentRow.owner_id == owner_id)
            .first()
        )
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")
        exists = (
            db.query(ChatThreadDocument)
            .filter(
                ChatThreadDocument.thread_id == thread_id,
                ChatThreadDocument.doc_id == doc_id,
            )
            .first()
        )
        if not exists:
            db.add(
                ChatThreadDocument(
                    id=str(uuid.uuid4()),
                    thread_id=thread_id,
                    doc_id=doc_id,
                    owner_id=owner_id,
                    attached_at=_utcnow(),
                )
            )
        attached.append(doc)
    thread.updated_at = _utcnow()
    db.add(thread)
    db.commit()
    return list_thread_documents(db, owner_id, thread_id)


def detach_document(db: Session, owner_id: str, thread_id: str, doc_id: str) -> bool:
    row = (
        db.query(ChatThreadDocument)
        .filter(
            ChatThreadDocument.thread_id == thread_id,
            ChatThreadDocument.doc_id == doc_id,
            ChatThreadDocument.owner_id == owner_id,
        )
        .first()
    )
    if not row:
        return False
    db.delete(row)
    thread = get_thread(db, owner_id, thread_id)
    if thread:
        thread.updated_at = _utcnow()
        db.add(thread)
    db.commit()
    return True


def ask_for_owner(
    db: Session,
    owner_id: str,
    question: str,
    *,
    thread_id: str | None = None,
) -> dict:
    if not thread_id:
        raise ValueError(NO_CHAT_DOCS_TEXT)
    thread = get_thread(db, owner_id, thread_id)
    if thread is None:
        raise ValueError("Chat not found.")

    doc_ids = list_thread_document_ids(db, owner_id, thread.id)
    if doc_ids:
        ready_ids = [
            d.id
            for d in db.query(DocumentRow)
            .filter(
                DocumentRow.owner_id == owner_id,
                DocumentRow.id.in_(doc_ids),
                DocumentRow.status == "ready",
            )
            .all()
        ]
    else:
        ready_ids = []

    if not ready_ids:
        from src.models import Answer

        result = Answer(
            text=NO_CHAT_DOCS_TEXT,
            citations=[],
            refused=True,
            retrieved_chunk_ids=[],
            model="",
        )
    else:
        store = OwnerStore(owner_id, ready_ids)
        result = rag_answer(question, store=store)  # type: ignore[arg-type]

    if thread.title in ("New chat", "Recent chat") and question.strip():
        thread.title = question.strip()[:60]

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


def list_threads(db: Session, owner_id: str, *, limit: int = 40) -> list[ChatThread]:
    """Return chats that actually have a user question (skip empty 'New chat' stubs)."""
    active_ids = (
        db.query(ChatMessage.thread_id)
        .filter(ChatMessage.owner_id == owner_id, ChatMessage.role == "user")
        .distinct()
        .subquery()
    )
    return (
        db.query(ChatThread)
        .filter(ChatThread.owner_id == owner_id, ChatThread.id.in_(active_ids))
        .order_by(ChatThread.updated_at.desc())
        .limit(limit)
        .all()
    )


def purge_empty_threads(
    db: Session, owner_id: str, *, keep_id: str | None = None
) -> int:
    """Delete stub threads with no questions and no attached documents."""
    active_ids = {
        r[0]
        for r in db.query(ChatMessage.thread_id)
        .filter(ChatMessage.owner_id == owner_id, ChatMessage.role == "user")
        .distinct()
        .all()
    }
    attached_ids = {
        r[0]
        for r in db.query(ChatThreadDocument.thread_id)
        .filter(ChatThreadDocument.owner_id == owner_id)
        .distinct()
        .all()
    }
    threads = db.query(ChatThread).filter(ChatThread.owner_id == owner_id).all()
    removed = 0
    for thread in threads:
        if thread.id in active_ids or thread.id in attached_ids:
            continue
        if keep_id and thread.id == keep_id:
            continue
        db.delete(thread)
        removed += 1
    if removed:
        db.commit()
    return removed


def list_messages(
    db: Session,
    owner_id: str,
    *,
    limit: int = 50,
    thread_id: str | None = None,
) -> list[ChatMessage]:
    q = db.query(ChatMessage).filter(ChatMessage.owner_id == owner_id)
    if thread_id:
        q = q.filter(ChatMessage.thread_id == thread_id)
    return q.order_by(ChatMessage.created_at.desc()).limit(limit).all()


def delete_thread(db: Session, owner_id: str, thread_id: str) -> bool:
    """Delete one chat thread (messages + attachments cascade)."""
    thread = get_thread(db, owner_id, thread_id)
    if not thread:
        return False
    db.delete(thread)
    db.commit()
    return True


def clear_chats(db: Session, owner_id: str) -> int:
    threads = db.query(ChatThread).filter(ChatThread.owner_id == owner_id).all()
    n = len(threads)
    for thread in threads:
        db.delete(thread)
    db.commit()
    return n
