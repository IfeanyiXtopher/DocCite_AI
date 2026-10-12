"""Grounded Q&A: retrieve → generate → citations from hits."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from src.config import settings
from src.models import Answer, Citation
from src.rag.prompt import REFUSAL_TEXT, SYSTEM_PROMPT, build_user_message
from src.rag.retrieve import retrieve
from src.store.chroma_store import ChromaStore, QueryHit, page_from_metadata

logger = logging.getLogger(__name__)

QUOTE_MAX = 240


class QaError(Exception):
    """User-safe Q&A failure."""


def _quote(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= QUOTE_MAX:
        return text
    return text[: QUOTE_MAX - 1].rstrip() + "…"


def citations_from_hits(hits: list[QueryHit]) -> list[Citation]:
    """Citations always come from retriever metadata, never from the model."""
    citations: list[Citation] = []
    for hit in hits:
        citations.append(
            Citation(
                filename=str(hit.metadata.get("filename", "unknown")),
                page=page_from_metadata(hit.metadata),
                chunk_id=hit.chunk_id,
                quote=_quote(hit.text),
            )
        )
    return citations


def _looks_like_refusal(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return (
        REFUSAL_TEXT.lower() in normalized
        or "don't have that in your uploaded documents" in normalized
        or "do not have that in your uploaded documents" in normalized
    )


def _chat_once(llm: ChatOpenAI, messages: list[tuple[str, str]]) -> Any:
    return llm.invoke(messages)


def _chat_with_retry(llm: ChatOpenAI, messages: list[tuple[str, str]]) -> Any:
    try:
        return _chat_once(llm, messages)
    except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as exc:
        logger.warning("Transient OpenAI error (%s); retrying once…", type(exc).__name__)
        time.sleep(1.0)
        try:
            return _chat_once(llm, messages)
        except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as exc2:
            logger.exception("OpenAI retry failed")
            raise QaError("The language service is busy. Try again.") from exc2


def answer(
    question: str,
    *,
    store: ChromaStore | None = None,
    llm: Optional[Any] = None,
) -> Answer:
    """Answer a question using only retrieved document excerpts."""
    q = (question or "").strip()
    if not q:
        raise QaError("Question is empty.")

    latency: dict[str, Any] = {}
    t0 = time.perf_counter()

    t_ret = time.perf_counter()
    result = retrieve(q, store=store)
    latency["retrieve"] = round((time.perf_counter() - t_ret) * 1000)

    if result.collection_empty:
        return Answer(
            text="Upload documents first.",
            citations=[],
            refused=True,
            retrieved_chunk_ids=[],
            model=settings.openai_chat_model,
            latency_ms={**latency, "generate": 0, "total": round((time.perf_counter() - t0) * 1000)},
        )

    if not result.hits:
        latency["generate"] = 0
        latency["total"] = round((time.perf_counter() - t0) * 1000)
        logger.info("No hits after threshold; refusing without LLM call")
        return Answer(
            text=REFUSAL_TEXT,
            citations=[],
            refused=True,
            retrieved_chunk_ids=[],
            model=settings.openai_chat_model,
            latency_ms=latency,
        )

    if llm is None:
        if not settings.openai_api_key:
            raise QaError("API key missing or invalid.")
        llm = ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", build_user_message(q, result.hits)),
    ]

    t_gen = time.perf_counter()
    try:
        response = _chat_with_retry(llm, messages)
    except QaError:
        raise
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "api key" in msg or "authentication" in msg or "unauthorized" in msg:
            raise QaError("API key missing or invalid.") from exc
        logger.exception("Q&A generation failed")
        raise QaError("The language service is busy. Try again.") from exc
    latency["generate"] = round((time.perf_counter() - t_gen) * 1000)
    latency["total"] = round((time.perf_counter() - t0) * 1000)

    text = (getattr(response, "content", None) or str(response)).strip()
    refused = _looks_like_refusal(text)
    citations = [] if refused else citations_from_hits(result.hits)
    usage = None
    meta = getattr(response, "usage_metadata", None) or getattr(
        response, "response_metadata", {}
    ).get("token_usage")
    if isinstance(meta, dict):
        usage = meta

    logger.info(
        "qa refused=%s retrieve_ms=%s generate_ms=%s hits=%s",
        refused,
        latency["retrieve"],
        latency["generate"],
        len(result.hits),
    )

    return Answer(
        text=REFUSAL_TEXT if refused else text,
        citations=citations,
        refused=refused,
        retrieved_chunk_ids=[h.chunk_id for h in result.hits],
        model=settings.openai_chat_model,
        latency_ms=latency,
        token_usage=usage,
    )
