# RSVP Engine — Development & Execution Plan

## Purpose

This document is the execution roadmap for developing the commercial Persian RSVP engine incrementally.

The project must become usable early, while the proprietary RSVP intelligence is introduced progressively in isolated phases.

The core architectural principle is:

> **Backend = intelligence and proprietary algorithms.  
> Client = high-performance rendering and playback.**

The browser/extension must never depend on network timing for individual words.

---

# 1. Global Architecture

```text
                         Browser / Extension
                                  │
                                  │ HTTPS
                                  ▼
                         ┌──────────────────┐
                         │     FastAPI      │
                         │                  │
                         │ Auth / Quota     │
                         │ RSVP API         │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    RSVP Engine   │
                         │                  │
                         │ Normalize        │
                         │ Tokenize         │
                         │ Difficulty       │
                         │ Pacing           │
                         │ Semantics        │
                         │ ORP              │
                         │ Chunking         │
                         └────────┬─────────┘
                                  │
                         token / playback chunks
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   Client Player  │
                         │                  │
                         │ Buffer           │
                         │ Timer            │
                         │ Rendering        │
                         │ ORP pixels       │
                         │ Controls         │
                         └──────────────────┘

                    ┌─────────────────────────┐
                    │       PostgreSQL        │
                    │ users / plans / usage   │
                    └─────────────────────────┘

                    ┌─────────────────────────┐
                    │          Redis          │
                    │ cache / rate limits     │
                    └─────────────────────────┘
```

## 1.1 Backend responsibilities

The backend owns the proprietary decision-making:

- text normalization
- Persian tokenization
- half-space handling
- linguistic analysis
- difficulty analysis
- frequency/corpus logic
- semantic grouping
- pause decisions
- cognitive pacing
- ORP decisions
- future ML/AI-based pacing
- generation of playback/token chunks

## 1.2 Client responsibilities

The client owns device-specific playback:

- rendering
- font measurement
- physical pixel alignment
- ORP positioning in the actual viewport
- local playback timing
- animation
- keyboard/mouse/touch controls
- buffering
- prefetching
- pause/resume/seek UI

The client must not contain the proprietary RSVP decision engine.

---

# 2. Development Rules

## Rule 1 — Always keep the product runnable

Every phase must leave the application in a working state.

Do not spend multiple phases building infrastructure without a usable RSVP path.

## Rule 2 — One engine capability per phase

Do not implement the complete intelligent RSVP engine in the first phase.

Each major intelligence capability should be introduced independently so that:

- behavior is measurable
- regressions are easy to isolate
- the engine remains understandable
- rollback is easy
- commercial value can be added progressively

## Rule 3 — Backend owns intelligence

When a requirement involves making a **decision** about how text should be read, prefer the backend.

When a requirement involves **displaying** an already-made decision on a real device, keep it client-side.

## Rule 4 — No per-word network dependency

Never implement:

```text
word → API → response → display → API → next word
```

Instead use:

```text
API → chunk → local buffer → local playback
```

## Rule 5 — Do not leak unnecessary engine internals

Avoid exposing unless strictly required:

- raw difficulty scores
- internal feature vectors
- frequency scores
- model outputs
- internal rule identifiers
- proprietary intermediate calculations
- source-level algorithm decisions

The API should expose the minimum representation required by the player.

## Rule 6 — Avoid premature infrastructure

Do not introduce microservices, Kafka, complex streaming infrastructure, or distributed processing unless the current phase has a concrete requirement for them.

The default MVP architecture is a modular FastAPI application with a well-isolated RSVP Engine.

---

# 3. Phase 0 — Foundation & Architectural Boundary

## Goal

Create a clean architectural boundary between the RSVP Engine, API layer, and client Player before adding intelligence.

## Scope

### Backend

- Create/confirm `rsvp_engine` module/package.
- Define the Engine input contract.
- Define internal token representation.
- Define public token/chunk output contract.
- Keep API handlers thin.
- Make engine logic independently testable.

### Client

- Isolate RSVP Player from page/UI logic.
- Create a buffer abstraction.
- Create a playback loop abstraction.
- Create rendering abstraction.
- Create API client abstraction.

## Suggested conceptual structure

