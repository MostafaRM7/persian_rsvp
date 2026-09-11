import assert from 'node:assert/strict';
import { WordRenderer } from './static/rsvp/renderer.js';

// Mock minimal DOM environment for Node.js testing
class MockElement {
  constructor() {
    this.textContent = '';
    this.classList = {
      add: () => {},
      remove: () => {},
    };
    this.style = {};
    this.firstChild = { textContent: '' };
  }
  getBoundingClientRect() {
    return { left: 100, right: 300, top: 50, bottom: 90, width: 200, height: 40 };
  }
}

globalThis.window = {
  innerWidth: 1024,
  devicePixelRatio: 2,
  addEventListener: () => {},
  getComputedStyle: (el) => ({
    fontFamily: el.style.fontFamily || 'Vazirmatn',
    fontSize: el.style.fontSize || '48px',
    fontWeight: '400',
  }),
  matchMedia: () => ({
    matches: true,
    addEventListener: () => {},
    addListener: () => {},
  }),
};

globalThis.document = {
  fonts: {
    ready: Promise.resolve(),
    addEventListener: () => {},
  },
  createRange: () => ({
    setStart: () => {},
    setEnd: () => {},
    getBoundingClientRect: () => ({
      left: 140,
      right: 160,
      top: 50,
      bottom: 90,
      width: 20,
      height: 40,
    }),
  }),
};

const wordEl = new MockElement();
const focusEl = new MockElement();
const renderer = new WordRenderer(wordEl, focusEl);

// 1. Initial font key
const key1 = renderer.getFontKey();
assert.equal(key1, 'Vazirmatn::48px::400');

// 2. Render token & check cache insertion
renderer.render({ w: 'تندخوانی', orp: 3 });
assert.equal(renderer.metricsCache.size, 1);
const cacheKey1 = `${key1}:تندخوانی:3`;
const cached1 = renderer.metricsCache.get(cacheKey1);
assert.ok(cached1, 'Cache entry should exist for rendered token');
assert.equal(cached1.relLeft, 40); // 140 - 100
assert.equal(cached1.relRight, 60); // 160 - 100
// Check focal centering calculation:
// focusRect.left = 100, focusRect.width = 200 => center = 200
// char.left = 140, char.right = 160 => charCenter = 150
// dx = 200 - 150 = 50
assert.equal(cached1.dx, 50);

// 3. Render from cache works cleanly
renderer.render({ w: 'تندخوانی', orp: 3 });
assert.equal(renderer.metricsCache.size, 1);

// 4. Dynamic font size change invalidates metrics cache
renderer.setFontSize(64);
assert.equal(renderer.metricsCache.size, 0, 'Cache must be invalidated on font size change');
const key2 = renderer.getFontKey();
assert.equal(key2, 'Vazirmatn::64px::400');

// 5. Dynamic font family change invalidates metrics cache
renderer.render({ w: 'تندخوانی', orp: 3 });
assert.equal(renderer.metricsCache.size, 1);
renderer.setFontFamily('Tahoma');
assert.equal(renderer.metricsCache.size, 0, 'Cache must be invalidated on font family change');
const key3 = renderer.getFontKey();
assert.equal(key3, 'Tahoma::64px::400');

// 6. Automatic font change detection in render() without explicit setFont
renderer.render({ w: 'کتاب', orp: 1 });
assert.equal(renderer.metricsCache.size, 1);
// Simulate CSS stylesheet or class change modifying computed font on wordEl
wordEl.style.fontSize = '32px';
renderer.render({ w: 'کتاب', orp: 1 });
// The change in computed font detected at render() start clears the cache and re-caches with the new font key
const key4 = renderer.getFontKey();
assert.equal(key4, 'Tahoma::32px::400');
assert.ok(renderer.metricsCache.has(`${key4}:کتاب:1`));

// 7. Viewport resize and DPI / zoom change invalidates cache
renderer.invalidateCache();
assert.equal(renderer.metricsCache.size, 0);
assert.equal(renderer.focusRect, null);

// 8. Zero-width Range rect fallback
// When range returns a 0-width rect (e.g. collapsed or unrendered glyph), fallback to proportional width
const origCreateRange = globalThis.document.createRange;
globalThis.document.createRange = () => ({
  setStart: () => {},
  setEnd: () => {},
  getBoundingClientRect: () => ({ left: 140, right: 140, width: 0, height: 40 }),
});
renderer.render({ w: 'کتاب', orp: 1 });
const fallbackCached = renderer.metricsCache.get(`${key4}:کتاب:1`);
assert.ok(fallbackCached);
// Avg width for 4 chars with wordRect width 200 is 50px
assert.ok(fallbackCached.relRight > fallbackCached.relLeft, 'Fallback must produce non-zero width highlight');
globalThis.document.createRange = origCreateRange;

// 9. Clear and message handling
renderer.setMessage('پایان');
assert.equal(wordEl.textContent, 'پایان');
assert.equal(wordEl.style.transform, 'none');
renderer.clear();
assert.equal(wordEl.textContent, '');

console.log('All client WordRenderer unit tests passed successfully!');
