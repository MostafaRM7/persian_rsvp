/**
 * RSVP Token Buffer Abstraction.
 * 
 * Manages the client-side pre-fetched queue of tokens.
 * Supports starting from an arbitrary chunk (for reading resumption),
 * tracks absolute and relative positions, and determines when prefetching is needed.
 */

export class TokenBuffer {
  constructor() {
    this.tokens = [];
    this.chunkIndex = 0;
    this.initialChunkIndex = 0;
    this.baseTokenOffset = 0;
    this.totalChunks = 0;
    this.totalTokens = 0;
    this.hasMore = false;
    this.isPrefetching = false;
  }

  clear() {
    this.tokens = [];
    this.chunkIndex = 0;
    this.initialChunkIndex = 0;
    this.baseTokenOffset = 0;
    this.totalChunks = 0;
    this.totalTokens = 0;
    this.hasMore = false;
    this.isPrefetching = false;
  }

  loadInitial(chunkResponse, chunkSize = 150) {
    this.tokens = chunkResponse.tokens || [];
    this.chunkIndex = chunkResponse.chunk_index;
    this.initialChunkIndex = chunkResponse.chunk_index;
    this.baseTokenOffset = chunkResponse.chunk_index * chunkSize;
    this.totalChunks = chunkResponse.total_chunks;
    this.totalTokens = chunkResponse.total_tokens;
    this.hasMore = chunkResponse.has_more;
    this.isPrefetching = false;
  }

  appendChunk(chunkResponse) {
    if (chunkResponse.tokens && chunkResponse.tokens.length > 0) {
      this.tokens.push(...chunkResponse.tokens);
    }
    this.chunkIndex = chunkResponse.chunk_index;
    this.totalChunks = chunkResponse.total_chunks;
    this.totalTokens = chunkResponse.total_tokens;
    this.hasMore = chunkResponse.has_more;
  }

  get(index) {
    if (index >= 0 && index < this.tokens.length) {
      return this.tokens[index];
    }
    return null;
  }

  getAbsoluteIndex(localIndex) {
    return this.baseTokenOffset + localIndex;
  }

  getLocalIndex(absoluteIndex) {
    return Math.max(0, absoluteIndex - this.baseTokenOffset);
  }

  length() {
    return this.tokens.length;
  }

  remaining(currentIndex) {
    return Math.max(0, this.tokens.length - currentIndex);
  }

  needsPrefetch(currentIndex, threshold = 45) {
    if (!this.hasMore || this.isPrefetching) {
      return false;
    }
    return this.remaining(currentIndex) <= threshold;
  }
}