```text
backend/
  app/
    api/
      rsvp.py
    rsvp_engine/
      engine.py
      models.py
      normalization.py
      tokenizer.py
      pacing.py
      orp.py
      chunking.py

frontend/
  rsvp/
    player.ts
    buffer.ts
    timer.ts
    renderer.ts
    api.ts
    types.ts
```

The exact paths may follow the existing repository conventions. Do not restructure unrelated parts of the project.

## Output

A minimal end-to-end RSVP flow exists through the new architecture.

## Acceptance Criteria

- Browser can request text processing.
- Backend returns a chunked token representation.
- Client can buffer and play the result.
- No request is made per word.
- Player can continue locally after receiving a chunk.
- Engine can be tested without running the browser.

---

# 4. Phase 1 — Basic RSVP Engine

## Goal

Bring up a commercially usable but intentionally simple RSVP engine.

This phase should prioritize correctness and smooth playback over linguistic intelligence.

## Backend

Implement:

- basic normalization
- basic whitespace-aware tokenization
- punctuation awareness
- simple word classes
- base playback plan
- chunk generation

The base algorithm should support configurable WPM.

Example conceptual settings:

```json
{
  "wpm": 600
}
```

## Client

Implement:

- stable word rendering
- ORP-aware rendering framework
- local timer
- pause/resume
- restart
- WPM control
- buffered playback
- next-chunk prefetch

## Acceptance Criteria

- Smooth playback at 300, 600, and 1000 WPM.
- No network request occurs for individual words.
- Temporary network latency does not directly affect playback of buffered content.
- Player recovers after a successful prefetch retry.
- Basic punctuation is readable and stable.

---

# 5. Phase 2 — Persian Normalization & Tokenization

## Goal

Move Persian-specific text handling into the backend and establish a reliable linguistic token stream.

## Backend

Implement and test:

- Arabic/Persian character normalization
- Unicode normalization
- whitespace normalization
- Persian punctuation normalization
- ZWNJ / half-space handling
- Persian number handling
- punctuation attachment
- quotation handling
- common edge cases
- URL/email handling where applicable

Examples that must be treated correctly:

```text
می‌خواهم
کتاب‌خانه
آن‌ها
رفته‌ام.
```

## Important

The client must not duplicate these rules.

## Acceptance Criteria

- Same input always produces deterministic tokenization.
- Half-space cases are stable.
- Punctuation does not create unexpected playback artifacts.
- Tokenization tests cover representative Persian text.

---

# 6. Phase 3 — ORP & Device-Aware Rendering

## Goal

Make the visual focus point robust while keeping device-specific measurements on the client.

## Backend

Backend provides the logical ORP decision or minimal ORP metadata.

## Client

Client calculates the actual pixel placement using:

- current font
- actual rendered width
- browser measurement APIs
- viewport dimensions
- zoom/DPI behavior

## Design rule

Backend must not attempt to predict physical pixel dimensions.

## Acceptance Criteria

- ORP remains visually stable across supported browsers.
- Changing font family/size does not break alignment.
- Long Persian words remain centered around the intended focus point.
- No measurable playback stutter is introduced by ORP rendering.

---

# 7. Phase 4 — Basic Cognitive Pacing

## Goal

Introduce the first real proprietary RSVP intelligence while preserving the same client contract.

## Backend

Implement a first pacing layer that can distinguish at minimum between:

- normal words
- punctuation
- sentence endings
- naturally longer reading units

The engine should derive a playback plan from WPM rather than exposing the implementation itself.

## Contract principle

Do not make the public API mirror internal engine variables.

Prefer abstractions such as:

```json
{
  "word": "...",
  "orp": 3,
  "pace": 2
}
```

over exposing a large set of internal calculations.

## Acceptance Criteria

- Basic pacing is perceptibly better than uniform timing.
- Punctuation produces sensible pauses.
- WPM remains user-configurable.
- Client does not need to understand the pacing algorithm.
- Existing API contract remains backward-compatible or versioned.

---

# 8. Phase 5 — Persian Difficulty & Frequency Intelligence

## Goal

Add Persian-language intelligence for varying reading difficulty.

## Backend

Implement:

