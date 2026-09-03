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
| **M5 exhaustion & RVOL** (E) | built — block exhaustion + EM, RVOL multiplies (D-044/045) |
| **M7 context & regime** (C) | built — evidence fills C, regime gates it (D-047) |
| Composite / gate / grading | built — **D-039 fixed a 0.600 ceiling** caused by four stubs sitting in the denominator; re-measuring |

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
grades start appearing. §5 below is expected to shrink sharply next round.

---

## 3. FIRST-CLASS — the engine has no third category overnight on NQ

**This is the most consequential finding of the D-054…D-058 sequence, and it is a
structural fact rather than a defect to be tuned.**

Measured (D-058): NQ's internals print on **2809 of 10014 bars, 28.0%**, and
essentially all of it is the cash session. So category **C is unavailable outside
RTH**.

Why that is load-bearing rather than a limitation to note in passing:

- D-019 requires **Location + at least one of {Liquidity, Order-flow} + ≥ minCats
  distinct categories**. Overnight the reachable set is L, E, Q.
- **E is anti-correlated with Q by construction** — M6 fires on the *reclaim*,
  when price is returning to the middle, while E modules need price *away* from
  it. Measured: **88% of L+Q bars have no E module active.**
- C was built specifically to escape that. **The escape does not exist overnight.**
- M6 fires overnight at a substantial rate, so this is not a small slice of the
  problem. Those are exactly the setups the engine currently cannot grade.

Earlier readings did not show this because the overnight gap was being filled with
held-forward prints, and those inflated C (D-058). The problem was always there;
the instrument was hiding it.

### Three real answers. We do not have the data to choose.

| Option | What it claims | What it would cost |
|---|---|---|
| **M3 as a second Location module** | Volume-profile levels (naked POC, VAH/VAL, poor highs) give L a second, independent source, so L+Q+profile reaches three categories overnight | Does **not** actually add a category — D-046: a second module in a category cannot move a category count. It would need M3 assigned to a *different* category, or D-019 relaxed. That is a spec change, not a module build |
| **M4 as the F path** | Approximated delta/CVD fills Order-flow, which is in the {Q,F} clause *and* counts as a distinct category, so L+Q+F reaches three without C | Depends on intrabar data quality at the plan tier; D-012 already says M4 is **re-specified, not re-tuned** if real footprint data ever arrives |
| **Accept it** | The engine is a cash-session tool on NQ; overnight NQ is out of scope, and GC carries the overnight book | Honest and cheap, but it discards a large share of NQ's M6 fires and makes the instrument asymmetric between the two products in a way the original spec did not intend |

**The M3 option has a trap worth stating now**, because it is the intuitive choice
and D-046 already refutes the naive form of it: adding a second Location module
does not add a third category. Anyone reaching for M3 here must first say which
category it fills and why.

Nothing is being built against this until `00 zGTlive` is confirmed at 0 and GC has
been re-read.

---

## 4. Open — blocked on modules that do not exist yet

| Item | What it is | Waiting on |
|---|---|---|
| **D-028** M1/M6 collinearity, within-E split | M1 correlates with M6 at swept extremes; M5's ADR exhaustion plausibly does not. Damp the correlated term rather than restricting D-019's third category. | **Half unblocked.** `CLS_TYP` exists (D-034) and **M1 now ships with the barrier-sweep check wired and inert** (`m1ExtremeDamp` = 1.0), with distance and damping logged separately. Waiting only on **M5** — then the four D-028 measurements run with no further registry or module change. |
| **D-027 sub-question** fixed vs age-dependent swept-level damping | Age-dependent is more principled but flattens the composite across M6 age, destroying fresh-vs-stale discrimination. | the D-026 age histogram — which needs grades to occur, which needs a third category |
| **M5 split** into separate Exhaustion and RVOL modules | two distinct claims sharing one weight | M5 built |
| **Naked POC decay** | how long an unfilled POC stays relevant | M3 built |
| **D-020 category precedence** | M2 over M3 for Location, M1 over M5 for Extension — defensible, untested | M3 and M5 built |

---

## 5. Open — measurable as soon as grades appear

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

## 6. Open — conventions and deferred defects

