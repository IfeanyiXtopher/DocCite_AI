"""Create and resolve guest / logged-in sessions."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.auth.passwords import hash_password, verify_password
from src.db.models import Session as AuthSession
from src.db.models import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_guest_session(db: Session) -> AuthSession:
    session_id = str(uuid.uuid4())
    row = AuthSession(
        id=session_id,
        token=secrets.token_urlsafe(32),
        owner_id=f"guest:{session_id}",
        is_guest=True,
        user_id=None,
        created_at=_utcnow(),
        last_active_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def register_user(db: Session, email: str, password: str) -> User:
    email_n = email.strip().lower()
    if db.query(User).filter(User.email == email_n).first():
        raise ValueError("Email already registered.")
    user = User(
        id=str(uuid.uuid4()),
        email=email_n,
        password_hash=hash_password(password),
        created_at=_utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, email: str, password: str) -> AuthSession:
    email_n = email.strip().lower()
    user = db.query(User).filter(User.email == email_n).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password.")
    row = AuthSession(
        id=str(uuid.uuid4()),
        token=secrets.token_urlsafe(32),
        owner_id=f"user:{user.id}",
        is_guest=False,
        user_id=user.id,
        created_at=_utcnow(),
        last_active_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session_by_token(db: Session, token: str) -> AuthSession | None:
    if not token:
        return None
    return db.query(AuthSession).filter(AuthSession.token == token).first()


def touch_session(db: Session, session: AuthSession) -> None:
    session.last_active_at = _utcnow()
    db.add(session)
    db.commit()


def logout_session(db: Session, session: AuthSession) -> None:
    db.delete(session)
    db.commit()
