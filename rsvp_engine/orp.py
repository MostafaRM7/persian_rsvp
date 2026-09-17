"""Logical Optical Recognition Point (ORP) boundary.

Determines the optimal focal character index within a word for fixation.
Rules:
- 1-3 characters: index 0 (initial letter)
- 4-6 characters: ~1/3 of the word length
- 7+ characters: between 1/3 and midpoint
- Skips Zero-Width Non-Joiner (ZWNJ) to avoid fixating on invisible control characters.
"""

import math
from rsvp_engine.constants import ALL_PUNCTUATION_CHARS, ZWNJ

PUNCTUATION_CHARS = ALL_PUNCTUATION_CHARS


def calculate_orp(word: str) -> int:
    """Calculates the 0-indexed character position for fixation.

    Leading and trailing punctuation are excluded from the focal calculation so that
    words like 'تندخوانی' and 'تندخوانی.' fixate on the exact same letter.
    """
    chars = list(word)
    total_len = len(chars)
    if total_len <= 1:
        return 0

    # Find boundaries of core word (excluding leading/trailing punctuation)
    start_idx = 0
    while start_idx < total_len and chars[start_idx] in PUNCTUATION_CHARS:
        start_idx += 1

    end_idx = total_len
    while end_idx > start_idx and chars[end_idx - 1] in PUNCTUATION_CHARS:
        end_idx -= 1

    core_len = end_idx - start_idx
    if core_len <= 1:
        return min(start_idx, total_len - 1)

    if core_len <= 3:
        core_orp = 0
    elif core_len <= 6:
        core_orp = max(1, math.floor(core_len / 3))
    else:
        core_orp = min(round(core_len / 3), math.floor((core_len - 1) / 2))

    target_idx = start_idx + core_orp

    # If ORP falls on a ZWNJ character, shift to the next readable letter
    if target_idx < total_len and chars[target_idx] == ZWNJ:
        if target_idx + 1 < end_idx:
            target_idx += 1
        elif target_idx > start_idx:
            target_idx -= 1

    return min(max(0, target_idx), total_len - 1)
