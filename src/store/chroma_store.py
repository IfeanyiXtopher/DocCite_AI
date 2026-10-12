"""ChromaDB persistence for document chunks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from langchain_openai import OpenAIEmbeddings

from src.config import settings
from src.models import Chunk

logger = logging.getLogger(__name__)

# Chroma metadata must be scalars. Missing PDF page → page=0 + has_page=False.
PAGE_SENTINEL = 0


@dataclass
class QueryHit:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float  # cosine distance from Chroma (lower is closer)


class ChromaStore:
    """Thin wrapper around a persisted Chroma collection."""

    def __init__(self) -> None:
        settings.ensure_data_dirs()
        # Import here so unit tests that only need extract/chunk stay lighter.
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embeddings = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )

    def count(self) -> int:
        return int(self._collection.count())

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        texts = [c.text for c in chunks]
        ids = [c.chunk_id for c in chunks]
        metadatas = [_chunk_metadata(c) for c in chunks]
        logger.info("Embedding %s chunks…", len(chunks))
        vectors = self._embeddings.embed_documents(texts)
        self._collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=vectors,
        )
        logger.info("Upserted %s chunks (collection count=%s)", len(chunks), self.count())

    def query(self, query_text: str, k: Optional[int] = None) -> list[QueryHit]:
        k = k if k is not None else settings.retrieve_top_k
        if self.count() == 0:
            return []
        vector = self._embeddings.embed_query(query_text)
        result = self._collection.query(
            query_embeddings=[vector],
            n_results=min(k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        hits: list[QueryHit] = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for chunk_id, text, meta, dist in zip(ids, docs, metas, dists, strict=True):
            hits.append(
                QueryHit(
                    chunk_id=chunk_id,
                    text=text or "",
                    metadata=dict(meta or {}),
                    score=float(dist),
                )
            )
        return hits

    def delete_by_doc_id(self, doc_id: str) -> None:
        # Chroma where filter
        self._collection.delete(where={"doc_id": doc_id})

    def get_chunks_for_doc(self, doc_id: str) -> list[QueryHit]:
        """Return stored chunks for one document (for summary sampling)."""
        result = self._collection.get(
            where={"doc_id": doc_id},
            include=["documents", "metadatas"],
        )
        hits: list[QueryHit] = []
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        for chunk_id, text, meta in zip(ids, docs, metas, strict=True):
            hits.append(
                QueryHit(
                    chunk_id=chunk_id,
                    text=text or "",
                    metadata=dict(meta or {}),
                    score=0.0,
                )
            )
        hits.sort(key=lambda h: int(h.metadata.get("chunk_index", 0)))
        return hits

    def delete_collection(self) -> None:
        name = settings.collection_name
        self._client.delete_collection(name)
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )


def _chunk_metadata(chunk: Chunk) -> dict[str, Any]:
    has_page = chunk.page is not None
    return {
        "doc_id": chunk.doc_id,
        "filename": chunk.filename,
        "file_type": chunk.file_type,
        "page": int(chunk.page) if has_page else PAGE_SENTINEL,
        "has_page": has_page,
        "chunk_index": chunk.chunk_index,
    }


def page_from_metadata(meta: dict[str, Any]) -> int | None:
    """Decode the page sentinel scheme used in Chroma metadata."""
    if not meta.get("has_page", False):
        return None
    page = meta.get("page")
    return int(page) if page is not None else None
