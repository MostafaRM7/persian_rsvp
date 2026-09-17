"""Advanced Adaptive Cognitive Pacing Engine (Phase 7).

Combines WPM, lexical difficulty, frequency, morphology, punctuation,
semantic boundaries, sentence position, and surrounding context into a
single deterministic weighting pipeline per §10 of the development plan.

Classes:
- Class 1: Normal words, sight words, and function words (d: 75–110)
- Class 2: Naturally longer reading units, compounds, and numerals (d: 115–144)
- Class 3: Clause boundaries and weak punctuation (d: 145–180)
- Class 4: Sentence endings and terminal propositions (d: 185–320)
"""

from dataclasses import dataclass
import math
import re
from typing import Optional

from rsvp_engine.constants import (
    ALL_PUNCTUATION_CHARS,
    CLOSING_BRACKETS_QUOTES,
    STRONG_PUNCTUATION,
    WEAK_PUNCTUATION,
    ZWNJ,
)

# High-frequency Persian function words (prepositions & conjunctions) processed with lower cognitive load
FUNCTION_WORDS = frozenset({
    "و", "به", "در", "از", "با", "تا", "که", "یا", "چون", "اگر", "بر", "چو", "هم",
})

# Pacing Tier Thresholds (strictly disjoint per P3-14)
CLASS_1_MIN_WEIGHT = 75
CLASS_1_NORMAL_BASE = 100
CLASS_1_FUNCTION_WORD = 80
CLASS_1_SENTENCE_INITIAL = 110
CLASS_1_MAX_WEIGHT = 110

CLASS_2_LONG_THRESHOLD = 7
CLASS_2_MIN_WEIGHT = 115
CLASS_2_MAX_WEIGHT = 144

CLASS_3_MIN_WEIGHT = 145
CLASS_3_CLAUSE_BASE = 155
CLASS_3_COLON_BASE = 160
CLASS_3_MAX_WEIGHT = 180

CLASS_4_MIN_WEIGHT = 185
CLASS_4_SENTENCE_BASE = 200
CLASS_4_ELLIPSIS_BASE = 220
CLASS_4_MAX_WEIGHT = 320


@dataclass(frozen=True)
class TokenFeatures:
    """Strongly-typed feature vector for a single reading token.
    
    Decouples feature extraction from pacing decisions, enabling new signals
    (e.g. sentence position, syntactic role, personalization) to be added
    without altering the client playback contract or caller signatures.
    """
    word: str
    clean_word: str
    prev_word: Optional[str] = None
    next_word: Optional[str] = None
    char_count: int = 0
    is_compound: bool = False
    has_digits: bool = False
    has_verb_prefix: bool = False
    is_long: bool = False
    difficulty_score: float = 0.0
    frequency_score: float = 0.5
    complexity_score: float = 0.0
    is_sentence_end: bool = False
    is_clause_end: bool = False
    semantic_pause_bonus: int = 0
    sentence_position: int = 0       # 0-indexed position within current sentence
    sentence_length: int = 1         # Total tokens in current sentence
    is_sentence_initial: bool = False


@dataclass(frozen=True)
class PacingProfile:
    """Personalized pacing configuration for an individual reader per §11.
    
    Attributes:
        pause_intensity: Multiplier for punctuation and clause pauses (default 1.0, range [0.5, 1.5]).
        difficulty_tolerance: Cognitive dwell bias for difficult/rare words (default 0.0, range [-0.20, +0.20]).
        personalization_enabled: Master switch to enable/disable personalized pacing (default True).
    """
    pause_intensity: float = 1.0
    difficulty_tolerance: float = 0.0
    personalization_enabled: bool = True


