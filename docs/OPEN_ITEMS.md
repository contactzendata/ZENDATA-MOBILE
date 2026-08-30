# Open Items — status reconciliation

As of 2026-08-29, after L0/M2/M6/M1. The D-035 blind review is deferred (see §1).
Full reasoning for every `D-nnn` lives in `DECISIONS.md`; this is the index.

---

## Build state

| Component | State |
|---|---|
| **L0 level registry** | built — 12 live classes, 0 `request.*` calls |
| **M2 structural levels** (L) | built — proximity and stacking scored separately |
| **M6 sweep & reclaim** (Q) | built — ~10 fires/session GC 5m, gate verified leak-free |
| **M1 VWAP extension** (E) | built — session-BLOCK anchored, directional band-walk (D-038) |
| M8 overnight prior (bias) | **stub** |
| M3 volume/market profile (L) | **stub** |
| M4 delta/CVD (F) | **stub** |
| M5 exhaustion & RVOL (E) | **stub** |
| M7 context & regime (C) | **stub** |
| Composite / gate / grading | built — gate opened 17x on GC 5m but **max composite 0.432 < 0.45 floor**; re-measuring after D-038 |

`request.*` budget: **2 call sites**, both wrapped. 1 live (M6 daily ATR, only when
selected). Compile risk from `ta.pivothigh` with a computed length: **cleared**.

---

## 1. DEFERRED — the blind review (D-035)

**Not run. Deferred, not cancelled.** `REVIEW_PROTOCOL.md` stays in place.

**Reason, recorded honestly:** insufficient discretionary screen time on GC/NQ for
the marks to be a meaningful baseline, and the working definition that would have
been used was close enough to M6's own logic that agreement would have been
**circular**. A pass run under those conditions produces a number that looks like
validation and is not one. Declining to generate it is the correct call — a
circular agreement figure would then be cited in every later decision as though it
meant something.

### What the deferral costs — carried forward, not resolved

**M6's definition is now unvalidated, and the remaining modules are being built on
top of it anyway.** Specifically:

| Unknown | Why it stays unknown |
|---|---|
| Does M6 fire on events a reader would mark? | only the review answers this |
| **What M6 misses entirely** | the *yours-only* bucket. **No counter in this script can detect it** — a missed event leaves no trace anywhere, because detecting it requires the judgement the engine approximates |
| Does M6 ever read the right location with the wrong side? | *matched–oppose* is invisible to every diagnostic; it would score as a match |
| Is the registry missing structure? | the `LVL` tag was the only instrument for this |

Every number produced so far — fire rate, funnel, per-class breakdown, exposure
normalization, leak assertion, age-at-grade — measures whether M6 does what it
says. **None measure whether what it says is worth saying.** That gap is now a
standing risk on everything built above M6, and it does not shrink as more modules
land; it compounds, because each new module inherits M6's category-Q gate keeping
(D-019).

**Revisit when either:** more discretionary time on these instruments, **or** the
engine is grading and can be watched live — at which point the marks come from
watching the engine be wrong in real time rather than from a cold chart, which is a
different and in some ways better baseline.

**Module order consequence:** the next module could not be chosen by miss-tag
distribution, so it was chosen on its own merits instead. See §2.

---

## 2. Module order — M1 chosen on merit, not on review findings

With the review deferred, M1 was selected for reasons independent of it:

1. It fills **category E**, so the gate (Location + event + third category) becomes
   satisfiable and **something can grade for the first time**.
2. VWAP sigma bands are the **best-evidenced extension tool** in the source
   research — practitioner-supported where most single indicators are folklore
   (see the evidence ledger in `SPEC.md` §4).
3. It is **mechanical rather than judgement-dependent**, so its correctness can be
   checked without the discretionary baseline the review would have supplied.

Point 3 is the one that matters given the deferral: M1 is a module whose
implementation can be verified even though the engine's *output* cannot yet be.

