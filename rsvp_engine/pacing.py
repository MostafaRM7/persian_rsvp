"""Adaptive cognitive pacing boundary (Phase 4 — Basic Cognitive Pacing).

Derives opaque duration weight multipliers (100 = 1.0x base delay) based on:
1. Four distinct cognitive reading unit classes:
   - Class 1: Normal words and high-frequency function words (d: 75–110)
   - Class 2: Naturally longer reading units, compounds, and numerals (d: 115–145)
   - Class 3: Clause boundaries and weak punctuation (d: 145–180)
   - Class 4: Sentence endings and terminal propositions (d: 185–260)
2. Surrounding context sensitivity (sentence-initial orientation, dialogue introducers).
3. Target WPM derivation (ensuring terminal pauses remain perceptually sufficient at high speeds).
"""

import re
from typing import Optional

ZWNJ = "\u200c"

STRONG_PUNCTUATION = set(".!?؟…\n")
WEAK_PUNCTUATION = set("،؛:;,—–-")
CLOSING_BRACKETS_QUOTES = set("»)]}\"'")

# High-frequency Persian function words (prepositions & conjunctions) processed with lower cognitive load
FUNCTION_WORDS = {
    "و", "به", "در", "از", "با", "تا", "که", "یا", "چون", "اگر", "بر", "چو", "هم",
}

# Pacing Tier Thresholds
CLASS_1_NORMAL_BASE = 100
CLASS_1_FUNCTION_WORD = 80
CLASS_1_SENTENCE_INITIAL = 110

CLASS_2_LONG_THRESHOLD = 7
CLASS_2_MIN_WEIGHT = 115
CLASS_2_MAX_WEIGHT = 145

CLASS_3_CLAUSE_BASE = 155
CLASS_3_COLON_BASE = 160
CLASS_3_MIN_WEIGHT = 145
CLASS_3_MAX_WEIGHT = 180

CLASS_4_SENTENCE_BASE = 200
CLASS_4_ELLIPSIS_BASE = 220
CLASS_4_MIN_WEIGHT = 185
CLASS_4_MAX_WEIGHT = 260