- word difficulty scoring
- frequency/corpus lookup or model — also converts open-class affix heuristics (P3-8: the `ها` suffix join, currently a documented trade-off) into a whitelist backed by corpus data
- length/complexity signals — requires P3-6 (Persian decimal separator `٫` / decimal-comma handling) to be resolved first, so number tokens are stable features
- linguistic complexity signals
- handling of rare vs common words
- combining multiple signals into pacing decisions

The internal representation may be richer than the public API.

For example, internally:

```text
difficulty = 0.83
frequency = 0.14
complexity = 0.71
```

But these exact values should not automatically be exposed to the client.

## Acceptance Criteria

- Difficult/rare Persian words receive different treatment from common words.
- Behavior is deterministic for the same engine version/settings.
- Engine unit tests cover common, rare, long, compound, and morphological cases.
- Internal scores are not required by the client.

---

# 9. Phase 6 — Semantic Chunking & Intelligent Pauses

## Goal

Move beyond word-level timing and introduce sentence/phrase-level reading rhythm.

## Entry criteria (P3 gate)

- **P3-3 must be resolved in the first commit of Phase 6, before boundary detection is built.** Current state: the floating-punctuation rule in `normalize_text` can swallow a newline following punctuation, and the `\n` entry in `STRONG_PUNCTUATION` is a dead signal. Phase 6's sentence-boundary detection needs newline boundaries as real input.

## Backend

Implement:

- sentence boundary detection
- phrase/semantic group detection
- clause boundary detection where practical
- context-sensitive pause decisions
- punctuation + semantic pause combination

Example conceptual output:

```text
[phrase]
اگرچه هوا بسیار سرد بود،

[pause]

[phrase]
اما او تصمیم گرفت ادامه دهد.
```

The final representation must remain optimized for client playback.

## Acceptance Criteria

- Pauses feel natural around sentence/phrase boundaries.
- Long sentences do not behave like flat word streams.
- Semantic logic remains entirely server-side.
- Client only consumes the resulting playback instructions.

---

# 10. Phase 7 — Advanced Adaptive Pacing

## Goal

Combine the previous engine components into a stronger proprietary pacing system.

## Backend

Combine signals such as:

- WPM
- word difficulty
- frequency
- word length
- morphology
- punctuation
- semantic boundaries
- sentence position
- surrounding context

The architecture must allow additional signals to be introduced without changing the browser architecture.

## Recommended internal concept

```text
Text
 ↓
Normalization
 ↓
Tokenization
 ↓
Linguistic analysis
 ↓
Feature extraction
 ↓
Difficulty / frequency
 ↓
Semantic analysis
 ↓
Pacing engine
 ↓
Playback plan
 ↓
Chunker
 ↓
Client
```

## Acceptance Criteria

- Adding a new engine signal does not require a client update.
- Engine behavior is measurable and testable.
- Playback remains smooth at high WPM.
- Performance remains acceptable for normal user-sized inputs.

---

# 11. Phase 8 — Personalization

## Goal

Make pacing adaptive to individual users.

## Potential inputs

- preferred WPM
- historical reading behavior
- preferred pause intensity
- difficulty tolerance
- reading mode
- user-selected profile

## Backend

Personalization should modify engine configuration rather than duplicate the engine in the client.

Conceptually:

```text
User Profile
     ↓
Engine Configuration
     ↓
RSVP Engine
     ↓
Playback Plan
```

## Acceptance Criteria

- Personalization can be enabled/disabled.
- Default behavior remains unchanged for new users.
- User profile is server-controlled.
- Extension updates are not required for new pacing preferences.

---

# 12. Phase 9 — Commercialization & Abuse Protection

## Goal

Turn the processing API into a commercially enforceable service.

## Backend

Implement:

- authenticated RSVP sessions
- subscription checks
- plan-based quotas
- rate limiting
- usage accounting
- short-lived access tokens where appropriate
- abuse monitoring
- session-level controls

The client must never be the authority for:

- subscription status
- quota
- feature entitlement
- API limits

## Important

Do not embed permanent API secrets in the extension/browser.

## Acceptance Criteria

- Free and paid users can be differentiated server-side.
- Usage can be measured.
- Processing endpoints cannot be used indefinitely without authorization.
- Limits are enforceable without trusting client code.

---

