"""JSON document registry under data/registry.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import Document

logger = logging.getLogger(__name__)


def registry_path() -> Path:
    return settings.data_dir / "registry.json"


def load_registry() -> dict[str, Document]:
    path = registry_path()
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    docs: dict[str, Document] = {}
    for doc_id, payload in raw.get("documents", {}).items():
        docs[doc_id] = Document.model_validate(payload)
    return docs


def save_registry(docs: dict[str, Document]) -> None:
    settings.ensure_data_dirs()
    path = registry_path()
    payload = {
        "documents": {doc_id: doc.model_dump() for doc_id, doc in docs.items()}
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.debug("Wrote registry with %s documents", len(docs))


def upsert_document(doc: Document) -> Document:
    docs = load_registry()
    docs[doc.doc_id] = doc
    save_registry(docs)
    return doc


def get_document(doc_id: str) -> Optional[Document]:
    return load_registry().get(doc_id)


def find_by_filename(filename: str) -> Optional[Document]:
    for doc in load_registry().values():
        if doc.filename == filename:
            return doc
    return None


def delete_document(doc_id: str) -> None:
    docs = load_registry()
    if doc_id in docs:
        del docs[doc_id]
        save_registry(docs)


def list_documents() -> list[Document]:
    return list(load_registry().values())
