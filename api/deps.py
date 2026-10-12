"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from src.auth.sessions import get_session_by_token, touch_session
from src.db.models import Session as AuthSession
from src.db.session import get_db


def current_session(
    db: Annotated[Session, Depends(get_db)],
    x_doccite_session: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthSession:
    token = x_doccite_session
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    session = get_session_by_token(db, token or "")
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid session. Call /auth/guest or /auth/login first.",
        )
    touch_session(db, session)
    return session
