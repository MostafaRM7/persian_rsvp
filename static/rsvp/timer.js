/**
 * RSVP Playback Timer Abstraction.
 * 
 * Manages the high-frequency playback loop with drift compensation.
 * Guarantees a single active timer, preventing parallel execution or cumulative timing drift.
 */

export class PlaybackTimer {
  constructor() {
    this.timerId = null;
    this.expectedTickTime = null;
  }

  schedule(callback, delayMs) {
    // Only cancel a pending timer — do NOT clear() here, because clear()
    // resets expectedTickTime and would destroy the drift anchor every tick.
    if (this.timerId !== null) {
      clearTimeout(this.timerId);
      this.timerId = null;
    }
    const now = performance.now();

    if (this.expectedTickTime === null) {
      this.expectedTickTime = now + delayMs;
    } else {
      this.expectedTickTime += delayMs;
    }

    // Drift compensation: if the event loop lagged, deduct the drift
    const drift = now - (this.expectedTickTime - delayMs);
    const effectiveDelay = Math.max(0, delayMs - Math.max(0, drift));

    this.timerId = setTimeout(() => {
      this.timerId = null;
      callback();
    }, effectiveDelay);
  }

  resetAnchor() {
    this.expectedTickTime = null;
  }

  clear() {
    if (this.timerId !== null) {
      clearTimeout(this.timerId);
      this.timerId = null;
    }
    // Stopping playback invalidates the anchor; the next schedule() re-anchors.
    this.expectedTickTime = null;
  }

  isActive() {
    return this.timerId !== null;
  }

  calculateDelay(wpm, durationWeight = 100) {
    const baseMs = 60000 / Math.max(1, wpm);
    const factor = (durationWeight || 100) / 100;
    return baseMs * factor;
  }
}
