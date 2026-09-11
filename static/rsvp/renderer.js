/**
 * RSVP Word Renderer Abstraction (Phase 3 — ORP & Device-Aware Rendering).
 * 
 * Responsible for device-specific presentation:
 * - Single text node rendering (preserves Persian cursive shaping & ZWNJ)
 * - Subpixel Range API measurement of the focal ORP character
 * - Dynamic translateX centering of the ORP character directly over the focal tick
 * - Seamless single-character gradient styling via background-clip: text
 * - Device-aware layout tracking: font family, font size, web font loading, zoom/DPI changes
 * - Fast layout-thrashing prevention via bounded metrics caching
 */

export class WordRenderer {
  constructor(wordEl, focusEl) {
    this.wordEl = wordEl;
    this.focusEl = focusEl;
    this.focusRect = null;
    this.currentFontKey = '';
    this.metricsCache = new Map(); // Key: `${fontKey}:${word}:${orp}` -> { dx, relLeft, relRight }
    this.maxCacheSize = 500;

    if (typeof window !== 'undefined') {
      // 1. Invalidate cached dimensions when viewport resizes
      window.addEventListener('resize', () => this.invalidateCache());

      // 2. Invalidate on Zoom / DPI (devicePixelRatio) resolution changes
      this._setupDprListener();

      // 3. Invalidate when web fonts finish loading asynchronously
      if (typeof document !== 'undefined' && document.fonts) {
        document.fonts.ready.then(() => this.invalidateCache()).catch(() => {});
        if (document.fonts.addEventListener) {
          document.fonts.addEventListener('loadingdone', () => this.invalidateCache());
        }
      }

      // 4. ResizeObserver on focusEl for responsive or style-driven size changes
      if (typeof ResizeObserver !== 'undefined' && this.focusEl) {
        this.resizeObserver = new ResizeObserver(() => this.invalidateCache());
        this.resizeObserver.observe(this.focusEl);
      }
    }
  }

  _setupDprListener() {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const dpr = window.devicePixelRatio || 1;
    const mq = window.matchMedia(`(resolution: ${dpr}dppx)`);
    const handler = () => {
      this.invalidateCache();
      this._setupDprListener();
    };
    if (mq.addEventListener) {
      mq.addEventListener('change', handler, { once: true });
    } else if (mq.addListener) {
      mq.addListener(handler);
    }
  }

  getFontKey() {
    if (!this.wordEl || typeof window === 'undefined' || !window.getComputedStyle) return 'default';
    const style = window.getComputedStyle(this.wordEl);
    return `${style.fontFamily || ''}::${style.fontSize || ''}::${style.fontWeight || ''}`;
  }

  setFontFamily(family) {
    if (this.focusEl) {
      this.focusEl.style.fontFamily = family;
    }
    if (this.wordEl) {
      this.wordEl.style.fontFamily = family;
    }
    this.invalidateCache();
  }

  setFontSize(size) {
    const sizeStr = typeof size === 'number' ? `${size}px` : size;
    if (this.focusEl) {
      this.focusEl.style.fontSize = sizeStr;
    }
    if (this.wordEl) {
      this.wordEl.style.fontSize = sizeStr;
    }
    this.invalidateCache();
  }

  invalidateCache() {
    this.focusRect = null;
    this.metricsCache.clear();
  }

  getFocusRect() {
    if (!this.focusRect && this.focusEl) {
      this.focusRect = this.focusEl.getBoundingClientRect();
    }
    return this.focusRect;
  }

  render(token) {
    if (!token || !this.wordEl) return;

    // Detect dynamic font family or size changes without requiring explicit event triggers
    const fontKey = this.getFontKey();
    if (this.currentFontKey && this.currentFontKey !== fontKey) {
      this.invalidateCache();
    }
    this.currentFontKey = fontKey;

    const word = token.w;
    this.wordEl.textContent = word;
    this.wordEl.classList.add('orped');

    const cacheKey = `${fontKey}:${word}:${token.orp}`;
    const cached = this.metricsCache.get(cacheKey);

    if (cached) {
      this.wordEl.style.transform = `translateX(${cached.dx}px)`;
      this.wordEl.style.backgroundImage =
        `linear-gradient(90deg, var(--text) 0 ${cached.relLeft}px, var(--orp) ${cached.relLeft}px ${cached.relRight}px, var(--text) ${cached.relRight}px 100%)`;
      return;
    }

    this.wordEl.style.transform = 'none';

    const chars = Array.from(word);
    const orpIndex = Math.min(Math.max(0, token.orp), chars.length - 1);
    const unitStart = chars.slice(0, orpIndex).join('').length;
    const unitLen = chars[orpIndex] ? chars[orpIndex].length : 1;

    const wordRect = this.wordEl.getBoundingClientRect();
    const focusRect = this.getFocusRect() || { left: 0, width: (typeof window !== 'undefined' ? window.innerWidth : 800) || 800 };

    let cLeft = null;
    let cRight = null;

    try {
      const range = document.createRange();
      range.setStart(this.wordEl.firstChild, unitStart);
      range.setEnd(this.wordEl.firstChild, unitStart + unitLen);
      const rect = range.getBoundingClientRect();
      if (rect && isFinite(rect.left) && isFinite(rect.right) && rect.width > 0) {
        cLeft = rect.left;
        cRight = rect.right;
      }
    } catch (err) {
      // Fallback
    }

    if (cLeft === null) {
      const avgWidth = wordRect.width / Math.max(1, chars.length);
      cLeft = wordRect.left + orpIndex * avgWidth;
      cRight = cLeft + avgWidth;
    }

    // Align ORP focal center with the page focal tick
    const dx = Number(((focusRect.left + focusRect.width / 2) - (cLeft + cRight) / 2).toFixed(1));
    const relLeft = Number((cLeft - wordRect.left).toFixed(1));
    const relRight = Number((cRight - wordRect.left).toFixed(1));

    // Store in cache
    if (this.metricsCache.size >= this.maxCacheSize) {
      const firstKey = this.metricsCache.keys().next().value;
      this.metricsCache.delete(firstKey);
    }
    this.metricsCache.set(cacheKey, { dx, relLeft, relRight });

    this.wordEl.style.transform = `translateX(${dx}px)`;
    this.wordEl.style.backgroundImage =
      `linear-gradient(90deg, var(--text) 0 ${relLeft}px, var(--orp) ${relLeft}px ${relRight}px, var(--text) ${relRight}px 100%)`;
  }

  clear() {
    if (!this.wordEl) return;
    this.wordEl.classList.remove('orped');
    this.wordEl.style.backgroundImage = 'none';
    this.wordEl.style.transform = 'none';
    this.wordEl.textContent = '';
  }

  setMessage(msg) {
    this.clear();
    if (this.wordEl) {
      this.wordEl.textContent = msg;
    }
  }
}
