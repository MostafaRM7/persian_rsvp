/**
 * RSVP Player Abstraction.
 * 
 * Orchestrates Buffer, Timer, Renderer, and API Client into a coherent player.
 * Dispatches progress and state events to UI listeners.
 * 
 * Features:
 * - In-flight prefetch deduplication (prevents duplicate chunk race)
 * - Exponential backoff retry on buffer underrun
 * - Arbitrary position resumption across multi-chunk texts
 * - Drift-compensated timing loop with smooth pickup on resume
 */

import { fetchPlanChunk } from './api.js';
import { TokenBuffer } from './buffer.js';
import { WordRenderer } from './renderer.js';
import { PlaybackTimer } from './timer.js';

export class RSVPPlayer {
  constructor({
    wordElement,
    focusElement,
    chunkSize = 150,
    prefetchThreshold = 45,
    getAuthToken = () => null,
    onProgress = () => {},
    onStateChange = () => {},
    onFinish = () => {},
  }) {
    this.buffer = new TokenBuffer();
    this.renderer = new WordRenderer(wordElement, focusElement);
    this.timer = new PlaybackTimer();

    this.chunkSize = chunkSize;
    this.prefetchThreshold = prefetchThreshold;
    this.getAuthToken = getAuthToken;

    this.onProgress = onProgress;
    this.onStateChange = onStateChange;
    this.onFinish = onFinish;

    this.state = 'idle'; // idle | loading | running | paused | buffering | done
    this.index = 0;
    this.wpm = 300;
    this.currentText = '';
    this.currentTextId = null;

    // Deduplication handle for in-flight requests
    this.inFlightPrefetchPromise = null;
    this.fetchGeneration = 0;
  }

  setState(newState) {
    this.state = newState;
    this.onStateChange(newState);
  }

  async loadPlan(text, textId = null, targetPosition = 0) {
    this.reset();
    this.currentText = text;
    this.currentTextId = textId;
    this.setState('loading');

    const startChunkIndex = Math.floor(Math.max(0, targetPosition) / this.chunkSize);
    const fetchGen = ++this.fetchGeneration;

    try {
      const response = await fetchPlanChunk({
        text: this.currentText,
        textId: this.currentTextId,
        chunkIndex: startChunkIndex,
        chunkSize: this.chunkSize,
        authToken: this.getAuthToken(),
        wpm: this.wpm,
      });

      if (fetchGen !== this.fetchGeneration) {
        return false;
      }

      if (!response || !response.tokens || response.tokens.length === 0) {
        this.renderer.setMessage('متنی برای نمایش وجود ندارد');
        this.setState('idle');
        return false;
      }

      this.buffer.loadInitial(response, this.chunkSize);
      this.index = this.buffer.getLocalIndex(targetPosition);
      this.showCurrentWord();
      this.setState('idle');
      return true;
    } catch (err) {
      console.error('Failed to load initial RSVP plan:', err);
      this.renderer.setMessage('خطا در دریافت متن');
      this.setState('idle');
      return false;
    }
  }

  showCurrentWord() {
    const token = this.buffer.get(this.index);
    if (token) {
      this.renderer.render(token);
    }
    const absoluteIndex = this.buffer.getAbsoluteIndex(this.index);
    const total = this.buffer.totalTokens || this.buffer.length();
    const pct = total > 0 ? ((absoluteIndex + 1) / total) * 100 : 0;

    this.onProgress({
      index: absoluteIndex,
      total,
      pct,
    });
  }

  async fetchNextChunk() {
    if (this.inFlightPrefetchPromise) {
      return await this.inFlightPrefetchPromise;
    }

    const targetChunkIndex = this.buffer.chunkIndex + 1;
    this.buffer.isPrefetching = true;
    const fetchGen = ++this.fetchGeneration;

    this.inFlightPrefetchPromise = (async () => {
      try {
        const nextChunk = await fetchPlanChunk({
          text: this.currentText,
          textId: this.currentTextId,
          chunkIndex: targetChunkIndex,
          chunkSize: this.chunkSize,
          authToken: this.getAuthToken(),
          wpm: this.wpm,
        });
        if (fetchGen === this.fetchGeneration && nextChunk && nextChunk.tokens && nextChunk.tokens.length > 0) {
          this.buffer.appendChunk(nextChunk);
        }
        return nextChunk;
      } finally {
        if (fetchGen === this.fetchGeneration) {
          this.buffer.isPrefetching = false;
          this.inFlightPrefetchPromise = null;
        }
      }
    })();

    return await this.inFlightPrefetchPromise;
  }

  async maybePrefetch() {
    if (this.buffer.needsPrefetch(this.index, this.prefetchThreshold) && !this.inFlightPrefetchPromise) {
      try {
        await this.fetchNextChunk();
      } catch (err) {
        console.warn('Background prefetch failed; will retry when buffer reaches threshold:', err);
      }
    }
  }

  async handleBufferUnderrun(maxRetries = 3) {
    this.setState('buffering');
    this.renderer.setMessage('...');

    let attempt = 0;
    while (attempt < maxRetries) {
      try {
        const nextChunk = await this.fetchNextChunk();
        if (nextChunk && nextChunk.tokens && nextChunk.tokens.length > 0) {
          if (this.state === 'buffering') {
            this.setState('running');
            this.timer.resetAnchor();
            this.loop();
          }
          return;
        }
        // Empty 200 response: treat like a failure so retries can't spin forever.
        attempt++;
        console.warn(`Buffer underrun: empty chunk returned (attempt ${attempt}/${maxRetries})`);
      } catch (err) {
        attempt++;
        console.warn(`Buffer underrun retry ${attempt}/${maxRetries} failed:`, err);
      }
      if (attempt < maxRetries) {
        await new Promise((res) => setTimeout(res, 500 * Math.pow(2, attempt - 1)));
      }
    }

    this.finish();
  }

