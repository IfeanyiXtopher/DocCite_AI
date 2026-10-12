"""DocCite FastAPI — multi-user auth, library, chat, guest purge."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.deps import current_session
from api.schemas import (
    AskIn,
    AskOut,
    AttachDocsIn,
    ChatMessageOut,
    ClearOut,
    DocumentOut,
    LoginIn,
    MeOut,
    ProfileUpdateIn,
    PurgeOut,
    RegisterIn,
    SessionOut,
    SummaryOut,
    ThreadOut,
    TranscribeOut,
)
from src.auth.sessions import (
    create_guest_session,
    login_user,
    logout_session,
    register_user,
)
from src.config import settings
from src.db.engine import init_db
from src.db.models import ChatThread
from src.db.models import Session as AuthSession
from src.db.models import User
from src.db.session import get_db
from src.logging_setup import setup_logging
from src.services import library as lib
from src.services.purge import purge_expired_guests

setup_logging()
init_db()

app = FastAPI(
    title="DocCite API",
    version="0.8.0",
    description=(
        "Document Q&A with citations. Guests are auto-purged after inactivity; "
        "logged-in libraries persist until the user clears them."
    ),
)

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GUEST_NOTICE = (
    "Guest mode: your uploads and chats are temporary and will be deleted after "
    f"{settings.guest_inactivity_ttl_hours} hours of inactivity. "
    "Register/login to keep your library."
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/guest", response_model=SessionOut)
def auth_guest(db: Annotated[Session, Depends(get_db)]) -> SessionOut:
    row = create_guest_session(db)
    return SessionOut(
        token=row.token,
        owner_id=row.owner_id,
        is_guest=True,
        guest_ttl_hours=settings.guest_inactivity_ttl_hours,
    )


@app.post("/auth/register", response_model=SessionOut)
def auth_register(
    body: RegisterIn, db: Annotated[Session, Depends(get_db)]
) -> SessionOut:
    try:
        user = register_user(db, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = login_user(db, user.email, body.password)
    return SessionOut(
        token=row.token,
        owner_id=row.owner_id,
        is_guest=False,
        guest_ttl_hours=settings.guest_inactivity_ttl_hours,
    )


@app.post("/auth/login", response_model=SessionOut)
def auth_login(body: LoginIn, db: Annotated[Session, Depends(get_db)]) -> SessionOut:
    try:
        row = login_user(db, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return SessionOut(
        token=row.token,
        owner_id=row.owner_id,
        is_guest=False,
        guest_ttl_hours=settings.guest_inactivity_ttl_hours,
    )


@app.post("/auth/logout")
def auth_logout(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    logout_session(db, session)
    return {"status": "logged_out"}


def _me_out(session: AuthSession, db: Session) -> MeOut:
    email = None
    display_name = None
    title = None
    company = None
    if session.user_id:
        user = db.get(User, session.user_id)
        if user:
            email = user.email
            display_name = user.display_name
            title = user.title
            company = user.company
    return MeOut(
        owner_id=session.owner_id,
        is_guest=session.is_guest,
        email=email,
        display_name=display_name,
        title=title,
        company=company,
        guest_notice=GUEST_NOTICE if session.is_guest else None,
    )


@app.get("/me", response_model=MeOut)
def me(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> MeOut:
    return _me_out(session, db)


@app.patch("/me/profile", response_model=MeOut)
def update_profile(
    body: ProfileUpdateIn,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> MeOut:
    if session.is_guest or not session.user_id:
        raise HTTPException(status_code=403, detail="Log in to edit your profile.")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None
    if body.title is not None:
        user.title = body.title.strip() or None
    if body.company is not None:
        user.company = body.company.strip() or None
    db.add(user)
    db.commit()
    db.refresh(user)
    return _me_out(session, db)


@app.get("/documents", response_model=list[DocumentOut])
def documents(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DocumentOut]:
    rows = lib.list_documents(db, session.owner_id)
    return [
        DocumentOut(
            id=r.id,
            filename=r.filename,
            file_type=r.file_type,
            size_bytes=r.size_bytes,
            page_count=r.page_count,
            chunk_count=r.chunk_count,
            status=r.status,
            error=r.error,
        )
        for r in rows
    ]


@app.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    ok = lib.delete_document(db, session.owner_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"status": "deleted", "id": doc_id}


@app.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    thread_id: Annotated[str | None, Form()] = None,
) -> DocumentOut:
    suffix = Path(file.filename or "upload.bin").suffix
    raw = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        row = lib.ingest_for_owner(
            db,
            session.owner_id,
            tmp_path,
            original_filename=file.filename or tmp_path.name,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    out = DocumentOut(
        id=row.id,
        filename=row.filename,
        file_type=row.file_type,
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        chunk_count=row.chunk_count,
        status=row.status,
        error=row.error,
    )
    # Surface ingest failures (e.g. OpenAI unreachable) without losing the row.
    if row.status == "failed":
        detail = row.error or "Document processing failed."
        if "connection" in detail.lower() or "proxy" in detail.lower():
            detail = (
                "Could not reach OpenAI to embed this document. "
                "Check network/proxy and OPENAI_API_KEY, then upload again."
            )
        raise HTTPException(status_code=502, detail=detail)

    if thread_id and row.status == "ready":
        try:
            lib.attach_documents(db, session.owner_id, thread_id, [row.id])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return out


@app.get("/summary", response_model=SummaryOut)
def summary(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
) -> SummaryOut:
    """Legacy whole-library summary (kept for CLI / Streamlit)."""
    try:
        result = lib.summarize_for_owner(db, session.owner_id, force=force)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SummaryOut(**result)


@app.get("/documents/{doc_id}/summary", response_model=SummaryOut)
def document_summary(
    doc_id: str,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
) -> SummaryOut:
    try:
        result = lib.summarize_for_document(
            db, session.owner_id, doc_id, force=force
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SummaryOut(
        text=result["text"],
        cached=result["cached"],
        library_hash=result["library_hash"],
    )


@app.post("/transcribe", response_model=TranscribeOut)
async def transcribe_audio(
    session: Annotated[AuthSession, Depends(current_session)],
    file: UploadFile = File(...),
) -> TranscribeOut:
    """Speech-to-text via OpenAI (gpt-4o-*-transcribe or whisper-1)."""
    _ = session.owner_id  # require auth; STT itself is not owner-scoped
    from src.services.transcribe import MAX_AUDIO_BYTES, transcribe_audio_file

    raw_name = file.filename or "recording.webm"
    suffix = Path(raw_name).suffix.lower() or ".webm"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio too large (max 25 MB)")

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        text = transcribe_audio_file(tmp_path, filename=f"recording{suffix}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if "connection" in detail.lower() or "proxy" in detail.lower():
            detail = (
                "Could not reach OpenAI to transcribe audio. "
                "Check network/proxy and OPENAI_API_KEY."
            )
        raise HTTPException(status_code=502, detail=detail) from exc
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    return TranscribeOut(text=text, model=settings.openai_transcribe_model)


@app.post("/ask", response_model=AskOut)
def ask(
    body: AskIn,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> AskOut:
    try:
        result = lib.ask_for_owner(
            db, session.owner_id, body.question, thread_id=body.thread_id
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AskOut(**result)


def _thread_out(db: Session, owner_id: str, thread: ChatThread) -> ThreadOut:
    return ThreadOut(
        id=thread.id,
        title=thread.title or "Recent chat",
        updated_at=thread.updated_at.isoformat(),
        document_ids=lib.list_thread_document_ids(db, owner_id, thread.id),
    )


@app.post("/chats/threads", response_model=ThreadOut)
def create_chat_thread(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> ThreadOut:
    thread = lib.create_thread(db, session.owner_id)
    return _thread_out(db, session.owner_id, thread)


@app.get("/chats/threads", response_model=list[ThreadOut])
def chat_threads(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 40,
) -> list[ThreadOut]:
    # Drop abandoned empty "New chat" stubs; only real Q&A chats are listed.
    lib.purge_empty_threads(db, session.owner_id)
    rows = lib.list_threads(db, session.owner_id, limit=limit)
    return [_thread_out(db, session.owner_id, t) for t in rows]


@app.get("/chats/threads/{thread_id}/documents", response_model=list[DocumentOut])
def thread_documents(
    thread_id: str,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DocumentOut]:
    if not lib.get_thread(db, session.owner_id, thread_id):
        raise HTTPException(status_code=404, detail="Chat not found.")
    rows = lib.list_thread_documents(db, session.owner_id, thread_id)
    return [
        DocumentOut(
            id=r.id,
            filename=r.filename,
            file_type=r.file_type,
            size_bytes=r.size_bytes,
            page_count=r.page_count,
            chunk_count=r.chunk_count,
            status=r.status,
            error=r.error,
        )
        for r in rows
    ]


@app.post("/chats/threads/{thread_id}/documents", response_model=list[DocumentOut])
def attach_thread_documents(
    thread_id: str,
    body: AttachDocsIn,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DocumentOut]:
    try:
        rows = lib.attach_documents(db, session.owner_id, thread_id, body.doc_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [
        DocumentOut(
            id=r.id,
            filename=r.filename,
            file_type=r.file_type,
            size_bytes=r.size_bytes,
            page_count=r.page_count,
            chunk_count=r.chunk_count,
            status=r.status,
            error=r.error,
        )
        for r in rows
    ]


@app.delete("/chats/threads/{thread_id}/documents/{doc_id}")
def detach_thread_document(
    thread_id: str,
    doc_id: str,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    ok = lib.detach_document(db, session.owner_id, thread_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    return {"status": "detached", "thread_id": thread_id, "doc_id": doc_id}


@app.delete("/chats/threads/{thread_id}")
def delete_chat_thread(
    thread_id: str,
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    ok = lib.delete_thread(db, session.owner_id, thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {"status": "deleted", "id": thread_id}


@app.get("/chats/messages", response_model=list[ChatMessageOut])
def chat_messages(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
    thread_id: str | None = None,
) -> list[ChatMessageOut]:
    rows = list(
        reversed(
            lib.list_messages(
                db, session.owner_id, limit=limit, thread_id=thread_id
            )
        )
    )
    return [
        ChatMessageOut(
            id=m.id,
            thread_id=m.thread_id,
            role=m.role,
            content=m.content,
            citations_json=m.citations_json,
            refused=m.refused,
        )
        for m in rows
    ]


@app.delete("/chats")
def delete_chats(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    n = lib.clear_chats(db, session.owner_id)
    return {"threads_removed": n}


@app.delete("/library", response_model=ClearOut)
def delete_library(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> ClearOut:
    result = lib.clear_library(db, session.owner_id)
    return ClearOut(**result)


@app.post("/admin/purge-guests", response_model=PurgeOut)
def admin_purge_guests(
    db: Annotated[Session, Depends(get_db)],
    x_admin_secret: Annotated[str | None, Header()] = None,
) -> PurgeOut:
    if x_admin_secret != settings.auth_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    result = purge_expired_guests(db)
    return PurgeOut(**result)
