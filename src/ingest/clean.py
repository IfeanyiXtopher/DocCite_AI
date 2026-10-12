"""Light text cleanup before chunking."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    """Normalize text without destroying case, punctuation, or numbers.

    Order (APPROACH.md §6.4):
    1. Normalize newlines
    2. Collapse 3+ blank lines to 2
    3. Strip trailing spaces on each line
    4. Remove null bytes
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
