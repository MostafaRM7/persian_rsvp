"""Shared linguistic constants for the Persian RSVP Engine.

Centralizes punctuation sets, quote markers, and typographic symbols
to eliminate drift risk and duplication across engine modules (P3-20, P3-13, P3-21).
"""

ZWNJ = "\u200c"

# Terminal / sentence-level punctuation (Class 4 triggers)
STRONG_PUNCTUATION = frozenset(".!?؟…\n")

# Clause-level / syntactic weak punctuation (Class 3 triggers)
WEAK_PUNCTUATION = frozenset("،؛:;,—–-")

# Quote and bracket delimiters
CLOSING_BRACKETS_QUOTES = frozenset("»)]}\"'")
OPENING_BRACKETS_QUOTES = frozenset("«([{")

# Combined punctuation set for word cleaning and ORP normalization
ALL_PUNCTUATION_CHARS = frozenset(
    STRONG_PUNCTUATION | WEAK_PUNCTUATION | CLOSING_BRACKETS_QUOTES | OPENING_BRACKETS_QUOTES | {"‹", "›"}
)
