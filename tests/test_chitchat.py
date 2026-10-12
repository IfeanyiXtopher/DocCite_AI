"""Chitchat detection — polite replies without refusing."""

from __future__ import annotations

from types import SimpleNamespace

from src.rag.chitchat import chitchat_reply, is_chitchat
from src.rag.qa import answer
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
        return SimpleNamespace(content=self.content)


def test_chitchat_phrases_detected() -> None:
    for phrase in (
        "okay good",
        "ok",
        "that's good",
        "thanks",
        "thank you",
        "great",
        "hi",
        "got it",
    ):
        assert is_chitchat(phrase), phrase


def test_real_questions_not_chitchat() -> None:
    for phrase in (
        "What is ALPHA-TOKEN-7?",
        "okay what is his role?",
        "thanks but where did he work?",
        "How many years of experience?",
    ):
        assert not is_chitchat(phrase), phrase


def test_answer_chitchat_skips_retrieval_and_llm() -> None:
    llm = RecordingLLM("should not be used")
    store = FakeStore([], count=5)  # library exists
    result = answer("okay good", store=store, llm=llm)  # type: ignore[arg-type]
    assert result.refused is False
    assert result.citations == []
    assert result.model == "chitchat"
    assert "Glad" in result.text or "helped" in result.text.lower()
    assert llm.calls == 0


def test_chitchat_reply_thanks() -> None:
    text = chitchat_reply("thank you")
    assert "welcome" in text.lower()
