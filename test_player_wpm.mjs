import assert from 'node:assert/strict';
import { RSVPPlayer } from './static/rsvp/player.js';

// Minimal DOM mocks for Node.js
class MockElement {
  constructor() {
    this.textContent = '';
    this.classList = { add: () => {}, remove: () => {} };
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
  matchMedia: () => ({ matches: true, addEventListener: () => {}, addListener: () => {} }),
};

globalThis.document = {
  fonts: { ready: Promise.resolve(), addEventListener: () => {} },
  createRange: () => ({
    setStart: () => {},
    setEnd: () => {},
    getBoundingClientRect: () => ({ left: 140, right: 160, top: 50, bottom: 90, width: 20, height: 40 }),
  }),
};

// Mock fetch to simulate backend RSVP engine chunk responses with WPM-derived pacing
let fetchCalls = [];
let fetchDelayMs = 0;

globalThis.fetch = async (url, options) => {
  const payload = JSON.parse(options.body);
  fetchCalls.push({ url, payload });

  if (fetchDelayMs > 0) {
    await new Promise((res) => setTimeout(res, fetchDelayMs));
  }

  const chunkSize = payload.chunk_size || 100;
  const chunkIndex = payload.chunk_index || 0;
  const wpm = payload.wpm || 300;
  const totalChunks = 3;
  const totalTokens = chunkSize * totalChunks;

  // Generate tokens where terminal token has WPM-derived d value:
  // 300 WPM -> d=200; 900 WPM -> d=230
  const tokens = Array.from({ length: chunkSize }, (_, i) => {
    const globalIdx = chunkIndex * chunkSize + i;
    const isTerminal = (globalIdx + 1) % 10 === 0;
    return {
      w: isTerminal ? `کلمه${globalIdx}.` : `کلمه${globalIdx}`,
      orp: 1,
      d: isTerminal ? (wpm >= 600 ? 230 : 200) : 100,
    };
  });

  return {
    ok: true,
    status: 200,
    json: async () => ({
      engine_version: '2026.04.1',
      chunk_index: chunkIndex,
      total_chunks: totalChunks,
      total_tokens: totalTokens,
      has_more: chunkIndex < totalChunks - 1,
      tokens,
    }),
  };
};

function createTestPlayer(options = {}) {
  const wordEl = new MockElement();
  const focusEl = new MockElement();
  return new RSVPPlayer({
    wordElement: wordEl,
    focusElement: focusEl,
    chunkSize: 100,
    prefetchThreshold: 30,
    ...options,
  });
}

async function runTests() {
  console.log('Running RSVPPlayer WPM refetch tests...');

  // 1. WPM change before loadPlan (no buffer) -> just update this.wpm, no refetch
  {
    fetchCalls = [];
    const player = createTestPlayer();
    assert.equal(player.wpm, 300);
    await player.setWpm(500);
    assert.equal(player.wpm, 500);
    assert.equal(fetchCalls.length, 0, 'Must not refetch when no buffer is loaded');
  }

  // 2. WPM change with buffered tokens -> buffer refreshed with new WPM pacing, index preserved
  {
    fetchCalls = [];
    const player = createTestPlayer();
    player.wpm = 300;
    await player.loadPlan('متن آزمایشی برای تندخوانی');
    assert.equal(fetchCalls.length, 1);
    assert.equal(player.buffer.length(), 100);

    // Initial playhead position
    player.index = 25;
    player.showCurrentWord();

    // Verify initial terminal token pacing at 300 WPM
    const initialTerminal = player.buffer.get(9); // 10th token
    assert.equal(initialTerminal.d, 200);

    // Change WPM to 900
    await player.setWpm(900);
    assert.equal(player.wpm, 900);
    assert.equal(fetchCalls.length, 2, 'Should have refetched current chunk');
    assert.equal(fetchCalls[1].payload.wpm, 900);

    // Verify playhead index is preserved
    assert.equal(player.index, 25);
    assert.equal(player.buffer.getAbsoluteIndex(player.index), 25);

    // Verify buffer was refreshed: terminal token now reflects 900 WPM pacing (d = 230)
    const refreshedTerminal = player.buffer.get(9);
    assert.equal(refreshedTerminal.d, 230, 'Terminal token must have updated d=230 for 900 WPM');
  }

  // 3. WPM change near chunk boundaries (boundary discipline)
  {
    fetchCalls = [];
    const player = createTestPlayer();
    await player.loadPlan('متن آزمایشی');
    // Load chunk 1 into buffer as well
    await player.fetchNextChunk();
    assert.equal(player.buffer.length(), 200);

    // Test near end of chunk 0: index 99
    player.index = 99;
    await player.setWpm(700);
    assert.equal(player.buffer.getAbsoluteIndex(player.index), 99);
    assert.equal(fetchCalls[fetchCalls.length - 1].payload.chunk_index, 0);

    // Re-fetch chunk 1 to have multi-chunk buffer again
    await player.fetchNextChunk();

    // Test at start of chunk 1: absolute index 100
    player.index = 100; // local index 100, which is token 100
    await player.setWpm(850);
    // After refetching chunk 1, baseTokenOffset is 100, localIndex is 0, absolute is 100
    assert.equal(player.buffer.getAbsoluteIndex(player.index), 100);
    assert.equal(fetchCalls[fetchCalls.length - 1].payload.chunk_index, 1);
  }

  // 4. In-flight prefetch deduplication: mid-prefetch WPM change must discard stale prefetch and prevent duplicate appends
  {
    fetchCalls = [];
    const player = createTestPlayer();
    await player.loadPlan('متن آزمایشی');
    assert.equal(player.buffer.length(), 100);

    // Trigger prefetch with simulated network latency
    fetchDelayMs = 50;
    const prefetchPromise = player.fetchNextChunk();

    // While prefetch is in flight, user changes WPM
    fetchDelayMs = 10;
    const wpmPromise = player.setWpm(900);

    await Promise.all([prefetchPromise, wpmPromise]);
    fetchDelayMs = 0;

    // Verify buffer integrity:
    // Stale prefetch for chunk 1 (wpm 300) must have been discarded and not appended
    // Buffer must contain chunk 0 with wpm 900
    assert.equal(player.wpm, 900);
    assert.equal(player.buffer.length(), 100, 'Buffer must not contain duplicate or stale appended chunks');
    assert.equal(player.buffer.get(9).d, 230, 'Buffer must contain the new 900 WPM tokens');
  }

  // 5. Rapid consecutive WPM changes (300 -> 600 -> 900)
  {
    fetchCalls = [];
    const player = createTestPlayer();
    await player.loadPlan('متن آزمایشی');

    fetchDelayMs = 20;
    const p1 = player.setWpm(600);
    const p2 = player.setWpm(900);
    await Promise.all([p1, p2]);
    fetchDelayMs = 0;

    assert.equal(player.wpm, 900);
    assert.equal(player.buffer.get(9).d, 230);
  }

  // 6. Edge cases: idle, paused, done, buffering
  {
    const player = createTestPlayer();
    await player.loadPlan('متن آزمایشی');

    // Idle
    player.setState('idle');
    await player.setWpm(400);
    assert.equal(player.state, 'idle');
    assert.equal(player.wpm, 400);

    // Paused
    player.setState('paused');
    await player.setWpm(500);
    assert.equal(player.state, 'paused');
    assert.equal(player.wpm, 500);

    // Buffering
    player.setState('buffering');
    await player.setWpm(600);
    assert.equal(player.state, 'buffering');
    assert.equal(player.wpm, 600);

    // Done
    player.finish();
    assert.equal(player.state, 'done');
    const callsBefore = fetchCalls.length;
    await player.setWpm(700);
    assert.equal(player.state, 'done');
    assert.equal(player.wpm, 700);
    assert.equal(fetchCalls.length, callsBefore, 'Must not refetch when playback is finished');
    assert.equal(player.renderer.wordEl.textContent, 'پایان');
  }

  // 7. P3-15: restart after done reloads a fresh plan (not a stale last-chunk replay)
  {
    let lastProgress = null;
    const player = createTestPlayer({ onProgress: (p) => { lastProgress = p; } });
    await player.loadPlan('متن آزمایشی');
    player.setState('running');
    player.index = 50;
    await player.fetchNextChunk(); // buffer now holds chunks 0+1
    player.finish();
    assert.equal(player.state, 'done');

    fetchCalls = [];
    await player.start();
    assert.equal(fetchCalls.length, 1, 'done-state start must reload the plan from the server');
    assert.equal(fetchCalls[0].payload.chunk_index, 0, 'restart must fetch chunk 0');
    assert.equal(lastProgress.index, 0, 'restart must render the first token of a fresh plan');
    assert.equal(player.buffer.length(), 100, 'buffer must hold exactly the fresh first chunk');
    assert.equal(player.state, 'running');
    player.pause(); // stop the live timer chain so the test process can exit
  }

  // 8. P3-16: setWpm during loading discards the stale-wpm initial fetch
  {
    fetchCalls = [];
    const player = createTestPlayer();
    fetchDelayMs = 50;
    const loadPromise = player.loadPlan('متن آزمایشی');
    await new Promise((res) => setTimeout(res, 10)); // let the load dispatch
    assert.equal(player.state, 'loading');

    await player.setWpm(900);
    assert.equal(player.wpm, 900);
    await loadPromise;
    fetchDelayMs = 0;

    assert.equal(player.buffer.length(), 0, 'stale-wpm initial fetch must be discarded, not installed');
    assert.equal(player.state, 'idle', 'superseded load must restore idle, not stay loading');
  }

  console.log('All RSVPPlayer WPM refetch unit tests passed successfully!');
}

runTests();
