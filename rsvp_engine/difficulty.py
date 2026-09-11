"""Persian Linguistic Difficulty & Complexity Scoring (Phase 5).

Derives objective lexical difficulty and structural complexity scores in [0.0, 1.0] by combining:
1. Lexical frequency / rarity (inverse corpus frequency).
2. Orthographic length and morphological composition (char count, ZWNJ compounding).
3. Phonological / orthographic complexity markers (Hamza variants, rare consonants, numerals).
"""

from typing import Tuple
from rsvp_engine.frequency import ZWNJ, get_word_frequency

RARE_CONSONANTS = set("ژثذصضطظغع")
HAMZA_CHARS = set("ئؤءأإ")


def calculate_complexity_score(clean_word: str) -> float:
    """Computes structural and orthographic complexity in [0.0, 1.0]."""
    if not clean_word:
        return 0.0

    core_chars = [c for c in clean_word if c != ZWNJ]
    char_len = len(core_chars)

    # 1. Character length penalty
    if char_len <= 4:
        len_score = 0.0
    elif char_len <= 6:
        len_score = 0.15
    elif char_len <= 8:
        len_score = 0.30
    elif char_len <= 10:
        len_score = 0.45
    else:
        len_score = min(0.60, 0.45 + (char_len - 10) * 0.05)

    # 2. Compounding penalty (ZWNJs)
    zwnj_count = clean_word.count(ZWNJ)
    compound_score = min(0.25, zwnj_count * 0.10)

    # 3. Orthographic features
    ortho_score = 0.0
    if any(c in HAMZA_CHARS for c in clean_word):
        ortho_score += 0.08
    if any(c in RARE_CONSONANTS for c in clean_word):
        ortho_score += 0.08
    if any(c.isdigit() for c in clean_word):
        ortho_score += 0.10

    total_complexity = len_score + compound_score + ortho_score
    return round(min(1.0, max(0.0, total_complexity)), 2)


def calculate_word_metrics(word: str, clean_word: str) -> Tuple[float, float, float]:
    """Calculates (difficulty_score, frequency_score, complexity_score) in [0.0, 1.0].

    - difficulty_score: Overall cognitive difficulty combining rarity and complexity.
    - frequency_score: Lexical familiarity from curated Persian corpus.
    - complexity_score: Structural/morphological length and orthographic load.
    """
    if not clean_word:
        return (0.0, 1.0, 0.0)

    freq_score = get_word_frequency(clean_word)
    complexity_score = calculate_complexity_score(clean_word)

    # Invert frequency: rare words have high rarity
    rarity = 1.0 - freq_score

    # Composite difficulty weighting: 55% lexical rarity, 45% structural complexity
    raw_difficulty = (0.55 * rarity) + (0.45 * complexity_score)
    difficulty_score = round(min(1.0, max(0.0, raw_difficulty)), 2)

    return (difficulty_score, freq_score, complexity_score)
