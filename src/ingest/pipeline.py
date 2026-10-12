"""End-to-end ingest: save → extract → chunk → embed → registry."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.config import settings
from src.ingest.chunk import chunk_document
from src.ingest.extract import ExtractError, detect_file_type, extract_file
from src.models import Document
from src.store import chroma_store as chroma_mod
from src.store import registry

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024


@dataclass
class IngestResult:
    document: Document
    timings_ms: dict[str, float] = field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(name: str) -> str:
    return Path(name).name.replace("/", "_").replace("\\", "_")


def ingest_file(source_path: Path | str) -> IngestResult:
    """Ingest a single file into Chroma + registry.

    All-or-nothing per doc_id: on embed failure, delete any chunks already written.
    """
    source_path = Path(source_path)
    settings.ensure_data_dirs()

    if not source_path.is_file():
        raise FileNotFoundError(f"File not found: {source_path}")

    size = source_path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds 25 MB limit ({size} bytes).")

    filename = _safe_filename(source_path.name)
    doc_id = str(uuid.uuid4())
    stored_path = settings.upload_dir / f"{doc_id}_{filename}"

    t0 = time.perf_counter()
    shutil.copy2(source_path, stored_path)

    try:
        file_type = detect_file_type(source_path)
    except ExtractError as exc:
        stored_path.unlink(missing_ok=True)
        raise ValueError(str(exc)) from exc

    doc = Document(
        doc_id=doc_id,
        filename=filename,
        stored_path=str(stored_path),
        file_type=file_type,
        size_bytes=size,
        status="processing",
        uploaded_at=_utc_now(),
    )
    registry.upsert_document(doc)

    store = chroma_mod.ChromaStore()
    timings: dict[str, float] = {}

    try:
        t_extract = time.perf_counter()
        extracted = extract_file(stored_path)
        timings["extract_ms"] = (time.perf_counter() - t_extract) * 1000

        t_chunk = time.perf_counter()
        chunks = chunk_document(extracted, doc_id=doc_id, filename=filename)
        timings["chunk_ms"] = (time.perf_counter() - t_chunk) * 1000

        t_embed = time.perf_counter()
        store.add_chunks(chunks)
        timings["embed_upsert_ms"] = (time.perf_counter() - t_embed) * 1000

        doc.page_count = extracted.page_count
        doc.chunk_count = len(chunks)
        doc.status = "ready"
        doc.ingested_at = _utc_now()
        doc.error = None
        registry.upsert_document(doc)

        timings["total_ms"] = (time.perf_counter() - t0) * 1000
        logger.info(
            "ingest ready filename=%s doc_id=%s pages=%s chunks=%s "
            "extract_ms=%.0f chunk_ms=%.0f embed_upsert_ms=%.0f total_ms=%.0f",
            filename,
            doc_id,
            doc.page_count,
            doc.chunk_count,
            timings.get("extract_ms", 0),
            timings.get("chunk_ms", 0),
            timings.get("embed_upsert_ms", 0),
            timings.get("total_ms", 0),
        )
        return IngestResult(document=doc, timings_ms=timings)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest failed for %s", filename)
        try:
            store.delete_by_doc_id(doc_id)
        except Exception:  # noqa: BLE001
            logger.warning("Rollback delete_by_doc_id failed for %s", doc_id)
        doc.status = "failed"
        doc.error = str(exc)
        registry.upsert_document(doc)
        raise
