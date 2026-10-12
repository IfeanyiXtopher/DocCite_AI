"""Library summary from sampled chunks, with a small disk cache."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from src.config import settings
from src.store import registry
from src.store.chroma_store import ChromaStore

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM = """You summarize a user's uploaded document library.
Rules:
- Use ONLY the provided document list and excerpt samples.
- Output 5–8 short bullets: what is in the library, main topics, and what kinds of questions it can support.
- Do not invent facts beyond the samples. If samples are thin, say the summary is based on excerpts.
"""


@dataclass
class SummaryResult:
    text: str
    cached: bool
    library_hash: str
    latency_ms: float


def summary_cache_path() -> Path:
    return settings.data_dir / "summary.json"


def library_hash(doc_ids: list[str]) -> str:
    payload = ",".join(sorted(doc_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_cache() -> Optional[dict[str, Any]]:
    path = summary_cache_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_cache(library_hash_value: str, text: str) -> None:
    settings.ensure_data_dirs()
    summary_cache_path().write_text(
        json.dumps(
            {"library_hash": library_hash_value, "text": text},
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_summary_cache() -> None:
    summary_cache_path().unlink(missing_ok=True)


def _sample_excerpts(store: ChromaStore, doc_id: str) -> list[str]:
    chunks = store.get_chunks_for_doc(doc_id)
    if not chunks:
        return []
    samples = [chunks[0].text]
    if len(chunks) > 1:
        mid = chunks[len(chunks) // 2]
        if mid.chunk_id != chunks[0].chunk_id:
            samples.append(mid.text)
    return samples


def summarize_library(
    *,
    store: ChromaStore | None = None,
    llm: Any | None = None,
    force: bool = False,
) -> SummaryResult:
    """Build or return a cached short library summary."""
    ready = [d for d in registry.list_documents() if d.status == "ready"]
    if not ready:
        return SummaryResult(
            text="No documents uploaded.",
            cached=False,
            library_hash="",
            latency_ms=0,
        )

    doc_ids = [d.doc_id for d in ready]
    h = library_hash(doc_ids)
    if not force:
        cached = _load_cache()
        if cached and cached.get("library_hash") == h and cached.get("text"):
            return SummaryResult(
                text=str(cached["text"]),
                cached=True,
                library_hash=h,
                latency_ms=0,
            )

    store = store or ChromaStore()
    lines = ["Documents:"]
    for doc in sorted(ready, key=lambda d: d.filename.lower()):
        pages = doc.page_count if doc.page_count is not None else "n/a"
        lines.append(
            f'- {doc.filename} (type={doc.file_type}, pages={pages}, chunks={doc.chunk_count})'
        )
        for i, excerpt in enumerate(_sample_excerpts(store, doc.doc_id), start=1):
            snippet = " ".join(excerpt.split())[:500]
            lines.append(f"  sample {i}: {snippet}")

    user_msg = "\n".join(lines)

    if llm is None:
        llm = ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

    t0 = time.perf_counter()
    response = llm.invoke(
        [
            ("system", SUMMARY_SYSTEM),
            ("human", user_msg + "\n\nWrite the library summary bullets now."),
        ]
    )
    latency = (time.perf_counter() - t0) * 1000
    text = (getattr(response, "content", None) or str(response)).strip()
    _save_cache(h, text)
    logger.info("summary generated hash=%s latency_ms=%.0f", h, latency)
    return SummaryResult(text=text, cached=False, library_hash=h, latency_ms=latency)
