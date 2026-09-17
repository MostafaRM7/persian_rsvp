"""Data contracts and schemas for the RSVP Engine.

Defines:
- Input contract for text processing requests
- Internal token representation
- Public token and chunk schemas returned to the client player
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


ENGINE_VERSION = "2026.08.1"


class EngineInput(BaseModel):
    """Input contract for the RSVP Engine."""
    model_config = ConfigDict(frozen=True)

    text: str = Field(..., min_length=1, max_length=100_000, description="Raw Persian text to process")
    chunk_index: int = Field(default=0, ge=0, description="0-indexed chunk index to retrieve")
    chunk_size: int = Field(default=150, ge=1, le=500, description="Tokens per chunk")
    wpm: Optional[int] = Field(default=300, ge=60, le=1200, description="Target reading speed (WPM) for pacing derivation")


class InternalToken(BaseModel):
    """Internal token model used within engine processing pipeline.
    
    Can contain rich linguistic metadata not exposed to the client.
    """
    raw_word: str
    clean_word: str
    char_count: int
    orp_index: int
    duration_weight: int
    is_sentence_end: bool = False
    is_clause_end: bool = False
    is_compound: bool = False
    has_digits: bool = False
    difficulty_score: float = 0.0
    frequency_score: float = 0.5
    complexity_score: float = 0.0

    def to_public_token(self) -> "RSVPToken":
        return RSVPToken(w=self.raw_word.rstrip("\n"), orp=self.orp_index, d=self.duration_weight)


class RSVPToken(BaseModel):
    """Public client-safe token contract.
    
    Exposes only the minimal opaque representation required by the dumb player:
    - w: display text
    - orp: 0-indexed unicode character offset of the focal letter
    - d: opaque duration weight (100 = 1.0x base delay)
    """
    model_config = ConfigDict(frozen=True)

    w: str = Field(..., description="Display token with intact Persian typography")
    orp: int = Field(..., ge=0, description="0-indexed character offset of the ORP focal letter")
    d: int = Field(default=100, ge=50, le=500, description="Opaque duration factor (100 = 1.0x)")


class RSVPChunkResponse(BaseModel):
    """Public chunked response for client buffer management and prefetching."""
    model_config = ConfigDict(frozen=True)

    engine_version: str = Field(default=ENGINE_VERSION, description="Server-controlled engine version")
    chunk_index: int = Field(..., ge=0, description="Current chunk index")
    total_chunks: int = Field(..., ge=0, description="Total chunks available")
    total_tokens: int = Field(..., ge=0, description="Total tokens in the complete plan")
    has_more: bool = Field(..., description="True if subsequent chunks exist on the server")
    tokens: List[RSVPToken] = Field(default_factory=list, description="List of tokens in this chunk")
