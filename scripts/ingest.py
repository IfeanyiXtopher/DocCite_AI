#!/usr/bin/env python3
"""CLI: ingest one PDF into Chroma + registry.

Usage:
  python scripts/ingest.py path/to/file.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/ingest.py` without installing the package.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.pipeline import ingest_file  # noqa: E402
from src.logging_setup import setup_logging  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Usage: python scripts/ingest.py path/to/file.pdf", file=sys.stderr)
        return 2

    path = Path(args[0])
    try:
        result = ingest_file(path)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    doc = result.document
    t = result.timings_ms
    print(f"status:     {doc.status}")
    print(f"doc_id:     {doc.doc_id}")
    print(f"filename:   {doc.filename}")
    print(f"pages:      {doc.page_count}")
    print(f"chunks:     {doc.chunk_count}")
    print(f"extract_ms: {t.get('extract_ms', 0):.0f}")
    print(f"chunk_ms:   {t.get('chunk_ms', 0):.0f}")
    print(f"embed_ms:   {t.get('embed_upsert_ms', 0):.0f}")
    print(f"total_ms:   {t.get('total_ms', 0):.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
