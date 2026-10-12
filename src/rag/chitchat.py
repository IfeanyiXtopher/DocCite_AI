"""Detect short conversational turns that are not document questions.

DocCite still refuses factual questions outside the library. Acknowledgments
like "thanks" or "okay good" get a brief polite reply without retrieval.
"""

from __future__ import annotations

import re

# Whole-message patterns only (keep short — long text is treated as a question).
_CHITCHAT_RE = re.compile(
    r"""^(?:
        (?:hi|hello|hey|howdy)(?:\s+there)?
      | (?:ok(?:ay)?(?:\s+good)?|alright|all\s+right)
      | (?:that'?s|thats)\s+(?:good|great|helpful|perfect|fine|nice|awesome)
      | (?:sounds|looks)\s+good
      | (?:good|great|perfect|awesome|nice|cool|excellent|wonderful)
      | (?:thanks|thank\s+you|thx|ty)(?:\s+(?:a\s+lot|so\s+much|again))?
      | (?:got\s+it|makes\s+sense|understood|appreciate\s+it)
      | (?:bye|goodbye|see\s+you)
    )[!?.,\s]*$""",
    re.IGNORECASE | re.VERBOSE,
)

_QUESTION_HINT = re.compile(
    r"\b(what|who|where|when|why|how|which|whose|whom|is|are|was|were|can|could|"
    r"should|would|does|did|do|tell|explain|list|summarize|find)\b|\?",
    re.IGNORECASE,
)

_MAX_CHITCHAT_LEN = 80


def is_chitchat(text: str) -> bool:
    """True for short thanks / greetings / compliments, not real questions."""
    cleaned = " ".join((text or "").strip().split())
    if not cleaned or len(cleaned) > _MAX_CHITCHAT_LEN:
        return False
    if _QUESTION_HINT.search(cleaned) and "?" in cleaned:
        return False
    # "what is…" without ? still a question
    if re.match(
        r"^(what|who|where|when|why|how|which)\b",
        cleaned,
        flags=re.IGNORECASE,
    ):
        return False
    return bool(_CHITCHAT_RE.match(cleaned))


def chitchat_reply(text: str) -> str:
    """Return a short, friendly reply (no document claims)."""
    lowered = " ".join((text or "").strip().lower().split())
    if re.match(r"^(hi|hello|hey|howdy)\b", lowered):
        return (
            "Hi! Ask me anything about your uploaded documents — "
            "I’ll answer only from those files, with citations."
        )
    if re.match(r"^(bye|goodbye|see you)\b", lowered):
        return "Goodbye! Upload or ask again anytime."
    if re.match(r"^(thanks|thank you|thx|ty)\b", lowered):
        return (
            "You’re welcome! Ask another question about your documents "
            "whenever you’re ready."
        )
    # compliments / acknowledgments: okay good, that's great, cool, …
    return (
        "Glad that helped. Ask anything else about your uploaded documents — "
        "I’ll stick to what’s in your files."
    )