**Immediate consequence:** the composite parameters — thresholds, weights,
`catDamp`, `minCats` composition, M8's cap — stop being unmeasurable the moment
grades start appearing. §4 below is expected to shrink sharply next round.

---

## 3. Open — blocked on modules that do not exist yet

| Item | What it is | Waiting on |
|---|---|---|
| **D-028** M1/M6 collinearity, within-E split | M1 correlates with M6 at swept extremes; M5's ADR exhaustion plausibly does not. Damp the correlated term rather than restricting D-019's third category. | **Half unblocked.** `CLS_TYP` exists (D-034) and **M1 now ships with the barrier-sweep check wired and inert** (`m1ExtremeDamp` = 1.0), with distance and damping logged separately. Waiting only on **M5** — then the four D-028 measurements run with no further registry or module change. |
| **D-027 sub-question** fixed vs age-dependent swept-level damping | Age-dependent is more principled but flattens the composite across M6 age, destroying fresh-vs-stale discrimination. | the D-026 age histogram — which needs grades to occur, which needs a third category |
| **M5 split** into separate Exhaustion and RVOL modules | two distinct claims sharing one weight | M5 built |
| **Naked POC decay** | how long an unfilled POC stays relevant | M3 built |
| **D-020 category precedence** | M2 over M3 for Location, M1 over M5 for Extension — defensible, untested | M3 and M5 built |

---

## 4. Open — measurable as soon as grades appear

**This section unblocks with M1.** The gate can now be satisfied by L + Q + E, so
these stop being unmeasurable — expect the next round to be about thresholds and
weights rather than module logic.

- **Grade thresholds** 0.75 / 0.60 / 0.45 — placeholders, no empirical basis
- **Module weights** — 1.0 across, except M4 and M7 at 0.5
- **`catDamp` 0.5** (D-020) — arbitrary
- **`minCats` composition** (D-019) — whether *which* three categories matters more
  than *how many*
- **M8 cap 0.05 and decay 150m** (D-021) — both guesses
- **D-026 `gradesNoM6`** — must read zero while `requireOF` is off and M4 is a stub;
  non-zero means something unexpected is filling category Q

---

## 5. Open — conventions and deferred defects

| Item | Status | Note |
|---|---|---|
| **D-007** GC RTH = COMEX pit window | **Provisional** | A convention choice. Exposed as an input. Would change for a trader framing the day around the London fix or the 18:00 Globex open. |
| **Round-number relocation** (D-034 note) | deferred | `ceil(close/step)*step` relocates when price crosses a step boundary — the D-032 swing defect again. Off by default; needs fixed anchoring, not just a type, if ever enabled. |
| **D-013 settling test** | unrun | Build the session profile from chart symbol and full-size and compare POC/VAH/VAL placement. Only matters when charting MNQ/MGC; irrelevant while charting NQ/GC directly. |
| **M4 re-specification trigger** | conditional | If the plan tier ever provides real footprint data, M4 is **re-specified, not re-tuned** (D-012). |

---

## 6. Closed since the last reconciliation

| Item | Outcome |
|---|---|
| **D-030** intact test | one-bar → 30-minute lookback. GC 50.2 → 21.5 fires/session (−57%) |
| **D-032** swing pivots | removed from M6's sweepable set. Were 35% of penetrations and 40% of fires from 2 of 12 classes. Definitional mismatch — a pivot passes any intact test by construction |
| **D-031** re-arm gate | built; **`LEAK 0`**, mean margin 2.4× threshold / 31 bars of 9. Gate is tight; thresholds left alone |
| **D-033** repeat-counter diagnosis | 48% repeat share is the *intended* double-top population, not a failure. The counter and the gate govern different populations |
| **D-034** barrier vs reference | **BARRIER 3.64 vs REFERENCE 2.35** f/100 exposure-bars. Raw fires/session ordering was inverted by exposure. `sweepUseReference` stays ON |

---

## 7. Standing constraints — not open items

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
