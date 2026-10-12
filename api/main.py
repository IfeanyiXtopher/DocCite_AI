"""DocCite FastAPI — multi-user auth, library, chat, guest purge."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.deps import current_session
from api.schemas import (
    AskIn,
    AskOut,
    ChatMessageOut,
    ClearOut,
    DocumentOut,
    LoginIn,
    MeOut,
    PurgeOut,
    RegisterIn,
    SessionOut,
    SummaryOut,
)
from src.auth.sessions import (
    create_guest_session,
    login_user,
    logout_session,
    register_user,
)
from src.config import settings
from src.db.engine import init_db
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
    version="0.7.0",
    description=(
        "Document Q&A with citations. Guests are auto-purged after inactivity; "
        "logged-in libraries persist until the user clears them."
    ),
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


@app.get("/me", response_model=MeOut)
def me(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> MeOut:
    email = None
    if session.user_id:
        user = db.get(User, session.user_id)
        email = user.email if user else None
    return MeOut(
        owner_id=session.owner_id,
        is_guest=session.is_guest,
        email=email,
        guest_notice=GUEST_NOTICE if session.is_guest else None,
    )


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


@app.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
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
    return DocumentOut(
        id=row.id,
        filename=row.filename,
        file_type=row.file_type,
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        chunk_count=row.chunk_count,
        status=row.status,
        error=row.error,
    )


@app.get("/summary", response_model=SummaryOut)
def summary(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
) -> SummaryOut:
    try:
        result = lib.summarize_for_owner(db, session.owner_id, force=force)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SummaryOut(**result)


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


@app.get("/chats/messages", response_model=list[ChatMessageOut])
def chat_messages(
    session: Annotated[AuthSession, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
) -> list[ChatMessageOut]:
    rows = list(reversed(lib.list_messages(db, session.owner_id, limit=limit)))
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
