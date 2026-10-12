"""Wipe local library: Chroma, uploads, registry, summary cache."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from src.config import settings
from src.rag.summarize import clear_summary_cache
from src.store.chroma_store import ChromaStore
from src.store.registry import registry_path, save_registry

logger = logging.getLogger(__name__)


def reset_library() -> dict[str, int | str]:
    """Full local reset. Returns a small status dict for CLIs."""
    settings.ensure_data_dirs()

    store = ChromaStore()
    before = store.count()
    store.delete_collection()

    removed_uploads = 0
    for path in settings.upload_dir.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
            removed_uploads += 1

    save_registry({})
    clear_summary_cache()

    # Drop empty registry file noise is fine; keep path consistent
    if registry_path().is_file():
        pass

    logger.info(
        "reset complete chroma_before=%s uploads_removed=%s",
        before,
        removed_uploads,
    )
    return {
        "chroma_before": before,
        "chroma_after": store.count(),
        "uploads_removed": removed_uploads,
        "registry": str(registry_path()),
    }
