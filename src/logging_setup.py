"""Central logging configuration for CLI, ingest, and (later) the UI."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging once.

    INFO is the default for timings and stage messages.
    Do not log full document text at INFO (can be huge / sensitive) — use DEBUG
    only when diagnosing locally, and keep DEBUG off by default.
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. Streamlit or a second import) — just bump level.
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Noisy libraries — keep them quieter unless we are debugging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
