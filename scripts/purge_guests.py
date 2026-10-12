#!/usr/bin/env python3
"""CLI: purge inactive guest owners (files + vectors + DB).

Usage:
  python scripts/purge_guests.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.engine import init_db
from src.db.session import session_scope
from src.logging_setup import setup_logging
from src.services.purge import purge_expired_guests


def main() -> int:
    setup_logging()
    init_db()
    db = session_scope()
    try:
        result = purge_expired_guests(db)
    finally:
        db.close()
    print(f"guests_purged: {result['guests_purged']}")
    print(f"ttl_hours:     {result['ttl_hours']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