# 13. Phase 10 — Performance, Scale & Engine Optimization

## Goal

Optimize the complete system after the product and engine are functionally mature.

## Focus areas

### Backend

- profiling
- tokenization performance
- engine performance
- caching opportunities
- concurrent request handling
- memory usage
- chunk generation latency

### Client

- rendering performance
- timer stability
- buffer strategy
- memory usage
- extension overhead
- large-text handling

### Infrastructure

Only introduce additional infrastructure when measurements justify it.

Potential future additions may include:

- background processing
- dedicated workers
- specialized caches
- streaming transports
- horizontal scaling
- model-serving infrastructure

Do not add these preemptively.

## Acceptance Criteria

- Performance bottlenecks are measured rather than guessed.
- High-WPM playback remains stable.
- Backend can scale horizontally without changing engine semantics.
- Caching does not compromise correctness or user isolation.

---

# 14. API Contract Principles

The API is a boundary between the proprietary Engine and the public Player.

## The API should expose

- authenticated session information
- engine version
- playback chunks
- minimal rendering metadata
- chunk sequencing information
- relevant player-safe settings

## The API should avoid exposing

- source-level rules
- internal feature vectors
- raw corpus scores
- internal ML features
- unnecessary intermediate classifications
- proprietary model details
- implementation-specific reasoning

## Versioning

The backend must be able to evolve engine behavior without requiring frequent extension releases.

Engine versions should be server-controlled.

Example:

```json
{
  "engine_version": "2026.01",
  "chunk_id": "abc123",
  "sequence": 4,
  "tokens": []
}
```

The exact protocol may evolve during implementation.

---

# 15. Chunking & Buffering Strategy

## Default direction

Use chunking + prefetching.

The client should maintain a playback buffer measured in time and/or tokens.

Conceptually:

```text
                       Playback
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ ███████████████████░░░░░░░░░░ │
        │       buffered ahead           │
        └─────────────────────────────────┘
                          ▲
                          │
                     prefetch
                          │
                      Backend
```

## Rules

- Never request every word separately.
- Prefetch before the buffer becomes low.
- Retry failed chunk fetches.
- Keep enough data to tolerate short network interruptions.
- Do not block playback while waiting for a non-critical request.

Initial chunk/buffer sizes should be determined empirically during implementation rather than permanently hard-coded in this document.

---

# 16. Transport Strategy

## Initial choice

Prefer normal HTTP/REST requests with chunking and prefetching for the MVP unless the current implementation already has a strong reason to use another transport.

## Possible future options

Evaluate only when needed:

- HTTP streaming
- Server-Sent Events
- WebSockets

The deciding factor should be measured product requirements, not preference.

---

# 17. Testing Strategy

Every Engine phase must add tests at the same time as the capability.

## Unit tests

Test individual engine components:

- normalization
- tokenization
- difficulty
- frequency
- semantic boundaries
- pacing
- ORP decisions

## Integration tests

Test:

```text
input text
 → engine
 → chunk generation
 → API
```

## Client tests

Test:

- buffering
- playback
- pause/resume
- WPM changes
- chunk transitions
- network retry behavior

## Regression principle

Every bug found in the Engine should produce a regression test before or alongside the fix.

---

# 18. Observability

The system should eventually record enough data to answer:

- How long does processing take?
- Which engine version was used?
- Which plan was used?
- How many words were processed?
- How often do chunk fetches fail?
- How often does the player run out of buffer?

Avoid logging raw user text unless there is an explicit privacy/business requirement and appropriate controls.

---

# 19. Engine Versioning

The RSVP Engine should be versionable independently from the client.

Conceptually:

```text
Client v1
    ↓
Engine v1

Client v1
    ↓
Engine v2
```

The client should consume a stable contract while backend intelligence evolves.

This is one of the key commercial advantages of keeping the Engine server-side.

---

# 20. MVP Definition

The MVP is complete when all of the following are true:

- End-to-end RSVP works.
- Browser/extension rendering is stable.
- Backend owns the initial Engine.
- Playback does not depend on per-word networking.
- Chunking and prefetching work.
- Persian normalization/tokenization are reliable enough for the initial product.
- Basic pacing exists.
- ORP rendering is robust.
- Authentication/usage enforcement can be introduced without redesigning the engine boundary.

