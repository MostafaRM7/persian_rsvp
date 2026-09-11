"""Persian linguistic tokenization boundary (Phase 2).

Splits normalized text into atomic tokens while preserving:
- Zero-Width Non-Joiner (نیم‌فاصله) affixes (e.g., می‌خواهم, کتاب‌خانه, آن‌ها)
- Attached punctuation for downstream pause determination
- Numerals and formatted numbers (e.g. ۱۲,۵۰۰, ۳.۱۴, ٪۲۵)
- URLs and email addresses as single unbroken tokens
- Elimination of isolated floating punctuation and brackets
"""

import re
from typing import List

# Punctuation sets for token attachment
TRAILING_PUNCTUATION = {'.', '!', '؟', '?', '،', '؛', ':', ',', '…', '»', ')', ']', '}', '٪', '%'}
LEADING_PUNCTUATION = {'«', '(', '[', '{', '٪'}
# A token made exclusively of punctuation/whitespace is never a readable frame.
PUNCTUATION_ONLY_REGEX = re.compile(r"^[.!؟?،؛:;,…»()\[\]{}٪%-]+$")


def tokenize(normalized_text: str) -> List[str]:
    """Splits normalized Persian text into clean linguistic tokens.

    Ensures trailing punctuation is attached to preceding words,
    opening brackets/quotes are attached to enclosed words,
    and newlines are preserved on line-ending tokens to signal sentence/paragraph boundaries (P3-3).
    Never outputs a standalone punctuation mark as a frame.
    """
    if not normalized_text:
        return []

    lines = normalized_text.split("\n")
    all_tokens: List[str] = []

    for line_idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        raw_line_tokens = re.split(r"[ \t]+", line)
        raw_line_tokens = [t.strip() for t in raw_line_tokens if t.strip()]

        line_cleaned: List[str] = []

        for token in raw_line_tokens:
            # Standalone punctuation runs (e.g. "؟؟؟", "!!! ...", "…") are never readable
            # RSVP frames — attach them to the previous word so pauses still apply.
            if PUNCTUATION_ONLY_REGEX.match(token):
                if line_cleaned:
                    line_cleaned[-1] = line_cleaned[-1] + token
                elif all_tokens:
                    all_tokens[-1] = all_tokens[-1].rstrip("\n") + token
                continue
            if token in TRAILING_PUNCTUATION:
                if line_cleaned:
                    line_cleaned[-1] = line_cleaned[-1] + token
                elif all_tokens:
                    all_tokens[-1] = all_tokens[-1].rstrip("\n") + token
                # Drop stray leading trailing-punctuation marks at the beginning of document
            elif token in LEADING_PUNCTUATION:
                line_cleaned.append(token)
            else:
                if line_cleaned and line_cleaned[-1] in LEADING_PUNCTUATION:
                    line_cleaned[-1] = line_cleaned[-1] + token
                else:
                    line_cleaned.append(token)

        # Clean up any trailing unclosed leading-punctuation marks at the end of line
        while line_cleaned and line_cleaned[-1] in LEADING_PUNCTUATION:
            line_cleaned.pop()

        if line_cleaned:
            # Preserve newline on the terminal token of this line if subsequent lines exist (P3-3)
            has_subsequent = any(l.strip() for l in lines[line_idx + 1:])
            if has_subsequent:
                line_cleaned[-1] = line_cleaned[-1] + "\n"
            all_tokens.extend(line_cleaned)

    return all_tokens
