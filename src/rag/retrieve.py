"""Retrieve top chunks for a question from Chroma."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src.config import settings
from src.store.chroma_store import ChromaStore, QueryHit

logger = logging.getLogger(__name__)

# CVs often list "+234 …" without the word "phone" — expand / boost those queries.
CONTACT_INTENT = re.compile(
    r"\b("
    r"phone|telephone|mobile|cell|whatsapp|"
    r"email|e-?mail|"
    r"contact(\s+(number|info|details|email|phone))?"
    r")\b",
    re.I,
)
WANTS_PHONE = re.compile(
    r"\b(phone|telephone|mobile|cell|whatsapp|contact\s*number)\b", re.I
)
WANTS_EMAIL = re.compile(r"\b(e-?mail|contact\s*email)\b", re.I)
PHONE_IN_TEXT = re.compile(r"(?:\+\d[\d\s().-]{6,}\d|\b\d{3}[\s().-]?\d{3}[\s().-]?\d{4}\b)")
EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


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


def _expand_query(question: str) -> str:
    if not CONTACT_INTENT.search(question):
        return question
    return (
        f"{question} contact details phone telephone mobile number "
        "email address @ github linkedin"
    )


def _matches_contact_need(question: str, text: str) -> bool:
    wants_phone = bool(WANTS_PHONE.search(question))
    wants_email = bool(WANTS_EMAIL.search(question))
    has_phone = bool(PHONE_IN_TEXT.search(text))
    has_email = bool(EMAIL_IN_TEXT.search(text))
    if wants_phone and wants_email:
        return has_phone or has_email
    if wants_phone:
        return has_phone
    if wants_email:
        return has_email
    # generic "contact" — either field
    return has_phone or has_email


def _merge_hits(*groups: list[QueryHit]) -> list[QueryHit]:
    seen: set[str] = set()
    out: list[QueryHit] = []
    for group in groups:
        for hit in group:
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            out.append(hit)
    return out


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
    contact = bool(CONTACT_INTENT.search(question or ""))
    # Contact lines are short and rarely say "phone"; cast a wider net.
    if contact:
        min_similarity = min(min_similarity, 0.12)
        wide_k = max(k, 12)
    else:
        wide_k = k

    if store.count() == 0:
        return RetrieveResult(hits=[], collection_empty=True, raw_hit_count=0)

    query_text = _expand_query(question)
    raw = store.query(query_text, k=wide_k)
    kept = [h for h in raw if _passes_threshold(h.score, min_similarity)]

    if contact:
        contact_hits = [h for h in raw if _matches_contact_need(question, h.text)]
        # Prefer chunks that literally contain the asked-for contact field.
        if contact_hits:
            kept = _merge_hits(contact_hits, kept)[:k]
        else:
            kept = kept[:k]
    else:
        kept = kept[:k]

    logger.info(
        "retrieve k=%s wide_k=%s raw=%s kept=%s contact=%s min_similarity=%.3f",
        k,
        wide_k,
        len(raw),
        len(kept),
        contact,
        min_similarity,
    )
    return RetrieveResult(
        hits=kept,
        collection_empty=False,
        raw_hit_count=len(raw),
    )