| Item | Status | Note |
|---|---|---|
| **D-007** GC RTH = COMEX pit window | **Provisional** | A convention choice. Exposed as an input. Would change for a trader framing the day around the London fix or the 18:00 Globex open. |
| **Round-number relocation** (D-034 note) | deferred | `ceil(close/step)*step` relocates when price crosses a step boundary — the D-032 swing defect again. Off by default; needs fixed anchoring, not just a type, if ever enabled. |
| **D-013 settling test** | unrun | Build the session profile from chart symbol and full-size and compare POC/VAH/VAL placement. Only matters when charting MNQ/MGC; irrelevant while charting NQ/GC directly. |
| **M4 re-specification trigger** | conditional | If the plan tier ever provides real footprint data, M4 is **re-specified, not re-tuned** (D-012). |
| **D-055/058** context staleness | **CONFIRMED and fixed** | `request.security` hold-forward means M7 may be scoring a stale RTH print as live overnight evidence. NQ: RAW 10014/10014, LIVE 2809, Z up to 5495. Z now computed over live samples only. All prior M7 readings withdrawn. |
| **M7 regime gate ~72% of NQ bars** | unmeasured | State 2 dominates M7 far more than missing data does. `ctxSeparate` / `adxTrend` are placeholders. Not touched while the availability measurement is running. |
| **GC context liveness** | **unmeasured, blocking** | `TVC:DXY` / `US10Y` / `US02Y` have not been checked for the same session-bound behaviour. Not assumed either way. GC's C column is suspect until the Data Window readout comes back from a GC run. |
| **`ctxZreset`** (D-060) | **deliberately undecided**, off | Bounded decaying contamination vs an unconditional per-session cost. An argument, not a measurement; queues behind uncontaminated grades. |
| **D-059** consensus divisor | **open, now with data** | Corrected by D-061: both instruments ran a divisor of 4, not 3 vs 4. Prospectively GC is 3 and NQ 4, but GC's three slots are live 94/86/79%, so neither divisor is stable. Four options recorded, none taken. |
| **D-061** GC slot 4 self-reference | **fixed; GC C values withdrawn** | `request.security("")` resolves to the chart symbol, so gold's own price was a wrong-signed fourth vote in gold's own context. GC's C availability stands; its C scores do not. |
| **`USI:VOLD` flat periods** | observed, not acted on | 744 live NQ bars produced no z because the last 24 live samples were identical. A live source with no usable z on ~25% of its live bars. |
| **Category C is RTH-only on NQ** | **structural, not fixable** | Internals print on 28.0% of bars. The escape from the E∩Q anti-correlation does not exist outside the cash session. |
| **L-fill by level class** | not built | Would test the round-number-density hypothesis for the NQ/GC L gap (D-054). Not built pre-emptively. |

---

## 7. Closed since the last reconciliation

| Item | Outcome |
|---|---|
| **D-030** intact test | one-bar → 30-minute lookback. GC 50.2 → 21.5 fires/session (−57%) |
| **D-032** swing pivots | removed from M6's sweepable set. Were 35% of penetrations and 40% of fires from 2 of 12 classes. Definitional mismatch — a pivot passes any intact test by construction |
| **D-031** re-arm gate | built; **`LEAK 0`**, mean margin 2.4× threshold / 31 bars of 9. Gate is tight; thresholds left alone |
| **D-033** repeat-counter diagnosis | 48% repeat share is the *intended* double-top population, not a failure. The counter and the gate govern different populations |
| **D-034** barrier vs reference | **BARRIER 3.64 vs REFERENCE 2.35** f/100 exposure-bars. Raw fires/session ordering was inverted by exposure. `sweepUseReference` stays ON |
| **D-051/053** `catFillMin` | set to 0.15 on measurement. On GC it cut C's fill 3879 → 1653 while L moved 178 → 178 |
| **D-054** `structProx` units | 8 ticks → 0.010 × daily ATR. Also settled the *direction*: the window was looser on **GC**, so normalising widens the NQ/GC L gap rather than closing it |
| **NQ internals availability** | `USI:TICK/ADD/VOLD/TRIN` **do resolve**. The standing "structurally weaker context path" conditional does not fire; no macro substitute is warranted |

---

## 8. Standing constraints — not open items

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