  async start() {
    if (this.state === 'running') return;
    if (this.state === 'paused') {
      this.resume();
      return;
    }
    // UX Nit: If finished, restart from beginning
    if (this.state === 'done') {
      this.index = 0;
    }

    if (this.buffer.length() === 0) {
      const loaded = await this.loadPlan(this.currentText, this.currentTextId);
      if (!loaded) return;
    }

    this.setState('running');
    this.timer.resetAnchor();
    this.loop();
  }

  loop() {
    if (this.state !== 'running') return;

    if (this.index >= this.buffer.length()) {
      if (this.buffer.hasMore) {
        this.handleBufferUnderrun();
        return;
      }
      this.finish();
      return;
    }

    const currentToken = this.buffer.get(this.index);
    this.showCurrentWord();
    this.index += 1;

    // Trigger background prefetch asynchronously
    this.maybePrefetch();

    // Schedule next frame with drift-compensated delay
    const delay = this.timer.calculateDelay(this.wpm, currentToken.d);
    this.timer.schedule(() => this.loop(), delay);
  }

  pause() {
    if (this.state === 'running') {
      this.timer.clear();
      this.setState('paused');
    }
  }

  resume() {
    if (this.state === 'paused') {
      this.setState('running');
      this.timer.resetAnchor();
      // Snappy pickup on resume: 50ms delay instead of full previous word delay
      this.timer.schedule(() => this.loop(), 50);
    }
  }

  reset() {
    this.timer.clear();
    this.renderer.clear();
    this.index = 0;
    this.buffer.clear();
    this.fetchGeneration = (this.fetchGeneration || 0) + 1;
    this.inFlightPrefetchPromise = null;
    this.setState('idle');
    this.onProgress({ index: 0, total: 0, pct: 0 });
  }

  finish() {
    this.timer.clear();
    this.renderer.setMessage('پایان');
    this.setState('done');
    const absoluteIndex = this.buffer.getAbsoluteIndex(this.index);
    this.onFinish(absoluteIndex);
  }

  async setWpm(newWpm) {
    this.wpm = Math.max(60, Math.min(1200, Math.round(newWpm)));

    // Do NOT refetch when there is no buffer (loadPlan hasn't run)
    if (this.buffer.length() === 0 || this.state === 'loading') {
      return;
    }

    // Edge case: playback finished
    if (this.state === 'done') {
      return;
    }

    const absoluteIndex = this.buffer.getAbsoluteIndex(this.index);
    const maxChunk = this.buffer.totalChunks > 0 ? this.buffer.totalChunks - 1 : 0;
    const chunkToFetch = Math.min(maxChunk, Math.floor(absoluteIndex / this.chunkSize));

    const fetchGen = ++this.fetchGeneration;
    this.buffer.isPrefetching = true;

    // Invalidate and await-and-discard any existing in-flight prefetch
    if (this.inFlightPrefetchPromise) {
      try {
        await this.inFlightPrefetchPromise;
      } catch (err) {
        // Discard errors from superseded in-flight prefetch
      }
    }

    // If another WPM change superseded us while awaiting, yield to the newer one
    if (fetchGen !== this.fetchGeneration) {
      return;
    }

    this.inFlightPrefetchPromise = (async () => {
      try {
        const response = await fetchPlanChunk({
          text: this.currentText,
          textId: this.currentTextId,
          chunkIndex: chunkToFetch,
          chunkSize: this.chunkSize,
          authToken: this.getAuthToken(),
          wpm: this.wpm,
        });

        if (fetchGen !== this.fetchGeneration) {
          return null;
        }

        if (response && response.tokens && response.tokens.length > 0) {
          this.buffer.loadInitial(response, this.chunkSize);
          this.index = Math.min(
            this.buffer.getLocalIndex(absoluteIndex),
            Math.max(0, this.buffer.length() - 1)
          );
          if (this.state !== 'done') {
            this.showCurrentWord();
          }
        }
        return response;
      } catch (err) {
        console.error('Failed to refetch chunk on WPM change:', err);
        return null;
      } finally {
        if (fetchGen === this.fetchGeneration) {
          this.buffer.isPrefetching = false;
          this.inFlightPrefetchPromise = null;
        }
      }
    })();

    return await this.inFlightPrefetchPromise;
  }

  setFontFamily(family) {
    this.renderer.setFontFamily(family);
    if (this.state === 'paused' || this.state === 'idle') {
      this.showCurrentWord();
    }
  }

  setFontSize(size) {
    this.renderer.setFontSize(size);
    if (this.state === 'paused' || this.state === 'idle') {
      this.showCurrentWord();
    }
  }

  invalidateRendererCache() {
    this.renderer.invalidateCache();
  }

  seek(absoluteIndex) {
    const localIndex = this.buffer.getLocalIndex(absoluteIndex);
    if (localIndex >= 0 && localIndex < this.buffer.length()) {
      this.index = localIndex;
      this.showCurrentWord();
    }
  }
}