def extract_token_features(
    word: str,
    prev_word: Optional[str] = None,
    next_word: Optional[str] = None,
    sentence_position: int = 0,
    sentence_length: int = 1,
    difficulty_score: Optional[float] = None,
    frequency_score: Optional[float] = None,
    complexity_score: Optional[float] = None,
    semantic_pause_bonus: Optional[int] = None,
) -> TokenFeatures:
    """Extracts a normalized TokenFeatures vector from raw token context."""
    if not word:
        return TokenFeatures(word="", clean_word="")

    strip_chars = "".join(ALL_PUNCTUATION_CHARS) + " \t\u200c"
    clean_word = word.strip(strip_chars)

    # Compute linguistic metrics if not provided
    if difficulty_score is None or frequency_score is None or complexity_score is None:
        from rsvp_engine.difficulty import calculate_word_metrics
        d_score, f_score, c_score = calculate_word_metrics(word, clean_word)
        difficulty_score = d_score if difficulty_score is None else difficulty_score
        frequency_score = f_score if frequency_score is None else frequency_score
        complexity_score = c_score if complexity_score is None else complexity_score

    # Compute semantic boundaries if not provided
    is_sent_end = False
    is_cl_end = False
    if semantic_pause_bonus is None:
        from rsvp_engine.semantics import analyze_token_boundaries
        is_sent_end, is_cl_end, semantic_pause_bonus = analyze_token_boundaries(
            word, next_word=next_word, prev_word=prev_word
        )
    else:
        from rsvp_engine.semantics import is_clause_boundary, is_sentence_boundary
        is_sent_end = is_sentence_boundary(word)
        is_cl_end = is_clause_boundary(word, next_word)

    # Word morphology and length features
    char_count = len([c for c in clean_word if c != ZWNJ])
    is_compound = ZWNJ in clean_word
    has_digits = any(c.isdigit() for c in clean_word)
    has_verb_prefix = bool(re.match(r"^(?:می|نمی)\u200c?", clean_word))
    effective_stem_len = char_count - (3 if clean_word.startswith("نمی") else (2 if clean_word.startswith("می") else 0))
    is_long = effective_stem_len >= CLASS_2_LONG_THRESHOLD

    # Sentence position context: sentence initial if explicit start '^' or following terminal/newline
    is_sentence_initial = False
    if prev_word == "^":
        is_sentence_initial = True
    elif prev_word:
        prev_strip = prev_word.rstrip("".join(CLOSING_BRACKETS_QUOTES) + "\n")
        if "\n" in prev_word or (prev_strip and prev_strip[-1] in STRONG_PUNCTUATION):
            is_sentence_initial = True

    return TokenFeatures(
        word=word,
        clean_word=clean_word,
        prev_word=prev_word,
        next_word=next_word,
        char_count=char_count,
        is_compound=is_compound,
        has_digits=has_digits,
        has_verb_prefix=has_verb_prefix,
        is_long=is_long,
        difficulty_score=difficulty_score or 0.0,
        frequency_score=frequency_score if frequency_score is not None else 0.5,
        complexity_score=complexity_score or 0.0,
        is_sentence_end=is_sent_end,
        is_clause_end=is_cl_end,
        semantic_pause_bonus=semantic_pause_bonus or 0,
        sentence_position=sentence_position,
        sentence_length=max(1, sentence_length),
        is_sentence_initial=is_sentence_initial,
    )


