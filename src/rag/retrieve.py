"""Retrieve top chunks for a question from Chroma."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import settings
from src.store.chroma_store import ChromaStore, QueryHit

logger = logging.getLogger(__name__)


@dataclass
class RetrieveResult:
    hits: list[QueryHit]
    collection_empty: bool
    raw_hit_count: int


def _passes_threshold(distance: float, min_similarity: float) -> bool:
    """Chroma cosine space returns *distance* (lower = closer).

    ``settings.similarity_threshold`` is treated as a minimum similarity in
    roughly ``[0, 1]``. Keep a hit when ``(1 - distance) >= min_similarity``,
    i.e. ``distance <= 1 - min_similarity``.
    """
    max_distance = 1.0 - min_similarity
    return distance <= max_distance


def retrieve(
    question: str,
    *,
    store: ChromaStore | None = None,
    k: int | None = None,
    min_similarity: float | None = None,
) -> RetrieveResult:
    """Embed the question and return filtered hits (best matches first)."""
    store = store or ChromaStore()
    k = k if k is not None else settings.retrieve_top_k
    min_similarity = (
        settings.similarity_threshold if min_similarity is None else min_similarity
    )

    if store.count() == 0:
        return RetrieveResult(hits=[], collection_empty=True, raw_hit_count=0)

    raw = store.query(question, k=k)
    kept = [h for h in raw if _passes_threshold(h.score, min_similarity)]
    logger.info(
        "retrieve k=%s raw=%s kept=%s min_similarity=%.3f",
        k,
        len(raw),
        len(kept),
        min_similarity,
    )
    return RetrieveResult(
        hits=kept,
        collection_empty=False,
        raw_hit_count=len(raw),
    )
