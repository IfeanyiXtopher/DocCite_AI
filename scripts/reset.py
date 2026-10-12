#!/usr/bin/env python3
"""CLI: wipe uploads, Chroma, registry, and summary cache.

Usage:
  python scripts/reset.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.logging_setup import setup_logging  # noqa: E402
from src.store.reset import reset_library  # noqa: E402


def main() -> int:
    setup_logging()
    try:
        info = reset_library()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print("Library reset.")
    for key, value in info.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