def compute_duration_weight(
    features: TokenFeatures,
    wpm: int = 300,
    profile: Optional[PacingProfile] = None,
) -> int:
    """Unified, deterministic weighting stage combining all extracted signals.
    
    Evaluates features across Classes 1–4, enforcing strict disjoint ranges,
    high-WPM cognitive pause floors, contextual cadence modulation,
    and server-controlled personalization profiles (Phase 8).
    """
    word = features.word
    if not word:
        return CLASS_1_NORMAL_BASE

    pause_intensity = profile.pause_intensity if (profile and profile.personalization_enabled) else 1.0
    diff_tolerance = profile.difficulty_tolerance if (profile and profile.personalization_enabled) else 0.0

    clean_word = features.clean_word
    diff = max(0.0, min(1.0, features.difficulty_score - diff_tolerance))
    freq = features.frequency_score
    sem_bonus = features.semantic_pause_bonus
    effective_wpm = wpm or 300

    trailing_strip = word.rstrip("".join(CLOSING_BRACKETS_QUOTES) + "\n")
    end_char = trailing_strip[-1] if trailing_strip else ""
    is_strong = ("\n" in word) or (end_char in STRONG_PUNCTUATION) or features.is_sentence_end
    is_weak = (end_char in WEAK_PUNCTUATION)

    # =========================================================================
    # Class 4: Sentence Endings (Terminal Boundary Consolidation) -> d: 185–320
    # =========================================================================
    if is_strong:
        weight = CLASS_4_SENTENCE_BASE
        if end_char == "…":
            weight = CLASS_4_ELLIPSIS_BASE

        # WPM-derived adaptation: ensure absolute pause duration remains >= 140ms
        # duration_ms = (60000 / wpm) * (weight / 100) >= 140 ms -> weight >= 140 * wpm / 600
        if effective_wpm >= 600:
            min_cognitive_d = int(math.ceil(145 * effective_wpm / 600))
            wpm_boost = max(int((effective_wpm - 600) / 10), min_cognitive_d - CLASS_4_SENTENCE_BASE)
            weight += wpm_boost

        # Cognitive compounding: rare words at sentence ends require extra resolution time
        if diff >= 0.35:
            diff_boost = min(25, int((diff - 0.35) * 40))
            weight += diff_boost

        # Personalization: scale pause intensity
        if pause_intensity != 1.0:
            weight = int(weight * pause_intensity)

        # High-WPM cognitive floor guarantee:
        # Personalization may compress pauses toward the cognitive floor, but never through it.
        # Absolute pause duration must remain >= 140ms across high WPMs (>= 600 WPM).
        if effective_wpm >= 600:
            min_cognitive_d = int(math.ceil(145 * effective_wpm / 600))
            weight = max(weight, min_cognitive_d)

        return int(min(CLASS_4_MAX_WEIGHT, max(CLASS_4_MIN_WEIGHT, weight)))

    # =========================================================================
    # Class 3: Clause Boundaries (Syntactic Clause Pause) -> d: 145–180
    # =========================================================================
    if is_weak:
        weight = CLASS_3_CLAUSE_BASE
        if end_char == ":":
            weight = CLASS_3_COLON_BASE

        # If introducing quotation (e.g. گفت: followed by «), provide slight emphasis
        if features.next_word and features.next_word.startswith("«"):
            weight += 5

        # Punctuation + semantic clause combination bonus:
        # Punctuated semantic boundary (e.g. 'بود، اما') provides +5 beyond base comma
        if sem_bonus == 15:
            weight += 5

        # Lexical difficulty adjustment at clause boundaries
        if diff >= 0.35:
            diff_boost = min(15, int((diff - 0.35) * 25))
            weight += diff_boost

        # Personalization: scale pause intensity
        if pause_intensity != 1.0:
            weight = int(weight * pause_intensity)

        return int(min(CLASS_3_MAX_WEIGHT, max(CLASS_3_MIN_WEIGHT, weight)))

    # Unpunctuated semantic clause boundaries (e.g. می‌دانست که, سرد بود اما)
    # Lifts base word duration to Class 3 clause boundary entry threshold (d = 145)
    if sem_bonus >= 30:
        weight = CLASS_3_MIN_WEIGHT
        if diff >= 0.35:
            diff_boost = min(15, int((diff - 0.35) * 25))
            weight += diff_boost
        if pause_intensity != 1.0:
            weight = int(weight * pause_intensity)
        return int(min(CLASS_3_MAX_WEIGHT, max(CLASS_3_MIN_WEIGHT, weight)))

    # =========================================================================
    # Class 2: Naturally Longer Reading Units (Cognitive Complexity) -> d: 115–144
    # =========================================================================
    # Frequency-aware demotion:
    # Routine inflections (می‌خوانم, گفته‌ام, کتاب‌ها, می‌روند) with high frequency and low difficulty
    # demote to Class 1. Genuinely long roots, numerals, and rare compounds stay in Class 2.
    is_demoted_to_class_1 = (
        not features.has_digits
        and not features.is_long
        and freq >= 0.70
        and diff <= 0.30
        and (features.is_compound or features.has_verb_prefix)
    )

    if not is_demoted_to_class_1 and (features.is_compound or features.has_digits or features.is_long):
        weight = CLASS_2_MIN_WEIGHT
        if features.is_long:
            weight += min(20, (features.char_count - 6) * 3)
        if features.is_compound:
            weight += 10
        if features.has_digits:
            weight += 10

        if not features.has_digits and diff >= 0.35:
            diff_bonus = min(15, int((diff - 0.30) * 20))
            weight += diff_bonus

        return int(min(CLASS_2_MAX_WEIGHT, max(CLASS_2_MIN_WEIGHT, weight)))

    # =========================================================================
    # Class 1: Normal Words & Function Words -> d: 75–110
    # =========================================================================
    # High-frequency functional prepositions/conjunctions without punctuation
    if clean_word in FUNCTION_WORDS and features.char_count <= 3:
        return CLASS_1_FUNCTION_WORD

    # Sentence-initial orienting delay
    if features.is_sentence_initial:
        return CLASS_1_SENTENCE_INITIAL

    # Extensibility proof signal (Phase 7): sentence position cadence
    # In long sentences (>= 15 tokens), words in late position (>= 12) without clause marks
    # receive subtle cadence modulation (+3ms duration weight) to relieve cognitive fatigue.
    cadence_bonus = 0
    if features.sentence_position >= 12 and features.sentence_length >= 15:
        cadence_bonus = 3

    # High-frequency sight-words (e.g. این, آن, بود, شد, گفت) process faster than average content
    if freq >= 0.88 and diff <= 0.15:
        return 90 + cadence_bonus

    # Rare/uncommon words in Class 1 receive cognitive dwell delay
    if diff >= 0.40:
        rare_delay = min(10, int((diff - 0.35) * 20))
        return min(CLASS_1_SENTENCE_INITIAL, CLASS_1_NORMAL_BASE + rare_delay + cadence_bonus)

    return min(CLASS_1_SENTENCE_INITIAL, CLASS_1_NORMAL_BASE + cadence_bonus)


def calculate_duration_weight(
    word: str,
    prev_word: Optional[str] = None,
    next_word: Optional[str] = None,
    wpm: Optional[int] = 300,
    difficulty_score: Optional[float] = None,
    frequency_score: Optional[float] = None,
    complexity_score: Optional[float] = None,
    semantic_pause_bonus: Optional[int] = None,
    sentence_position: int = 0,
    sentence_length: int = 1,
    profile: Optional[PacingProfile] = None,
) -> int:
    """Facade for compute_duration_weight preserving full backward compatibility.

    Accepts complexity_score (P3-23) so direct-facade callers feed the pipeline
    the same difficulty inputs as the engine path.
    """
    features = extract_token_features(
        word=word,
        prev_word=prev_word,
        next_word=next_word,
        sentence_position=sentence_position,
        sentence_length=sentence_length,
        difficulty_score=difficulty_score,
        frequency_score=frequency_score,
        complexity_score=complexity_score,
        semantic_pause_bonus=semantic_pause_bonus,
    )
    return compute_duration_weight(features=features, wpm=wpm or 300, profile=profile)
