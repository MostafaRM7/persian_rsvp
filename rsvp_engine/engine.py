"""RSVPEngine facade.

Coordinates normalization, tokenization, ORP decision logic, pacing,
and chunking pipelines behind a clean, testable interface.
"""

from typing import List
from rsvp_engine.chunking import create_chunks
from rsvp_engine.difficulty import calculate_word_metrics
from rsvp_engine.models import EngineInput, InternalToken, RSVPChunkResponse, RSVPToken
from rsvp_engine.normalization import ZWNJ, normalize_text
from rsvp_engine.orp import PUNCTUATION_CHARS, calculate_orp
from rsvp_engine.pacing import STRONG_PUNCTUATION, WEAK_PUNCTUATION, calculate_duration_weight
from rsvp_engine.semantics import analyze_token_boundaries
from rsvp_engine.tokenizer import tokenize


class RSVPEngine:
    """Facade for the proprietary RSVP intelligence engine."""

    @classmethod
    def generate_internal_tokens(cls, text: str, wpm: int = 300) -> List[InternalToken]:
        """Linguistic analysis pipeline producing rich internal tokens."""
        normalized = normalize_text(text)
        raw_tokens = tokenize(normalized)

        internal_tokens: List[InternalToken] = []
        total = len(raw_tokens)

        for i, word in enumerate(raw_tokens):
            prev_w = raw_tokens[i - 1] if i > 0 else "^"
            next_w = raw_tokens[i + 1] if i + 1 < total else None

            clean_word = word.strip("".join(PUNCTUATION_CHARS) + "\n")
            orp = calculate_orp(word)

            diff_score, freq_score, comp_score = calculate_word_metrics(word, clean_word)
            is_sentence_end, is_clause_end, sem_bonus = analyze_token_boundaries(
                word, next_word=next_w, prev_word=prev_w
            )
            weight = calculate_duration_weight(
                word, prev_w, next_w, wpm=wpm,
                difficulty_score=diff_score, frequency_score=freq_score,
                semantic_pause_bonus=sem_bonus,
            )

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
    def generate_token_plan(cls, text: str, wpm: int = 300) -> List[RSVPToken]:
        """Generates the public client-safe token plan from raw input text."""
        internal_tokens = cls.generate_internal_tokens(text, wpm=wpm)
        return [t.to_public_token() for t in internal_tokens]

    @classmethod
    def get_chunk(
        cls,
        text: str,
        chunk_index: int = 0,
        chunk_size: int = 150,
        wpm: int = 300,
    ) -> RSVPChunkResponse:
        """Processes text and returns a paginated chunk for client playback."""
        plan = cls.generate_token_plan(text, wpm=wpm)
        return create_chunks(tokens=plan, chunk_index=chunk_index, chunk_size=chunk_size)

    @classmethod
    def process_input(cls, engine_input: EngineInput) -> RSVPChunkResponse:
        """Processes strongly-typed EngineInput contract."""
        return cls.get_chunk(
            text=engine_input.text,
            chunk_index=engine_input.chunk_index,
            chunk_size=engine_input.chunk_size,
            wpm=engine_input.wpm or 300,
        )
