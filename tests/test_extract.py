"""Unit tests for PDF extraction (no OpenAI)."""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest

from src.ingest.extract import ExtractError, extract_pdf

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "two_page_fixture.pdf"


@pytest.fixture(scope="module", autouse=True)
def ensure_fixture() -> None:
    if FIXTURE.is_file():
        return
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text(
        (72, 72),
        "DocCite fixture page one. The ALPHA-TOKEN-7 appears only on this first page.",
        fontsize=12,
    )
    page2 = doc.new_page()
    page2.insert_text(
        (72, 72),
        "DocCite fixture page two. The BRAVO-TOKEN-9 appears only on this second page.",
        fontsize=12,
    )
    doc.save(FIXTURE)
    doc.close()



def test_extract_pdf_pages_and_tokens() -> None:
    extracted = extract_pdf(FIXTURE)
    assert extracted.file_type == "pdf"
    assert extracted.page_count == 2
    assert len(extracted.pages) == 2
    assert extracted.pages[0].page == 1
    assert extracted.pages[1].page == 2
    assert "ALPHA-TOKEN-7" in extracted.pages[0].text
    assert "BRAVO-TOKEN-9" in extracted.pages[1].text
    assert "BRAVO-TOKEN-9" not in extracted.pages[0].text
    assert "ALPHA-TOKEN-7" not in extracted.pages[1].text


def test_extract_empty_pdf_fails(tmp_path: Path) -> None:
    empty_pdf = tmp_path / "empty.pdf"
    doc = fitz.open()
    doc.new_page()  # blank page, no text
    doc.save(empty_pdf)
    doc.close()

    with pytest.raises(ExtractError, match="No extractable text"):
        extract_pdf(empty_pdf)
