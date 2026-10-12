"""Unit tests for grounded Q&A refusal paths (mocked LLM / store)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.rag.prompt import REFUSAL_TEXT
from src.rag.qa import answer, citations_from_hits
from src.store.chroma_store import QueryHit


class FakeStore:
    def __init__(self, hits: list[QueryHit], count: int | None = None) -> None:
        self._hits = hits
        self._count = len(hits) if count is None else count

    def count(self) -> int:
        return self._count

    def query(self, query_text: str, k: int | None = None) -> list[QueryHit]:
        return list(self._hits)


class RecordingLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def invoke(self, messages):  # noqa: ANN001
        self.calls += 1
        return SimpleNamespace(content=self.content, usage_metadata={"total_tokens": 10})


def test_empty_question_raises() -> None:
    from src.rag.qa import QaError

    with pytest.raises(QaError, match="empty"):
        answer("   ", store=FakeStore([], count=0), llm=RecordingLLM("x"))  # type: ignore[arg-type]


def test_empty_collection_refuses_without_llm() -> None:
    llm = RecordingLLM("should not be used")
    result = answer("Anything?", store=FakeStore([], count=0), llm=llm)  # type: ignore[arg-type]
    assert result.refused is True
    assert "Upload documents first" in result.text
    assert result.citations == []
    assert llm.calls == 0


def test_no_hits_after_threshold_skips_llm() -> None:
    weak = QueryHit(
        chunk_id="x:0",
        text="unrelated",
        metadata={"filename": "f.pdf", "page": 1, "has_page": True},
        score=0.99,  # fails default similarity 0.25 → max dist 0.75
    )
    llm = RecordingLLM("should not be used")
    result = answer("Capital of France?", store=FakeStore([weak]), llm=llm)  # type: ignore[arg-type]
    assert result.refused is True
    assert result.text == REFUSAL_TEXT
    assert result.citations == []
    assert llm.calls == 0


def test_model_refusal_clears_citations() -> None:
    hit = QueryHit(
        chunk_id="d:0",
        text="DocCite fixture page two. BRAVO-TOKEN-9",
        metadata={
            "filename": "two_page_fixture.pdf",
            "page": 2,
            "has_page": True,
            "chunk_index": 0,
        },
        score=0.2,
    )
    llm = RecordingLLM(REFUSAL_TEXT)
    result = answer("What is the capital of France?", store=FakeStore([hit]), llm=llm)  # type: ignore[arg-type]
    assert result.refused is True
    assert result.citations == []
    assert llm.calls == 1


def test_citations_from_hits_not_model() -> None:
    hit = QueryHit(
        chunk_id="d:1",
        text="The BRAVO-TOKEN-9 appears only on this second page.",
        metadata={
            "filename": "two_page_fixture.pdf",
            "page": 2,
            "has_page": True,
        },
        score=0.1,
    )
    cites = citations_from_hits([hit])
    assert len(cites) == 1
    assert cites[0].page == 2
    assert cites[0].filename == "two_page_fixture.pdf"
    assert "BRAVO-TOKEN-9" in cites[0].quote
