#!/usr/bin/env python3
"""Create the tiny 2-page fixture PDF used by Step 2 tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf as fitz

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "tests" / "fixtures" / "two_page_fixture.pdf"

PAGE1 = (
    "DocCite fixture page one. "
    "The ALPHA-TOKEN-7 appears only on this first page."
)
PAGE2 = (
    "DocCite fixture page two. "
    "The BRAVO-TOKEN-9 appears only on this second page."
)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for text in (PAGE1, PAGE2):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(OUT)
    doc.close()
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
