"""Domain types shared across ingest, store, and RAG."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


FileType = Literal["pdf", "docx", "txt", "md"]
DocStatus = Literal["processing", "ready", "failed"]


class Document(BaseModel):
    """One uploaded file in the document registry."""

    doc_id: str
    filename: str
    stored_path: str
    file_type: FileType
    size_bytes: int
    page_count: Optional[int] = None
    chunk_count: int = 0
    status: DocStatus = "processing"
    error: Optional[str] = None
    uploaded_at: str
    ingested_at: Optional[str] = None
    # Step 7 multi-user: "user:<id>" or "guest:<session_id>"
    owner_id: Optional[str] = None


class Chunk(BaseModel):
    """A text segment ready for embedding / vector storage."""

    chunk_id: str
    doc_id: str
    filename: str
    file_type: str
    page: Optional[int] = None
    chunk_index: int
    text: str


class Citation(BaseModel):
    """A source shown next to an answer (from retriever metadata, not the LLM)."""

    filename: str
    page: Optional[int] = None
    chunk_id: str
    quote: str


class Answer(BaseModel):
    """Result of a grounded Q&A call."""

    text: str
    citations: list[Citation] = Field(default_factory=list)
    refused: bool = False
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    model: str = ""
    latency_ms: dict[str, Any] = Field(default_factory=dict)
    token_usage: Optional[dict[str, Any]] = None
