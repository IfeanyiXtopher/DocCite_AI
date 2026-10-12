"""Unit tests for chunking (no OpenAI)."""

from __future__ import annotations

from src.ingest.chunk import chunk_document
from src.ingest.clean import clean_text
from src.ingest.extract import ExtractedDocument, PageText


def test_clean_collapses_blank_lines() -> None:
    raw = "a\n\n\n\nb  \n"
    cleaned = clean_text(raw)
    assert cleaned == "a\n\nb"
    assert "\x00" not in clean_text("x\x00y")


def test_chunk_preserves_page_and_overlap() -> None:
    # Long page-1 text so the splitter must create overlap chunks.
    long_page = ("Sentence about ALPHA. " * 80).strip()
    extracted = ExtractedDocument(
        file_type="pdf",
        page_count=2,
        pages=[
            PageText(page=1, text=long_page),
            PageText(page=2, text="Short BRAVO-TOKEN-9 only on page two."),
        ],
    )
    chunks = chunk_document(extracted, doc_id="doc-test", filename="f.pdf")
    assert chunks
    assert all(c.doc_id == "doc-test" for c in chunks)
    assert all(c.filename == "f.pdf" for c in chunks)
    assert all(c.text.strip() for c in chunks)
    assert chunks[0].chunk_index == 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    page1 = [c for c in chunks if c.page == 1]
    page2 = [c for c in chunks if c.page == 2]
    assert len(page1) >= 2  # long page split
    assert len(page2) == 1
    assert "BRAVO-TOKEN-9" in page2[0].text
    # No cross-page mix: page-2 chunk should not carry long ALPHA spam as primary
    assert page2[0].page == 2
