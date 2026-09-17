"""Persian Semantic Analysis & Intelligent Pause Detection (Phase 6).

Provides rule-based, deterministic syntactic and semantic boundary detection:
1. Sentence boundary detection across punctuation, quotations, and newline/paragraph breaks (P3-3).
2. Phrase and clause boundary detection (subordinating conjunctions, adversatives, speech reporting).
3. Context-sensitive pause decisions and punctuation + semantic pause combination.
4. Intelligent pacing modulation to eliminate flat-stream fatigue in long sentences.
"""

from typing import Optional, Tuple

from rsvp_engine.constants import (
    ALL_PUNCTUATION_CHARS,
    CLOSING_BRACKETS_QUOTES,
    STRONG_PUNCTUATION,
    WEAK_PUNCTUATION,
    ZWNJ,
)

# Persian Subordinating Conjunctions (حروف ربط وابسته ساز)
# Words introducing dependent clauses where the preceding constituent marks a clause boundary
SUBORDINATING_CONJUNCTIONS = {
    "که",
    "اگر",
    "گر",
    "چنانچه",
    "چون",
    "چونکه",
    "زیرا",
    "زیراکه",
    "چراکه",
    "اگرچه",
    "گرچه",
    "هرچند",
    "بااینکه",
    "بااین‌که",
    "هرچندکه",
    "تااینکه",
    "تااین‌که",
    "همین‌که",
    "همینکه",
    "به‌طوری‌که",
    "به‌گونه‌ای‌که",
    "درحالی‌که",
    "درحالیکه",
    "مگر",
    "مگرآنکه",
    "مگرآن‌که",
}

# Persian Coordinating & Adversative Conjunctions (حروف ربط همپایه و تقابلی)
# Words introducing major syntactic clauses with contrast or consequence
COORDINATING_ADVERSATIVE_CONJUNCTIONS = {
    "اما",
    "ولی",
    "لیکن",
    "بلکه",
    "بنابراین",
    "درنتیجه",
    "ازاین‌رو",
    "ازاینرو",
    "بااین‌حال",
    "بااینحال",
}

# Verbs of speech / direct citation (افعال گفتار و نقل قول)
SPEECH_VERBS = {
    "گفت", "گفتم", "گفتی", "گفتیم", "گفتید", "گفتند",
    "می‌گوید", "می‌گویند", "می‌گویم", "می‌گوییم",
    "پرسید", "پرسیدم", "پرسیدند", "می‌پرسد",
    "افزود", "افزودند", "فرمود",
}


def clean_core_token(word: Optional[str]) -> str:
    """Strips punctuation and whitespace from a word token."""
    if not word:
        return ""
    strip_chars = "".join(ALL_PUNCTUATION_CHARS) + " \t\u200c"
    return word.strip(strip_chars)


def is_sentence_boundary(word: str) -> bool:
    """Returns True if the token represents a sentence termination.
    
    Recognizes strong punctuation (.!?؟…), embedded quotes enclosing terminals (e.g. «...شد.»),
    and newline / paragraph breaks (P3-3).
    """
    if not word:
        return False

    if "\n" in word:
        return True

    trailing_strip = word.rstrip("".join(CLOSING_BRACKETS_QUOTES) + "\n")
    if trailing_strip and trailing_strip[-1] in STRONG_PUNCTUATION:
        return True

    return False


def is_clause_boundary(word: str, next_word: Optional[str] = None) -> bool:
    """Returns True if the token marks an overt or semantic clause boundary."""
    if not word:
        return False

    trailing_strip = word.rstrip("".join(CLOSING_BRACKETS_QUOTES) + "\n")
    if trailing_strip and trailing_strip[-1] in WEAK_PUNCTUATION:
        return True

    clean_w = clean_core_token(word)
    clean_next = clean_core_token(next_word)

    if not clean_next:
        return False

    # 1. Word precedes a subordinating clause introducer (e.g. می‌دانست [که], سرد بود [اگرچه])
    if clean_next in SUBORDINATING_CONJUNCTIONS:
        return True

    # 2. Word precedes an adversative/consequential conjunction (e.g. سرد بود [اما])
    if clean_next in COORDINATING_ADVERSATIVE_CONJUNCTIONS:
        return True

    # 3. Speech introducer before quote or clause
    if clean_w in SPEECH_VERBS and (next_word and next_word.startswith("«") or clean_next == "که"):
        return True

    return False


def analyze_token_boundaries(
    word: str,
    next_word: Optional[str] = None,
    prev_word: Optional[str] = None,
) -> Tuple[bool, bool, int]:
    """Analyzes a token within its immediate local context.
    
    Returns:
        (is_sentence_end, is_clause_end, semantic_pause_bonus)
    """
    is_sent_end = is_sentence_boundary(word)
    if is_sent_end:
        return (True, False, 0)

    trailing_strip = word.rstrip("".join(CLOSING_BRACKETS_QUOTES) + "\n")
    end_char = trailing_strip[-1] if trailing_strip else ""
    is_punct_clause_end = end_char in WEAK_PUNCTUATION

    clean_w = clean_core_token(word)
    clean_next = clean_core_token(next_word)

    is_semantic_clause = False
    if clean_next:
        is_semantic_clause = (
            clean_next in SUBORDINATING_CONJUNCTIONS or
            clean_next in COORDINATING_ADVERSATIVE_CONJUNCTIONS or
            (clean_w in SPEECH_VERBS and (next_word and next_word.startswith("«") or clean_next == "که"))
        )

    is_clause_end = is_punct_clause_end or is_semantic_clause

    bonus = 0
    if is_punct_clause_end and is_semantic_clause:
        # Punctuation + semantic clause boundary combination (e.g. بود، اما) -> bonus 15
        bonus = 15
    elif not is_punct_clause_end and is_semantic_clause:
        # Unpunctuated semantic clause boundary (e.g. می‌دانست که, بود اما) -> bonus 45
        bonus = 45

    return (False, is_clause_end, bonus)