def calculate_duration_weight(
    word: str,
    prev_word: Optional[str] = None,
    next_word: Optional[str] = None,
    wpm: Optional[int] = 300,
    difficulty_score: Optional[float] = None,
    frequency_score: Optional[float] = None,
    semantic_pause_bonus: Optional[int] = None,
) -> int:
    """Computes an opaque relative duration factor (100 = 1.0x base delay).

    Guarantees strictly distinct output tiers across cognitive reading classes,
    factoring in lexical frequency, structural complexity (Phase 5),
    and semantic/clause boundaries (Phase 6).
    """
    if not word:
        return CLASS_1_NORMAL_BASE

    # Identify terminal/clause punctuation (ignoring any closing quotes or brackets)
    trailing_strip = word.rstrip("".join(CLOSING_BRACKETS_QUOTES) + "\n")
    end_char = trailing_strip[-1] if trailing_strip else ""
    is_strong = ("\n" in word) or (end_char in STRONG_PUNCTUATION)
    is_weak = end_char in WEAK_PUNCTUATION

    # Clean core word for morphological and character count analysis
    core_word = word.rstrip("".join(STRONG_PUNCTUATION | WEAK_PUNCTUATION | CLOSING_BRACKETS_QUOTES) + "\n")
    core_len = len([c for c in core_word if c != ZWNJ])

    # If metrics not provided, compute dynamically
    if difficulty_score is None or frequency_score is None:
        from rsvp_engine.difficulty import calculate_word_metrics
        diff, freq, _ = calculate_word_metrics(word, core_word)
        if difficulty_score is None:
            difficulty_score = diff
        if frequency_score is None:
            frequency_score = freq

    diff = difficulty_score or 0.0
    freq = frequency_score if frequency_score is not None else 0.5

    # If semantic bonus not provided, compute dynamically from local context
    if semantic_pause_bonus is None:
        from rsvp_engine.semantics import analyze_token_boundaries
        _, _, semantic_pause_bonus = analyze_token_boundaries(word, next_word=next_word, prev_word=prev_word)

    # =========================================================================
    # Class 4: Sentence Endings (Terminal Boundary Consolidation) -> d: 185–260
    # =========================================================================
    if is_strong:
        weight = CLASS_4_SENTENCE_BASE
        if end_char == "…":
            weight = CLASS_4_ELLIPSIS_BASE

        # WPM-derived adaptation: at high WPM (>= 600), boost terminal pause multiplier
        # so absolute pause duration in milliseconds remains perceptually sufficient (> 140ms)
        effective_wpm = wpm or 300
        if effective_wpm >= 600:
            wpm_boost = min(40, int((effective_wpm - 600) / 10))
            weight += wpm_boost

        # Cognitive compounding: rare words at sentence ends require additional time
        # for lexical resolution before terminal proposition consolidation
        if diff >= 0.35:
            diff_boost = min(25, int((diff - 0.35) * 40))
            weight += diff_boost

        return int(min(CLASS_4_MAX_WEIGHT, max(CLASS_4_MIN_WEIGHT, weight)))

    # =========================================================================
    # Class 3: Clause Boundaries (Syntactic Clause Pause) -> d: 145–180
    # =========================================================================
    if is_weak:
        weight = CLASS_3_CLAUSE_BASE
        if end_char == ":":
            weight = CLASS_3_COLON_BASE

        # If introducing quotation (e.g. گفت: followed by «), provide slight emphasis
        if next_word and next_word.startswith("«"):
            weight += 5

        # Punctuation + semantic clause combination (Phase 6):
        # Two-tier semantic bonus:
        # - bonus == 15: Punctuated semantic boundary (weak punct + semantic clause cue, e.g. 'بود، اما')
        #   provides slight emphasis (+5) beyond plain comma pause (155 -> 160) while preserving Class 3 ceiling.
        # - bonus >= 30 (45): Unpunctuated semantic clause boundary (e.g. 'بود اما', 'می‌دانست که')
        #   lifts base reading duration up to Class 3 clause boundary threshold (145).
        if semantic_pause_bonus and semantic_pause_bonus == 15:
            weight += 5

        # Lexical difficulty adjustment at clause boundaries
        if diff >= 0.35:
            diff_boost = min(15, int((diff - 0.35) * 25))
            weight += diff_boost

        return int(min(CLASS_3_MAX_WEIGHT, max(CLASS_3_MIN_WEIGHT, weight)))

    # Phase 6: Unpunctuated semantic clause boundaries (e.g. می‌دانست که, سرد بود اما)
    # Lifts base word duration to Class 3 clause boundary entry threshold (d = 145)
    if semantic_pause_bonus and semantic_pause_bonus >= 30:
        weight = CLASS_2_MAX_WEIGHT
        if diff >= 0.35:
            diff_boost = min(15, int((diff - 0.35) * 25))
            weight += diff_boost
        return int(min(CLASS_3_MAX_WEIGHT, max(CLASS_2_MIN_WEIGHT, weight)))

    # =========================================================================
    # Class 2: Naturally Longer Reading Units (Cognitive Complexity) -> d: 115–145
    # =========================================================================
    is_compound = ZWNJ in core_word
    has_digits = any(c.isdigit() for c in core_word)

    # Verbal prefix detection (می / نمی with or without ZWNJ):
    # Routine verbal prefixes add 2-3 characters to an otherwise short base verb.
    # To evaluate genuine lexical reading load, effective stem length excludes routine verbal prefixes.
    has_verb_prefix = bool(re.match(r"^(?:می|نمی)\u200c?", core_word))
    effective_stem_len = core_len - (3 if core_word.startswith("نمی") else (2 if core_word.startswith("می") else 0))
    is_long = effective_stem_len >= CLASS_2_LONG_THRESHOLD

    # Frequency-aware demotion:
    # High-frequency words with low cognitive difficulty (e.g. routine ZWNJ-joined verbs like می‌خوانم,
    # past participles like گفته‌ام, plurals like کتاب‌ها, and continuous forms like می‌روند / میخوانم)
    # resolve with high frequency (>= 0.70) and low difficulty (<= 0.30).
    # These must NOT be penalized into Class 2 simply because they carry routine inflectional affixes or ZWNJ.
    # They are demoted to Class 1 (75–110).
    # In contrast, genuinely long lexical roots (e.g. دانشگاه len 7, استیضاح len 7), numerals (۱۲,۵۰۰),
    # and complex/rare compounds (کتاب‌خانه, بین‌المللی‌سازی, دل‌تنگ) remain length/compound-gated in Class 2.
    is_demoted_to_class_1 = (
        not has_digits
        and not is_long
        and freq >= 0.70
        and diff <= 0.30
        and (is_compound or has_verb_prefix)
    )

    if not is_demoted_to_class_1 and (is_compound or has_digits or is_long):
        weight = CLASS_2_MIN_WEIGHT
        if is_long:
            # Scaled smoothly with character count beyond threshold
            weight += min(20, (core_len - 6) * 3)
        if is_compound:
            weight += 10
        if has_digits:
            weight += 10

        # High difficulty/rarity bonus within Class 2 (applied to lexical words, avoiding double-counting digits)
        if not has_digits and diff >= 0.35:
            diff_bonus = min(15, int((diff - 0.30) * 20))
            weight += diff_bonus

        return int(min(CLASS_2_MAX_WEIGHT, max(CLASS_2_MIN_WEIGHT, weight)))

    # =========================================================================
    # Class 1: Normal Words & Function Words -> d: 75–110
    # =========================================================================
    # High-frequency functional prepositions/conjunctions without punctuation
    if core_word in FUNCTION_WORDS and core_len <= 3:
        return CLASS_1_FUNCTION_WORD

    # Sentence-initial orienting delay: when preceding token was a sentence end, newline, or explicit document start
    prev_trailing = prev_word.rstrip("".join(CLOSING_BRACKETS_QUOTES) + "\n") if prev_word else ""
    is_prev_strong = bool(prev_word and ("\n" in prev_word or (prev_trailing and prev_trailing[-1] in STRONG_PUNCTUATION)))
    is_doc_start = prev_word == "^"

    if is_doc_start or is_prev_strong:
        return CLASS_1_SENTENCE_INITIAL

    # High-frequency sight-words (e.g. این, آن, بود, شد, گفت) process faster than average content
    if freq >= 0.88 and diff <= 0.15:
        return 90

    # Rare/uncommon words in Class 1 receive cognitive dwell delay
    if diff >= 0.40:
        rare_delay = min(10, int((diff - 0.35) * 20))
        return min(CLASS_1_SENTENCE_INITIAL, CLASS_1_NORMAL_BASE + rare_delay)

    return CLASS_1_NORMAL_BASE
