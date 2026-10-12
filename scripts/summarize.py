#!/usr/bin/env python3
"""CLI: print a short library summary (cached until the library changes).

Usage:
  python scripts/summarize.py
  python scripts/summarize.py --force
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.logging_setup import setup_logging  # noqa: E402
from src.rag.summarize import summarize_library  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = argv if argv is not None else sys.argv[1:]
    force = "--force" in args
    try:
        result = summarize_library(force=force)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"cached: {result.cached}")
    if result.library_hash:
        print(f"hash:   {result.library_hash}")
    print(f"ms:     {result.latency_ms:.0f}")
    print()
    print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
