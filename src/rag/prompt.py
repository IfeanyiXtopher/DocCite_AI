"""Q&A system prompt and context packing for grounded answers."""

from __future__ import annotations

from src.store.chroma_store import QueryHit, page_from_metadata

REFUSAL_TEXT = "I don't have that in your uploaded documents."

SYSTEM_PROMPT = """You are a document assistant for DocCite.

Rules:
- Answer factual questions ONLY using the provided excerpts.
- If the excerpts are insufficient to answer a factual question, reply with exactly:
  I don't have that in your uploaded documents.
- Do not use outside / world knowledge to answer document questions.
- Be concise.
- Do not invent page numbers or filenames; the application attaches sources separately.
- Short thanks or acknowledgments are handled by the app; if you still see one,
  reply briefly and politely without citing documents.
"""


def pack_context(hits: list[QueryHit], *, max_chunks: int = 6) -> str:
    """Format retrieved hits for the user message."""
    parts: list[str] = []
    for i, hit in enumerate(hits[:max_chunks], start=1):
        page = page_from_metadata(hit.metadata)
        filename = hit.metadata.get("filename", "unknown")
        page_repr = "null" if page is None else str(page)
        parts.append(
            f'[Source {i}] file="{filename}" page={page_repr} '
            f'chunk_id="{hit.chunk_id}"\n{hit.text.strip()}'
        )
    return "\n\n".join(parts)


def build_user_message(question: str, hits: list[QueryHit]) -> str:
    context = pack_context(hits)
    return (
        f"Excerpts from the user's uploaded documents:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the excerpts above."
    )
