#!/usr/bin/env python3
"""CLI: ask a grounded question against the ingested library.

Usage:
  python scripts/ask.py "Your question?"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.logging_setup import setup_logging  # noqa: E402
from src.rag.qa import QaError, answer  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print('Usage: python scripts/ask.py "Your question?"', file=sys.stderr)
        return 2

    question = " ".join(args)
    try:
        result = answer(question)
    except QaError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"refused:  {result.refused}")
    print(f"model:    {result.model}")
    print(f"latency:  {result.latency_ms}")
    if result.token_usage:
        print(f"tokens:   {json.dumps(result.token_usage)}")
    print()
    print("Answer:")
    print(result.text)
    print()
    if result.citations:
        print("Citations:")
        for i, c in enumerate(result.citations, start=1):
            page = "n/a" if c.page is None else c.page
            print(f"  [{i}] {c.filename}  page={page}  chunk={c.chunk_id}")
            print(f"      quote: {c.quote}")
    elif not result.refused:
        print("Citations: (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
