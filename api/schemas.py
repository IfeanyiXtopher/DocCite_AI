"""Pydantic request/response models for the API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SessionOut(BaseModel):
    token: str
    owner_id: str
    is_guest: bool
    guest_ttl_hours: int


class RegisterIn(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    page_count: Optional[int]
    chunk_count: int
    status: str
    error: Optional[str]


class SummaryOut(BaseModel):
    text: str
    cached: bool
    library_hash: str


class AskIn(BaseModel):
    question: str
    thread_id: Optional[str] = None


class AskOut(BaseModel):
    thread_id: str
    answer: dict[str, Any]


class ChatMessageOut(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    citations_json: Optional[str]
    refused: Optional[bool]


class ClearOut(BaseModel):
    documents_removed: int
    chroma_remaining: int


class PurgeOut(BaseModel):
    guests_purged: int
    ttl_hours: int


class MeOut(BaseModel):
    owner_id: str
    is_guest: bool
    email: Optional[str] = None
    guest_notice: Optional[str] = None
