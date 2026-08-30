# Open Items — status reconciliation

As of 2026-08-29, after M6/M2/L0 and before the D-035 blind review.
Full reasoning for every `D-nnn` lives in `DECISIONS.md`; this is the index.

---

## Build state

| Component | State |
|---|---|
| **L0 level registry** | built — 12 live classes, 0 `request.*` calls |
| **M2 structural levels** (L) | built — proximity and stacking scored separately |
| **M6 sweep & reclaim** (Q) | built — ~10 fires/session GC 5m, gate verified leak-free |
| **M8 overnight prior** (bias) | stub |
| M1 VWAP extension (E) | **stub** |
| M3 volume/market profile (L) | **stub** |
| M4 delta/CVD (F) | **stub** |
| M5 exhaustion & RVOL (E) | **stub** |
| M7 context & regime (C) | **stub** |
| Composite / gate / grading | built — nothing can grade yet (gate needs a third category) |

`request.*` budget: **2 call sites**, both wrapped. 1 live (M6 daily ATR, only when
selected). Compile risk from `ta.pivothigh` with a computed length: **cleared**.

---

## 1. Blocked on the blind review (D-035)

Nothing gets built until these come back. See `REVIEW_PROTOCOL.md`.

| Item | Waiting on | Unblocks |
|---|---|---|
| **Is M6 measuring anything worth measuring** | recall on H-conviction marks; opposite-read rate; `DEF` tag count | everything — a bad result rebuilds M6 and discards work layered on it |
| **Which module is built next** | miss-tag distribution over the yours-only bucket | M1 / M3 / M5 order; `SPEC.md`'s planned order is not binding |
| **Whether L0 is missing structure** | `LVL` tag count | registry extension rather than a new module |

---

## 2. Open — blocked on modules that do not exist yet

| Item | What it is | Waiting on |
|---|---|---|
| **D-028** M1/M6 collinearity, within-E split | M1 correlates with M6 at swept extremes; M5's ADR exhaustion plausibly does not. Damp the correlated term rather than restricting D-019's third category. | **Structurally unblocked — `CLS_TYP` now exists (D-034).** Still needs M1 and M5 built with per-term sub-score logging, then the four measurements listed in D-028. |
| **D-027 sub-question** fixed vs age-dependent swept-level damping | Age-dependent is more principled but flattens the composite across M6 age, destroying fresh-vs-stale discrimination. | the D-026 age histogram — which needs grades to occur, which needs a third category |
| **M5 split** into separate Exhaustion and RVOL modules | two distinct claims sharing one weight | M5 built |
| **Naked POC decay** | how long an unfilled POC stays relevant | M3 built |
| **D-020 category precedence** | M2 over M3 for Location, M1 over M5 for Extension — defensible, untested | M3 and M5 built |

---

## 3. Open — blocked on any grade occurring at all

No setup can currently grade: the gate requires Location **and** an event **and** a
third category, and every E/F/C module is a stub. Everything here is unmeasurable
until that changes.

- **Grade thresholds** 0.75 / 0.60 / 0.45 — placeholders, no empirical basis
- **Module weights** — 1.0 across, except M4 and M7 at 0.5
- **`catDamp` 0.5** (D-020) — arbitrary
- **`minCats` composition** (D-019) — whether *which* three categories matters more
  than *how many*
- **M8 cap 0.05 and decay 150m** (D-021) — both guesses
- **D-026 `gradesNoM6`** — must read zero while `requireOF` is off and M4 is a stub;
  non-zero means something unexpected is filling category Q

---

## 4. Open — conventions and deferred defects

| Item | Status | Note |
|---|---|---|
| **D-007** GC RTH = COMEX pit window | **Provisional** | A convention choice. Exposed as an input. Would change for a trader framing the day around the London fix or the 18:00 Globex open. |
| **Round-number relocation** (D-034 note) | deferred | `ceil(close/step)*step` relocates when price crosses a step boundary — the D-032 swing defect again. Off by default; needs fixed anchoring, not just a type, if ever enabled. |
| **D-013 settling test** | unrun | Build the session profile from chart symbol and full-size and compare POC/VAH/VAL placement. Only matters when charting MNQ/MGC; irrelevant while charting NQ/GC directly. |
| **M4 re-specification trigger** | conditional | If the plan tier ever provides real footprint data, M4 is **re-specified, not re-tuned** (D-012). |

---

## 5. Closed since the last reconciliation

| Item | Outcome |
|---|---|
| **D-030** intact test | one-bar → 30-minute lookback. GC 50.2 → 21.5 fires/session (−57%) |
| **D-032** swing pivots | removed from M6's sweepable set. Were 35% of penetrations and 40% of fires from 2 of 12 classes. Definitional mismatch — a pivot passes any intact test by construction |
| **D-031** re-arm gate | built; **`LEAK 0`**, mean margin 2.4× threshold / 31 bars of 9. Gate is tight; thresholds left alone |
| **D-033** repeat-counter diagnosis | 48% repeat share is the *intended* double-top population, not a failure. The counter and the gate govern different populations |
| **D-034** barrier vs reference | **BARRIER 3.64 vs REFERENCE 2.35** f/100 exposure-bars. Raw fires/session ordering was inverted by exposure. `sweepUseReference` stays ON |

---

## 6. Standing constraints — not open items

These are properties of the platform, recorded so they are not periodically
rediscovered as problems. Full detail in `PINE_LIMITS.md`.

- No Level 2, DOM, bid/ask trade classification, or market-by-order. **Category F
  cannot be built** — M4 is a tick-rule proxy and the engine is a screener, not a
  trigger (D-012).
- No options data. GEX and gamma regime are manual inputs; no proxy is invented.
- No economic calendar. Catalyst stand-down is a manual toggle.
- ~100k intrabar cap forces M3's hybrid sourcing (D-001).
- 500 boxes / lines / labels, shared across the whole script.
- ~40 `request.*` calls.
