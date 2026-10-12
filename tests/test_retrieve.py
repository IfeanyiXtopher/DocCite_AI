"""Unit tests for retrieval thresholding (no OpenAI)."""

from __future__ import annotations

from src.rag.retrieve import (
    RetrieveResult,
    _expand_query,
    _matches_contact_need,
    _passes_threshold,
    retrieve,
)
from src.store.chroma_store import QueryHit


class FakeStore:
    def __init__(self, hits: list[QueryHit], count: int | None = None) -> None:
        self._hits = hits
        self._count = len(hits) if count is None else count
        self.last_k: int | None = None

    def count(self) -> int:
        return self._count

    def query(self, query_text: str, k: int | None = None) -> list[QueryHit]:
        self.last_k = k
        return list(self._hits)


def _hit(chunk_id: str, distance: float, page: int = 1) -> QueryHit:
    return QueryHit(
        chunk_id=chunk_id,
        text=f"text for {chunk_id}",
        metadata={"filename": "f.pdf", "page": page, "has_page": True},
        score=distance,
    )


def test_passes_threshold_uses_distance() -> None:
    # min similarity 0.25 → max distance 0.75
    assert _passes_threshold(0.40, 0.25) is True
    assert _passes_threshold(0.80, 0.25) is False


def test_retrieve_filters_weak_hits() -> None:
    store = FakeStore(
        [
            _hit("a:0", 0.20),
            _hit("a:1", 0.90),
        ]
    )
    result = retrieve("q", store=store, min_similarity=0.25)  # type: ignore[arg-type]
    assert isinstance(result, RetrieveResult)
    assert result.raw_hit_count == 2
    assert [h.chunk_id for h in result.hits] == ["a:0"]
    assert result.collection_empty is False


def test_retrieve_empty_collection() -> None:
    store = FakeStore([], count=0)
    result = retrieve("q", store=store)  # type: ignore[arg-type]
    assert result.collection_empty is True
    assert result.hits == []


def test_expand_query_for_phone() -> None:
    expanded = _expand_query("what is his phone number")
    assert "telephone" in expanded.lower()
    assert _expand_query("where did he school") == "where did he school"


def test_contact_boost_prefers_phone_chunk() -> None:
    """Phone may appear as +234… without the word 'phone' in the CV."""
    contact = QueryHit(
        chunk_id="cv:0",
        text="Lagos, Nigeria | +234 803 274 6255 | name@email.com",
        metadata={"filename": "cv.pdf", "page": 1, "has_page": True},
        score=0.55,  # weaker semantic score
    )
    other = QueryHit(
        chunk_id="cv:1",
        text="Led backend delivery for an energy platform.",
        metadata={"filename": "cv.pdf", "page": 1, "has_page": True},
        score=0.20,
    )
    store = FakeStore([other, contact])
    result = retrieve(
        "what is his phone number",
        store=store,  # type: ignore[arg-type]
        min_similarity=0.25,
    )
    assert result.hits[0].chunk_id == "cv:0"
    assert _matches_contact_need("phone number", contact.text) is True
    assert store.last_k is not None and store.last_k >= 12