Advanced linguistic intelligence is explicitly **not required** for MVP completion.

---

# 21. Definition of Done for Every Phase

A phase is complete only when:

1. The implementation is integrated into the existing project.
2. Existing functionality continues to work.
3. Tests cover the new behavior.
4. The client/server contract is documented where relevant.
5. No proprietary logic has accidentally moved into the client.
6. No unrelated refactor is included.
7. The application remains runnable.
8. The phase acceptance criteria are satisfied.
9. Any known limitations are documented.

After that, proceed to the next phase.

---

# 22. Agent Execution Rules

When working from this document:

## Always

- Inspect the existing implementation before changing it.
- Preserve working behavior.
- Reuse existing project conventions.
- Implement the smallest complete change for the current phase.
- Add tests with each capability.
- Keep the Engine/client boundary explicit.
- Prefer backward-compatible contracts.

## Never

- Rewrite the whole project unnecessarily.
- Move rendering to the backend.
- Introduce per-word network calls.
- Put proprietary pacing logic in browser JavaScript.
- Assume obfuscation makes client code secret.
- Introduce infrastructure without a demonstrated need.
- Implement future phases prematurely unless the current phase requires a compatible foundation.

---

# 23. Phase Tracking

Use this section as the execution state.

| Phase | Name | Status |
|---|---|---|
| 0 | Foundation & Architectural Boundary | DONE |
| 1 | Basic RSVP Engine | DONE |
| 2 | Persian Normalization & Tokenization | DONE |
| 3 | ORP & Device-Aware Rendering | DONE |
| 4 | Basic Cognitive Pacing | DONE |
| 5 | Persian Difficulty & Frequency Intelligence | DONE |
| 6 | Semantic Chunking & Intelligent Pauses | DONE |
| 7 | Advanced Adaptive Pacing | TODO |
| 8 | Personalization | TODO |
| 9 | Commercialization & Abuse Protection | TODO |
| 10 | Performance, Scale & Engine Optimization | TODO |

### Open P3 ledger (deferred findings — must not be silently dropped)

| ID | Finding | Scheduled for | Notes |
|---|---|---|---|
| P3-3 | Floating-punct rule can swallow newlines; `\n` pacing signal is dead | **Phase 6 (hard gate, first commit)** | **Resolved in Phase 6** (newlines preserved across normalization, token stream, and sentence boundary pacing with regression tests) |
| P3-6 | Persian decimal separator `٫` / decimal-comma unhandled | **Phase 5 (before difficulty features)** | **Resolved in Phase 5** (canonical `٫` and thousands comma, verified with regression tests) |
| P3-8 | `ها` plural suffix join is open-class | **Phase 5** | **Resolved in Phase 5** (converted to curated noun whitelist with negative regression tests) |
| P3-9 | Cosmetic intermediate space in normalized string | Ride-along: next changeset touching `normalization.py`/`tokenizer.py` | **Resolved in Phase 6** (horizontal whitespace regex in normalization eliminates cosmetic spaces, verified with regression tests) |
| P3-10 | `test_renderer.mjs` not wired into any automated test workflow (manual `node` only) | Ride-along: next changeset touching tests/README | Client regressions could pass pytest silently |
| P3-11 | Renderer global listeners (resize/fonts/DPR/ResizeObserver) lack `dispose()`; legacy `mq.addListener` leaks per DPR change | Phase 10 (client memory/perf) | Harmless for current single-page lifetime |
| P3-12 | `getComputedStyle` per `render()` call (~17/s at 1000 WPM) | Phase 10 (profiling-gated) | Negligible; measure before optimizing |
| P3-13 | `engine.py` duplicates pacing punctuation detection via string literal (drift risk vs `pacing.CLOSING_BRACKETS_QUOTES`) | Ride-along: next `engine.py` changeset | Refactor to shared constant |
| P3-14 | Documented Class 2/3 tier ranges overlap at 145 (actual outputs disjoint) | Ride-along: next `pacing.py` changeset | Doc/clamp nit only |
| P3-15 | Restart-after-done replays only the last chunk (`start()` sets `index=0` without clearing/reloading buffer), stale `d` if WPM changed post-finish | Ride-along: next `player.js` changeset | Fix: `loadPlan` on restart, not bare index reset |
| P3-16 | `setWpm` during `loading` skips generation bump; initial fetch installs stale-wpm buffer | Ride-along: same changeset as P3-15 | Sub-second window, self-heals on next chunk |
| P3-17 | Dotted technical identifiers (IP addresses like `192.168.1.1`) get decimal-separator conversion | Ride-along: next `normalization.py` changeset | Shield dotted-quads from decimal rule |
| P3-18 | `AFFIX_STRIP_REGEX` allows over-aggressive 1-letter suffix stripping (`م`/`ی`); needs minimum-stem guard | ~~Ride-along~~ **Closed in Phase 5 fix cycle** (min-stem guard ≥3 implemented in `frequency.py`; verified by reviewer probes: شام/غم/زمین/بهاریم stay rare) | |
| P3-19 | Frequency lexicon coverage small (~300 entries); everyday words (`گوش`, `سینما`, `خانواده`, `شنبه`, …) unlisted → rare-dwell | Phase 7 (pacing rework) | Partial patch landed with Phase 5 fix (495 entries) |
| P3-20 | Punctuation sets now duplicated in 3 modules (`pacing.py`, `semantics.py`, `engine.py` literal — P3-13 pattern spreading) | Ride-along: next `engine.py`/`semantics.py` changeset | Consolidate into one shared constants module; fold in P3-13 |
| P3-21 | `FINITE_PREDICATE_VERBS` in `semantics.py` defined but never referenced (dead code) | Ride-along: same changeset as P3-20 | |
| P3-22 | Phase 4 dialogue test widened to `in (165, 170)` without pinning the cause — the 170 path is semantic bonus (15) stacking on the quote-introducer bonus (+5); behavior is correct but the assertion no longer documents which value occurs when | Ride-along: next pacing-test changeset | Pin exact values or document bonus stacking in a comment |

