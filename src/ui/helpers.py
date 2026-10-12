"""Formatting helpers for the Streamlit UI."""

from __future__ import annotations

from typing import Any

from src.models import Answer, Citation, Document


def format_doc_row(doc: Document) -> str:
    pages = doc.page_count if doc.page_count is not None else "n/a"
    base = f"**{doc.filename}** — `{doc.status}` · pages={pages} · chunks={doc.chunk_count}"
    if doc.status == "failed" and doc.error:
        return f"{base}\n\n:red[Error: {doc.error}]"
    return base


def citation_lines(citations: list[Citation]) -> list[str]:
    lines: list[str] = []
    for i, c in enumerate(citations, start=1):
        page = "n/a" if c.page is None else c.page
        lines.append(f"**[{i}]** `{c.filename}` · page={page}\n> {c.quote}")
    return lines


def answer_to_message(answer: Answer) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": answer.text,
        "refused": answer.refused,
        "citations": [c.model_dump() for c in answer.citations],
        "latency_ms": answer.latency_ms,
    }


def safe_error_message(exc: BaseException) -> str:
    """User-facing error without stack traces."""
    text = str(exc).strip() or exc.__class__.__name__
    lowered = text.lower()
    if "api key" in lowered or "authentication" in lowered or "unauthorized" in lowered:
        return "API key missing or invalid."
    if "timeout" in lowered or "rate limit" in lowered or "429" in lowered:
        return "The language service is busy. Try again."
    if len(text) > 240:
        return text[:239] + "…"
    return text
