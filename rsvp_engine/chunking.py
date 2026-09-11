"""Chunking and prefetching boundary.

Paginates token streams into discrete batches to enable client buffering
and prevent per-word networking.
"""

import math
from typing import List
from rsvp_engine.models import ENGINE_VERSION, RSVPChunkResponse, RSVPToken


def create_chunks(
    tokens: List[RSVPToken],
    chunk_index: int = 0,
    chunk_size: int = 150,
    engine_version: str = ENGINE_VERSION,
) -> RSVPChunkResponse:
    """Extracts the requested chunk window from the complete token plan."""
    total_tokens = len(tokens)
    if total_tokens == 0 or chunk_size <= 0:
        return RSVPChunkResponse(
            engine_version=engine_version,
            chunk_index=0,
            total_chunks=0,
            total_tokens=0,
            has_more=False,
            tokens=[],
        )

    total_chunks = math.ceil(total_tokens / chunk_size)
    safe_index = max(0, min(chunk_index, total_chunks - 1))

    start_idx = safe_index * chunk_size
    end_idx = min(start_idx + chunk_size, total_tokens)

    chunk_tokens = tokens[start_idx:end_idx]
    has_more = end_idx < total_tokens

    return RSVPChunkResponse(
        engine_version=engine_version,
        chunk_index=safe_index,
        total_chunks=total_chunks,
        total_tokens=total_tokens,
        has_more=has_more,
        tokens=chunk_tokens,
    )