Rule: a deferred finding is only closed by a code change plus regression test, or by explicit removal from this ledger with a one-line justification.

### Review workflow (fixed convention)

1. Every review classifies findings P1/P2/P3 against the current phase's acceptance criteria.
2. Findings belonging to the current phase are fixed before the tracker moves; a phase is only DONE after re-review confirms the fixes.
3. Findings that do **not** belong to the current phase are recorded in the Open P3 ledger above with a scheduled phase (or "ride-along") — never left in chat only.
4. After current-phase fixes are verified, the reviewer supplies the prompt for starting the next phase. Implementers never set the tracker to DONE themselves.
5. Every review ends with a passable **findings-fix prompt**: a self-contained prompt embedding the current findings (file references, exact issues, required fix approach, scope limits, test requirements) that the user hands to the implementer agent for the fix cycle.
6. Reviewer briefings are standardized — every review (initial and fix-verification) is run from this skeleton, with the phase-specific items filled in:
   ```text
   1. Role: reviewer only — report findings, never edit code.
   2. Scope: current phase's acceptance criteria (§<N>) + boundaries (contract, ledger, version rules).
   3. Evidence: verify every claim on disk; run pytest + client tests + syntax checks;
      run independent adversarial probes — implementer output is not evidence.
   4. Classify: P1 (correctness/architecture, blocking) / P2 (must fix before DONE) /
      P3 (out of scope → Open P3 ledger with schedule).
   5. Closure: on confirmed pass, reviewer updates tracker and supplies next-phase start prompt.
   ```

Recommended status values:

```text
TODO
IN_PROGRESS
BLOCKED
DONE
``` 

---

# 24. Final Architectural Principle

The system should evolve like this:

```text
                    MVP
                     │
                     ▼
             Basic RSVP Engine
                     │
                     ▼
        Persian Tokenization / NLP
                     │
                     ▼
             Better Pacing
                     │
                     ▼
          Difficulty / Frequency
                     │
                     ▼
        Semantic Reading Intelligence
                     │
                     ▼
            Adaptive Personalization
                     │
                     ▼
          Commercial Optimization
```

The important constraint across every phase is:

> **The browser should become a better player, not a smarter copy of the engine.**

The proprietary intelligence should continuously become more valuable on the backend while the public client contract stays as small, stable, and implementation-agnostic as possible.
