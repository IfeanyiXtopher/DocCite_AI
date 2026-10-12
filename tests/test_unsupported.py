"""Unsupported / empty file rejection (no OpenAI)."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document as DocxDocument

from src.ingest.extract import ExtractError, extract_docx, extract_file, extract_text_file
from src.ingest.pipeline import MAX_FILE_BYTES, ingest_file


def test_unsupported_extension(tmp_path: Path) -> None:
    bad = tmp_path / "note.png"
    bad.write_bytes(b"\x89PNG\r\n")
    with pytest.raises(ExtractError, match="Unsupported file type"):
        extract_file(bad)


def test_empty_txt_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(ExtractError, match="No extractable text"):
        extract_text_file(empty, file_type="txt")


def test_docx_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    doc = DocxDocument()
    doc.add_paragraph("DocCite DOCX sample with enough text for extraction.")
    doc.save(path)
    extracted = extract_docx(path)
    assert extracted.file_type == "docx"
    assert extracted.page_count is None
    assert extracted.pages[0].page is None
    assert "DOCX sample" in extracted.pages[0].text


def test_oversize_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "big.txt"
    path.write_text("enough text for a fake oversized file check", encoding="utf-8")
    # Pretend the limit is tiny so a normal file looks oversized.
    monkeypatch.setattr("src.ingest.pipeline.MAX_FILE_BYTES", 10)
    with pytest.raises(ValueError, match="25 MB"):
        ingest_file(path)
