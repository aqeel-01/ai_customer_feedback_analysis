"""
filtering/filter.py
===================
Stateless rules that decide whether a ticket qualifies for LLM analysis.

Rules (applied in order):
  1. Spam / promotional broadcasts  → IGNORED ("spam or promotional broadcast")
  2. Pure greeting / social pleasantry → IGNORED ("greeting or social pleasantry …")
  3. Everything else                → qualifies

Key design constraint:
  A message that *starts* with a greeting but contains an actionable customer
  request MUST qualify. Example:
    "Hi team, it would be awesome if you could add a dark mode to the mobile app."
    → qualifies (actionable request follows greeting)

  Versus pure conversational pleasantries:
    "Hello, hope you are having a nice day!"
    → IGNORED (no actionable content)

Public API:
    is_qualifying(ticket: RawTicket) -> tuple[bool, str]
        Returns (True, "") if the ticket qualifies.
        Returns (False, reason) if it should be ignored.
"""

from __future__ import annotations

import re

from feedback_analyzer.schemas.input_schema import RawTicket

# ---------------------------------------------------------------------------
# Word sets used to detect social pleasantries
# A message whose words are entirely a subset of _NON_QUALIFYING_WORDS is
# considered a pure greeting / social pleasantry with no actionable content.
# ---------------------------------------------------------------------------

_GREETING_WORDS: frozenset[str] = frozenset(
    {
        "hi", "hello", "hey", "howdy", "greetings", "yo", "dear",
        "hiya", "hola", "sup", "good",
    }
)

_SOCIAL_FILLER: frozenset[str] = frozenset(
    {
        # Time-of-day and calendar words (follow "good …")
        "morning", "afternoon", "evening", "night", "day", "week",
        # Common social filler verbs and adjectives
        "hope", "have", "having", "are", "is", "be", "been",
        "doing", "going",
        # Positive descriptors with no actionable meaning
        "nice", "great", "wonderful", "fantastic", "lovely", "beautiful",
        "fine", "well", "good",
        # Articles, conjunctions, pronouns
        "a", "an", "the", "and", "or", "to", "so", "too", "just",
        "i", "am", "im", "you", "your", "my", "our", "their", "us",
        "it", "its", "how", "all",
        # Salutation targets that add no request signal
        "there", "team", "everyone", "everybody", "folks", "was", "were", "will", "would",
    }
)

# A message is a social pleasantry when ALL its normalised words belong here.
_NON_QUALIFYING_WORDS: frozenset[str] = _GREETING_WORDS | _SOCIAL_FILLER

# ---------------------------------------------------------------------------
# Spam / promotional patterns
# ---------------------------------------------------------------------------

_SPAM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(buy now|limited offer|act now|click here|unsubscribe)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(free offer|special (promotion|deal)|exclusive deal|flash sale|clearance)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(order now|shop now|don[\'']?t miss out)\b", re.IGNORECASE),
    # e.g. "90% off", "50 % OFF"
    re.compile(r"\d+\s*%\s*off", re.IGNORECASE),
]

# Heuristic: very high uppercase ratio + multiple exclamation marks
_MIN_EXCLAMATIONS_FOR_SPAM = 3
_MIN_UPPER_RATIO_FOR_SPAM = 0.40


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_words(text: str) -> set[str]:
    """Lowercase, strip punctuation, return the set of non-empty word tokens."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return {w for w in cleaned.split() if w}


def _is_spam(message: str) -> bool:
    """Return True when the message matches spam or promotional patterns."""
    for pattern in _SPAM_PATTERNS:
        if pattern.search(message):
            return True

    # Heuristic: messages that are mostly uppercase with many exclamation marks
    # (e.g. "BUY NOW!!! 90% OFF TODAY ONLY!!!") are promotional broadcasts.
    exclamation_count = message.count("!")
    non_space_chars = message.replace(" ", "")
    upper_ratio = (
        sum(1 for c in non_space_chars if c.isupper()) / len(non_space_chars)
        if non_space_chars
        else 0.0
    )
    return bool(
        exclamation_count >= _MIN_EXCLAMATIONS_FOR_SPAM
        and upper_ratio >= _MIN_UPPER_RATIO_FOR_SPAM
    )


def _is_social_pleasantry(message: str) -> bool:
    """
    Return True when the message is a pure greeting or social pleasantry
    containing no actionable customer content.

    Strategy: normalise the message to a word set and check whether every
    word belongs to the non-qualifying vocabulary.  If so, the message has
    no signal that would change the analysis — ignore it.
    """
    words = _normalize_words(message)
    if not words:
        # Effectively empty after normalisation — treat as non-qualifying.
        return True
    return words.issubset(_NON_QUALIFYING_WORDS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_qualifying(ticket: RawTicket | str) -> tuple[bool, str]:
    """
    Determine whether a ticket qualifies for LLM analysis.

    Checks are applied in order; the first match wins.

    Args:
        ticket: A validated RawTicket instance or a message string.

    Returns:
        (True, "")              — ticket qualifies; pass it to the LLM.
        (False, reason: str)    — ticket should be IGNORED; reason explains why.
    """
    message = ticket if isinstance(ticket, str) else ticket.message

    if _is_spam(message):
        return False, "spam or promotional broadcast"

    if _is_social_pleasantry(message):
        return False, "greeting or social pleasantry with no actionable content"

    return True, ""
