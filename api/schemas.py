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


class TranscribeOut(BaseModel):
    text: str
    model: str


class AskIn(BaseModel):
    question: str
    thread_id: str


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


class ThreadOut(BaseModel):
    id: str
    title: str
    updated_at: str
    document_ids: list[str] = Field(default_factory=list)


class AttachDocsIn(BaseModel):
    doc_ids: list[str] = Field(min_length=1)


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
    display_name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    guest_notice: Optional[str] = None


class ProfileUpdateIn(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    title: Optional[str] = Field(default=None, max_length=160)
    company: Optional[str] = Field(default=None, max_length=160)
