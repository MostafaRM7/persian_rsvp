"""RSVPEngine facade.

Coordinates normalization, tokenization, ORP decision logic, feature extraction,
adaptive cognitive pacing, and chunking pipelines behind a clean, testable interface.

Phase 10: full-text token planning is memoized (measured bottleneck — §13).
A 10k-token book costs ~155 ms to plan; without memoization every chunk request
re-plans the entire text, so one playback session burns seconds of repeated CPU.
"""

from collections import OrderedDict
from typing import List, Optional, Tuple
from rsvp_engine.chunking import create_chunks
from rsvp_engine.constants import ALL_PUNCTUATION_CHARS, ZWNJ
from rsvp_engine.difficulty import calculate_word_metrics
from rsvp_engine.models import ENGINE_VERSION, EngineInput, InternalToken, RSVPChunkResponse, RSVPToken
from rsvp_engine.normalization import normalize_text
from rsvp_engine.orp import calculate_orp
from rsvp_engine.pacing import PacingProfile, compute_duration_weight, extract_token_features
from rsvp_engine.semantics import analyze_token_boundaries, is_sentence_boundary
from rsvp_engine.tokenizer import tokenize


class RSVPEngine:
    """Facade for the proprietary RSVP intelligence engine."""

    # ------------------------------------------------------------------
    # Token-plan memoization (Phase 10, §13: measured, not guessed).
    # Bounded, insertion-order-evicting LRU. Key: (normalized text, wpm,
    # personalization scalars, ENGINE_VERSION) — so an engine upgrade can
    # never serve a stale plan. Token budget (not entry count) bounds memory.
    # Isolation: cached values are never handed to callers; every chunk gets
    # deep-copied tokens, and profile-derived content is part of the key.
    # Single-process only — horizontal scaling caches per process, semantics
    # unchanged (Phase 10 §13; shared-store concerns tracked as P3-27).
    # ------------------------------------------------------------------
    _plan_cache: "OrderedDict[Tuple, List[RSVPToken]]" = OrderedDict()
    _PLAN_CACHE_MAX_TOKENS = 20_000
    _plan_cache_tokens = 0
    _plan_cache_hits = 0
    _plan_cache_misses = 0

    @classmethod
    def _plan_cache_key(
        cls, text: str, wpm: int, profile: Optional[PacingProfile]
    ) -> Tuple:
        if profile is None or not profile.personalization_enabled:
            intensity, tolerance = 1.0, 0.0
        else:
            intensity = float(profile.pause_intensity)
            tolerance = float(profile.difficulty_tolerance)
        return (text, int(wpm), intensity, tolerance, ENGINE_VERSION)

    @classmethod
    def generate_internal_tokens(
        cls, text: str, wpm: int = 300, profile: Optional[PacingProfile] = None
    ) -> List[InternalToken]:
        """Linguistic analysis pipeline producing rich internal tokens per §10, §11."""
        normalized = normalize_text(text)
        raw_tokens = tokenize(normalized)

        total = len(raw_tokens)
        if total == 0:
            return []

        # 1. Pre-pass: sentence span segmentation to track token sentence position and sentence length
        sentence_spans = []
        current_start = 0
        for idx, w in enumerate(raw_tokens):
            if is_sentence_boundary(w) or idx == total - 1:
                sentence_spans.append((current_start, idx))
                current_start = idx + 1

        token_sentence_info = {}
        for start, end in sentence_spans:
            s_len = end - start + 1
            for pos, idx in enumerate(range(start, end + 1)):
                token_sentence_info[idx] = (pos, s_len)

        # 2. Pipeline pass: ORP, features, pacing
        internal_tokens: List[InternalToken] = []
        strip_chars = "".join(ALL_PUNCTUATION_CHARS) + " \t\u200c"

        for i, word in enumerate(raw_tokens):
            prev_w = raw_tokens[i - 1] if i > 0 else "^"
            next_w = raw_tokens[i + 1] if i + 1 < total else None
            sent_pos, sent_len = token_sentence_info[i]

            clean_word = word.strip(strip_chars)
            orp = calculate_orp(word)

            diff_score, freq_score, comp_score = calculate_word_metrics(word, clean_word)
            is_sentence_end, is_clause_end, sem_bonus = analyze_token_boundaries(
                word, next_word=next_w, prev_word=prev_w
            )

            features = extract_token_features(
                word=word,
                prev_word=prev_w,
                next_word=next_w,
                sentence_position=sent_pos,
                sentence_length=sent_len,
                difficulty_score=diff_score,
                frequency_score=freq_score,
                complexity_score=comp_score,
                semantic_pause_bonus=sem_bonus,
            )

            weight = compute_duration_weight(features=features, wpm=wpm, profile=profile)

            is_compound = ZWNJ in clean_word
            has_digits = any(c.isdigit() for c in clean_word)

            token = InternalToken(
                raw_word=word,
                clean_word=clean_word,
                char_count=len([c for c in clean_word if c != ZWNJ]),
                orp_index=orp,
                duration_weight=weight,
                is_sentence_end=is_sentence_end,
                is_clause_end=is_clause_end,
                is_compound=is_compound,
                has_digits=has_digits,
                difficulty_score=diff_score,
                frequency_score=freq_score,
                complexity_score=comp_score,
            )
            internal_tokens.append(token)

        return internal_tokens

    @classmethod
    def generate_token_plan(
        cls, text: str, wpm: int = 300, profile: Optional[PacingProfile] = None, *, use_cache: bool = True
    ) -> List[RSVPToken]:
        """Generates the public client-safe token plan from raw input text.

        Results are memoized per (text, wpm, personalization scalars, version).
        The returned list is fresh, but token objects are shared with the cache:
        RSVPToken is frozen (immutable — mutation raises), so sharing is safe and
        copy-free. If RSVPToken ever becomes mutable, reintroduce per-token
        model_copy() here. use_cache=False bypasses memoization entirely
        (determinism tests compare full pipelines, not cache hits).
        """
        if not use_cache:
            internal_tokens = cls.generate_internal_tokens(text, wpm=wpm, profile=profile)
            return [t.to_public_token() for t in internal_tokens]

        key = cls._plan_cache_key(text, wpm, profile)
        cached = cls._plan_cache.get(key)
        if cached is not None:
            cls._plan_cache.move_to_end(key)  # LRU refresh
            cls._plan_cache_hits += 1
            return list(cached)  # fresh list; frozen token objects shared safely

        cls._plan_cache_misses += 1
        internal_tokens = cls.generate_internal_tokens(text, wpm=wpm, profile=profile)
        plan = [t.to_public_token() for t in internal_tokens]

        cls._plan_cache[key] = plan
        cls._plan_cache_tokens += len(plan)
        while cls._plan_cache_tokens > cls._PLAN_CACHE_MAX_TOKENS and len(cls._plan_cache) > 1:
            _, evicted = cls._plan_cache.popitem(last=False)  # LRU eviction
            cls._plan_cache_tokens -= len(evicted)
        return list(plan)

    @classmethod
    def clear_plan_cache(cls) -> None:
        """Drops all memoized plans (memory pressure, tests, engine reload)."""
        cls._plan_cache.clear()
        cls._plan_cache_tokens = 0
        cls._plan_cache_hits = 0
        cls._plan_cache_misses = 0

    @classmethod
    def plan_cache_stats(cls) -> dict:
        """Cache observability for profiling (§13: measure, don't guess)."""
        return {
            "entries": len(cls._plan_cache),
            "tokens": cls._plan_cache_tokens,
            "hits": cls._plan_cache_hits,
            "misses": cls._plan_cache_misses,
        }

    @classmethod
    def get_chunk(
        cls,
        text: str,
        chunk_index: int = 0,
        chunk_size: int = 150,
        wpm: int = 300,
        profile: Optional[PacingProfile] = None,
    ) -> RSVPChunkResponse:
        """Processes text and returns a paginated chunk for client playback."""
        plan = cls.generate_token_plan(text, wpm=wpm, profile=profile)
        return create_chunks(tokens=plan, chunk_index=chunk_index, chunk_size=chunk_size)

    @classmethod
    def process_input(
        cls, engine_input: EngineInput, profile: Optional[PacingProfile] = None
    ) -> RSVPChunkResponse:
        """Processes strongly-typed EngineInput contract."""
        return cls.get_chunk(
            text=engine_input.text,
            chunk_index=engine_input.chunk_index,
            chunk_size=engine_input.chunk_size,
            wpm=engine_input.wpm or 300,
            profile=profile,
        )

