"""Split cleaned text into chunks with citation metadata."""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings
from src.ingest.clean import clean_text
from src.ingest.extract import ExtractedDocument
from src.models import Chunk


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def chunk_document(
    extracted: ExtractedDocument,
    *,
    doc_id: str,
    filename: str,
) -> list[Chunk]:
    """Chunk within each page so PDF page numbers stay accurate."""
    splitter = _splitter()
    chunks: list[Chunk] = []
    chunk_index = 0

    for page_block in extracted.pages:
        text = clean_text(page_block.text)
        if not text:
            continue

        pieces = splitter.split_text(text) if len(text) > settings.chunk_size else [text]
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{chunk_index}",
                    doc_id=doc_id,
                    filename=filename,
                    file_type=extracted.file_type,
                    page=page_block.page,
                    chunk_index=chunk_index,
                    text=piece,
                )
            )
            chunk_index += 1

    if not chunks:
        raise ValueError("No chunks produced after cleaning (empty text).")

    return chunks
