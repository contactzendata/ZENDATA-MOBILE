# Reversal Engine — Technical Specification

**Target:** TradingView Pine Script v6, single indicator, `overlay = true`
**Instruments:** NQ (E-mini Nasdaq-100, CME) · GC (Gold, COMEX) — micros MNQ/MGC as aliases
**Chart timeframes:** 1m, 5m, 15m
**Status:** Scaffold complete, spec complete. No module logic implemented.

> Educational/research only. Counter-trend trading has a structurally low win rate
> and asymmetric blow-up risk. Every threshold below is an untested hypothesis.

---

## 1. What this engine is

The source research converges on one framework: **a statistically extended
location that coincides with order-flow evidence of a failed auction.** Location
tells you *where*; order flow tells you *when*; neither works alone. Operationally
it becomes a five-category checklist requiring **≥3 aligned categories**:

| | Category | Evidence |
|---|---|---|
| **L** | Location | VWAP ±2σ, VAH/VAL, naked POC, PDH/PDL/ONH/ONL, GEX wall, expected-move boundary |
| **E** | Extension | ADR/ATR exhausted, ≥2σ from VWAP, z-score/Bollinger extreme |
| **F** | Order-flow failure | Absorption, exhaustion, stacked imbalance, unfinished auction, CVD divergence |
| **Q** | Liquidity event | Stop-run/sweep of the level that immediately reverses (trapped traders) |
| **C** | Context | Internals (NQ) or macro (GC); COT/GEX regime |

### 1.1 The load-bearing constraint

**Pine can build L, E, Q and C. It cannot build F.** There is no Level 2, no DOM,
no bid/ask trade classification, no market-by-order — so absorption, stacked
imbalance, unfinished auctions and trapped-trader reads are all out of reach at
any effort level. The only F-category input available is M4's **tick-rule
approximation** of delta, which the source research independently flags as a
frequent *"real divergence, no reversal"* trap.

This is not a gap to engineer around. It is the shape of the tool:

> **This engine is a screener, not a trigger.** It marks zones where Location,
> Extension, Liquidity and Context align, and hands off order-flow confirmation to
> a footprint/DOM platform. A grade published here is the *first four* checklist
> categories, not all five.

That framing matches the source recommendation directly — a two-layer setup with
profile/VWAP/levels on one layer and footprint/DOM confirmation on another. This
engine is layer one. Treating a grade as an entry signal skips the category the
research calls load-bearing (D-012).

**Out of scope** (record here if it changes): position sizing, stops, targets,
dollar risk, trade management, execution. This is an `indicator`, not a `strategy`.

---

## 2. Architecture

```
  instrument detect ──┐
  timeframe normalize ├─→  M1 VWAP extension        [E]
  session resolve ────┘    M2 Structural levels     [L]   each module →
                           M3 Volume/Market profile [L]   { score 0..1,
                           M4 Delta / CVD (APPROX)  [F]     active bool,
                           M5 Exhaustion & RVOL     [E]     dir ±1/0 }
                           M6 Sweep & reclaim       [Q]
                           M7 Context & regime      [C]
                                    │
                     within-category damping (2nd+ module × 0.5)
                                    │
                    evaluate LONG side and SHORT side separately
                                    │
              gate: Location AND (Liquidity OR Order-flow) AND ≥3 categories
                                    │
                    both sides qualify → CONFLICT → suppress
                                    │
             M8 overnight prior: bounded ± bias on the resolved side (≤0.05)
                                    │
                        A / B / C threshold mapping
                                    │
                  hostile context caps the grade (default B)
                                    │
                            published grade + side
```

### 2.1 Module contract

| Field | Type | Meaning |
|---|---|---|
| `score` | float | Normalized **0..1**. Meaningful only when `active`. |
| `active` | bool | This module has something to say about *this* bar. |
| `dir` | int | `+1` supports a **long** reversal (fading a low) · `-1` supports a **short** reversal (fading a high) · `0` non-directional |
| `note` | string | Human-readable reason, for the eventual detail pane. |

Four rules, all load-bearing:

1. **Normalize honestly.** 0 = no support, 1 = the strongest form of this evidence
   the module can express. Saturation points are inputs, not magic numbers.
2. **Missing data → `active = false`.** Never a neutral 0.5. The composite cannot
   distinguish a real 0.5 from a fabricated one (D-011).
3. **`dir` must be honest.** `dir = 0` contributes to *both* sides and is how a
   module double-counts unnoticed. Most reversal evidence has a side.
4. **Modules compute; RENDER draws.** No exceptions (D-010).

### 2.2 Composite

```
module OFF                      → excluded from numerator and denominator
module ON, idle                 → contributes 0.0, effective weight stays
module ON, active, WRONG side   → contributes 0.0, effective weight stays

effective weightᵢ = weightᵢ × factorᵢ
factorᵢ = 1.0 for the first ENABLED module in its category
        = catDamp (default 0.5) for the second and subsequent

composite(side) = Σ(scoreᵢ × ewᵢ) / Σ(ewᵢ)   over enabled modules, counting only
                                              modules whose dir agrees with `side`
                                              or is 0
```

Evidence for a low is not neutral when grading a high, so an opposing module costs
score rather than being excluded (D-015).

**Within-category damping (D-020).** The category gate stops collinear modules
from *unlocking* a grade; damping stops them from *inflating the score*. M2 and M3
are both Location — a POC sitting at prior-day high is largely one observation, and
under flat weighting it paid out twice. Damping applies to **both numerator and
denominator**: numerator-only damping would let a second agreeing module *lower*
the composite, and confirming evidence must never reduce a grade.

Precedence is **declared push order, not score** — M1 primary Extension (M5
secondary), M2 primary Location (M3 secondary) — so the denominator stays stable
and an idle module's weight stays well-defined. F, Q and C have one member each,
so damping is inert there today.

### 2.3 Confluence gate: composition, not just count

The gate counts **distinct categories** — M2 and M3 firing together are *one*
category, not two confirmations (D-014) — and additionally **enforces composition**
(D-019). A grade requires all three of:

1. **Location present** — mandatory, no exceptions.
2. **At least one of {Liquidity, Order-flow}** — something must have *happened*.
3. **Total distinct categories ≥ `minCats`** — configurable, default 3.

Composition is not optional; only the count is. A bare count of three treats all
category triples as equivalent, and they are not: `{Location, Extension, Context}`
satisfies a count while describing a market merely *extended near a level in a
supportive regime* — which fits every band-walk on every trend day. No event has
occurred. That is a watch, not a setup.

Location is where the thesis lives; rule 2 is the *failure* evidence — a sweep
that reversed (Q) or aggression that stopped working (F). Location plus an event
is the irreducible core; the third category is corroboration. Extension and
Context are therefore corroborating categories by construction and can never be
two of the three on their own.

`requireOF` narrows rule 2 from `{Q or F}` to `F` only. **Off by default**: in
Pine that would gate every setup on the weakest module in the engine.

> **Consequence worth planning around:** with `requireOF` off, **M6 carries rule 2
> alone in practice**, since M4 is the approximation. M6's quality gates the whole
> engine far more than its weight of 1.0 suggests — it should be among the first
> modules built and the most carefully tested.

### 2.4 Grading

A ≥ 0.75 · B ≥ 0.60 · C ≥ 0.45 · below → nothing. All inputs, all placeholders
with no evidence behind them yet. The raw composite is hidden behind a
development-only toggle: 0.71 and 0.69 are not different numbers when they come
from seven approximated sub-scores (D-009).

Hostile context caps the grade at B by default rather than vetoing, so the gate
stays auditable (D-004).

**Grades are comparable across bars for a fixed configuration, and not comparable
between configurations.** Any performance record must capture the toggle state.

### 2.5 Instrument profiles

| | NQ | MNQ | GC | MGC |
|---|---|---|---|---|
| Exchange | CME | CME | COMEX | COMEX |
| Multiplier | $20 × index | $2 × index | 100 oz | 10 oz |
| Tick | 0.25 = $5.00 | 0.25 = $0.50 | 0.10 = $10.00 | 0.10 = $1.00 |
| RTH | 09:30–16:00 ET | same | 08:20–13:30 ET (pit-equiv.) | same |
| Overnight | 18:00–09:30 ET | same | 18:00–08:20 ET | same |
| Settlement | cash | cash | physical | physical |
| Expiry | quarterly, 3rd Fri Mar/Jun/Sep/Dec | same | Feb/Apr/Jun/Aug/Oct/Dec | same |
| Roll | ~8 trading days pre-expiry | same | ~5–7 business days pre-FND | same |
| Context data | TICK / ADD / VOLD / TRIN / VIX / GEX | same | DXY / real yields / GVZ / COT | same |

Detection is substring matching on `syminfo.root`, micro tested first for display
naming only ("MNQ" contains "NQ"). Micros share the full-size profile exactly:
same price, same tick, same matching engine — only the multiplier differs, and
this indicator does not price risk in dollars (D-006). Tick size is read from
`syminfo.mintick`, never hardcoded, so a wrong family detection degrades session
times rather than tick arithmetic.

**Reversal-prone windows** (soft prior, never a trigger). NQ: open drive and its
failure 09:30–10:00, ~10:00, European close ~11:00–11:30, lunch 12:00–13:00,
14:00–15:00 into the close. GC: London open ~03:00, COMEX open 08:20, the
London–NY overlap ~08:00–11:00, and the London fixes.

**Continuous contracts.** Back-adjusted continuous series shift every historical
price at each roll, so absolute horizontal levels drawn on them are unreliable.
The engine detects a continuous ticker and flags it in the status table; levels
should be read on the live front month (D-017).

### 2.6 Timeframe normalization

No input is expressed in bars. Every duration is in **minutes**, converted by
`f_bars()`. Every price distance is in **ticks**. Together these make the engine
portable across 1m/5m/15m and across NQ/GC without a per-combination table (D-005).

Two things do not survive the conversion: M4's intrabar TF must be strictly lower
than the chart TF (so it self-disables on 1m charts), and the ~100k intrabar cap
forces M3's hybrid sourcing.

### 2.7 No-repaint guarantee

- All external data flows through `f_sec()` / `f_secLTF()` (D-008). `f_sec()`
  hardcodes `lookahead = barmerge.lookahead_off`. `request.security_lower_tf()`
  takes no `lookahead` argument and cannot look ahead by construction; its wrapper
  centralizes auditing and the `f_ltfValid()` guard.
- Publication is gated on `barstate.isconfirmed`.
- Developing-bar values (session range, live VWAP sigma, developing POC) update
  within the bar by design; modules using them must say so.
- Budget: ~15 of ~40 `request.*` calls worst case. Every addition needs a
  DECISIONS entry.

---

## 3. Modules

### M1 — VWAP extension  ·  category **E** (primary)
**Inputs:** anchor (RTH open default), RTH-only bands, σ extension start (2.0), σ
saturation (3.0), warm-up (30m), **band-walk suppression (20m)**, plot toggle.

**Method.** Session VWAP with running standard-deviation bands, RTH-anchored.
±1σ contains ~68% of session action, ±2σ ~95%, so a 2σ tag is a genuinely extended
location. Anchored VWAP from a major high/low or roll date gives a slower reference.

**Score mapping.** Linear interpolation of |extension in σ| from `vwapSigmaLo` to
`vwapSigmaHi`, saturating at 1.0. `dir = -1` above VWAP, `+1` below.

**Active condition.** False during warm-up (a fresh anchor has σ≈0, making the
reading meaningless) **and** false during a band-walk.

**Known weaknesses.** *Band-walking is the primary failure mode of this entire
style.* Mechanically fading a band in a trending session is, per the source
research, a leading cause of blow-ups. The band-walk guard — sustained closes
beyond the band flipping M1 from "extended" to "trending" — is the single most
important piece of logic in the module, not an optional refinement. Bands must be
RTH-anchored; overnight volume is too thin for reliable σ. σ is also
regime-dependent: 2σ in a compressed overnight is not 2σ on a trend day.

**Evidence class:** practitioner-supported, thinly peer-reviewed.

---

### M2 — Structural levels  ·  category **L** (primary)
**Inputs:** per-level toggles (PDH/PDL, PDC, ONH/ONL, IB, opening range, RTH open,
round numbers), IB length (60m), OR length (15m), proximity (8 ticks), draw
toggle; **manual GEX levels** (NQ only, off by default).

**Method.** Collect enabled levels, find the nearest within `structProx` ticks,
score by proximity **and** by how many *distinct level classes* stack at that price.

**Score mapping.** Proximity term × stacking term, both normalized. `dir = -1` at
resistance, `+1` at support.

**Known weaknesses.** Level *stacking* and level *importance* are different things;
scoring must not double-count them. For NQ the RTH open and the first-hour IB
dominate, and PDH/PDL sweeps are prime triggers — but that is M6's category (Q),
not M2's, and the two must not both claim credit for one event.

**GEX is manual and will go stale.** Pine has no options chain, no OI, no IV
surface, and no way to fetch any (PINE_LIMITS §4). GEX is also *modeled*, not
observed; OI updates end-of-day; and it is computed on NDX/QQQ then applied to
NQ/MNQ. Regime context, never a trigger. 0DTE concentrates enormous gamma into
the session — per Cboe's 2025 full-year report, SPX 0DTE hit a record 2.3M
contracts ADV, 59% of total SPX volume.

---

### M3 — Volume & Market profile  ·  category **L** (secondary, damped)
**Inputs:** rows (48), value area (70%), intrabar TF (1m), historical sessions
(10), naked POCs, HVN/LVN, TPO structures with 30m brackets, single prints, poor
highs/lows, 80% rule, draw toggle.

**Method.** Hybrid sourcing (D-001): current + prior session from intrabars, older
sessions from chart bars. Derive POC, VAH/VAL, HVN/LVN, naked POCs, and TPO
structures from 30-minute brackets.

**Reversal setups.** (a) Value-area edge fade — price extends beyond VAH/VAL, fails
to find acceptance, rotates back toward POC. (b) Naked/virgin POC as magnet and
reaction point. (c) HVN as reversal wall vs LVN as continuation zone. (d) The 80%
rule — open outside prior value, re-enter, hold two consecutive 30-min brackets
inside → ~80% tendency to traverse the full value area.

**TPO structures.** Single prints/excess tails mark genuine rejection and act as
magnets. Profile shapes: **D** = balance (fade extremes toward POC); **P** =
short-covering that often tops out; **b** = long-liquidation bottoming;
**double-distribution** = trend day, with the LVN between distributions as the
reversal pivot.

**Known weaknesses — three, all structural.**

1. **Poor highs/lows invert the signal.** A flat extreme across 2+ brackets with no
   excess tail is an *unfinished auction* that typically gets revisited **and
   exceeded**. It is a warning **against** fading, so M3 must score it *negatively*
   for the fade side. Getting this backwards turns the module into a
   trade-the-worst-setups generator (D-016).
2. **Resolution asymmetry.** Chart-bar-derived POCs from older sessions are less
   precise than the intrabar-derived current POC and must not score as tightly.
3. **Budget.** The largest consumer of the 500-box limit: 48 rows × 2 sessions =
   96 boxes before anything else draws.

Sessions matter more here than anywhere else. Gold's 23-hour Globex profile smears
Asia, London and NY into one uninformative distribution; the pit window and the
London–NY overlap carry the information. For NQ the cash session is the meaningful
profile.

**Evidence class:** practitioner-supported, thinly peer-reviewed.

---

### M4 — Delta / CVD  ·  category **F**  ·  ⚠ **APPROXIMATION**
**Inputs:** intrabar TF (1m), CVD reset (RTH open default), divergence lookback
(50m), **"only score divergence at a marked level"** (on by default).

**Method.** Tick rule on intrabar candles: intrabar close > open counts volume as
buying, close < open as selling, equal contributes zero. Cumulative sum = CVD.
Reversal read: price makes a new high while CVD makes a lower high (bearish), or a
new low while CVD makes a higher low (bullish).

**Active condition.** False unless `f_ltfValid(deltaTF)` — the intrabar TF must be
strictly lower than the chart TF. On a 1m chart that requires seconds data, which
is unreliable below the top plan tiers, and the module **self-disables rather than
reporting zeros**.

**Known weaknesses — this module is the weakest link by design.**
- It is not order flow. Real delta requires bid/ask trade classification, which
  Pine does not have (PINE_LIMITS §2). The tick rule's error rate rises sharply in
  fast, thin, one-tick-range conditions — exactly reversal conditions.
- The source research flags CVD divergence as a frequent **"real divergence, no
  reversal" trap**: liquidity at the high may simply have been consumed over
  repeated tests, and price breaks through anyway. Hence `deltaReqLvl` defaults on
  — divergence away from a pre-marked level is not evidence.
- Weighted 0.5 by default, and the category floor stops it carrying a grade alone.
- If a plan tier ever provides real footprint data, this module is
  **re-specified**, not re-tuned. The approximation and the real measurement are
  different things.

**Evidence class:** the underlying feature (order-flow imbalance) is the strongest
simple microstructure signal in the literature — Cont/Kukanov/Stoikov show a linear
OFI↔price relationship; Gould & Bonart find it predicts roughly the next two
mid-price changes then decays to near zero. But it is sub-transaction-cost for
round-trip speculation, spoofable, and *this module measures a proxy of it*.

---

### M5 — Exhaustion & RVOL  ·  category **E** (secondary, damped)
**Inputs:** ADR days (20), ADR exhaustion ratio (1.0), RVOL baseline (20 sessions),
RVOL threshold (1.5), time-of-day bucket (30m), climax multiple (2.0), expected
move with per-family IV symbol and rule-of-16 divisor (15.87).

**Method.**
- **ADR exhaustion:** session range ÷ average daily range. Continuation
  probability falls off around 1.0× the typical daily range.
- **RVOL:** current volume ÷ average volume *for the same time-of-day* over 10–20
  sessions. Time-of-day normalization is mandatory — futures volume is strongly
  U-shaped (heavy at the RTH open and close, thin midday), so a flat average
  makes every open look like a spike.
- **Climax volume:** ≥2× the 20-period average *at a level*.
- **Expected move:** daily EM ≈ Price × (IV/100) ÷ √252. VIX for NQ, GVZ for GC.
  A tag of the ±1 EM boundary is a statistically extended zone.

**Known weaknesses.**
- **A volume spike is ambiguous.** It marks exhaustion *or* breakout initiation.
  It becomes reversal evidence only when price **fails to follow through** — the
  failure, not the spike, is the signal.
- Exhaustion and RVOL are two distinct claims sharing one module and one weight.
  Whether they should be split is open (§5).
- GVZ is quoted on GLD options — a proxy for COMEX gold vol, not a measure of it.
- Holiday and half-day sessions distort both baselines.

---

### M6 — Sweep & reclaim  ·  category **Q**
**Inputs:** min penetration (4 ticks), max penetration (40 ticks), reclaim window
(10m), mark toggle.

**Method.** Price penetrates a tracked level by between `sweepMinTicks` and
`sweepMaxTicks` — beyond the max it is a breakout, not a sweep — then closes back
inside within `reclaimMin`. This is the stop-run-into-reversal pattern: clustered
stops at an obvious level (PDH/PDL, round number, prior swing) are triggered, and
the trapped traders' forced exits fuel the counter-move.

**Known weaknesses.**
- **Confirmation is structurally late.** The reclaim window cannot be evaluated
  until it elapses, so the module fires *after* the extreme, never at it. This is
  inherent to bar-by-bar execution with no lookahead, not a tuning problem.
- **Inter-module coupling.** M6 depends on M2/M3 for the levels it watches — the
  engine's one real dependency, and a collinearity risk the category floor exists
  to contain.
- Pine sees the *price behavior*, not the resting orders. M6 detects a failed
  penetration; it cannot know stops were there. Describe its output as "failed
  penetration", never "liquidity taken" (PINE_LIMITS §1).

---

### M7 — Context & regime  ·  category **C** + **grade cap**
**Inputs:** hostile cap (B), context TF (5m), NQ internals (TICK/ADD/VOLD/TRIN)
with ±1000 TICK extreme, GC macro (DXY/US10Y/US02Y), **manual gamma regime**,
regime method (ADX / range-vs-ADR / both) with ADX length 14 and threshold 25,
overnight-reversal prior, optional COT.

**Method.** Resolves an ordinary sub-score **and**, through an independent path, a
hostile flag (D-004). Deriving the cap from a sub-score threshold would collapse
them into one signal wearing two hats.

**NQ context.** NYSE TICK — normal range ±600, extremes beyond ±1000 mark breadth
exhaustion. *Context-dependent:* in range-bound sessions TICK extremes mark
reversal points; in trends they confirm momentum. ADD/VOLD divergence from price
(index new high, ADD fails to confirm) is a classic non-confirmation. TRIN >2.0 in
a decline = capitulation; <0.5 = frenzied buying that can fade.

**GC context.** Strong inverse correlation to DXY and 10-year *real* (TIPS)
yields — PIMCO's 2004–2025 regression puts gold's "real duration" at ~18 years
(100bp rise in 10y real yields ↔ ~18% decline in inflation-adjusted gold). **Post-2022
this anchor weakened**: record central-bank buying decoupled gold's level from real
yields, which held above 2% while gold rose. Real yields still transmit intraday
but no longer anchor the level — so this is a *filter*, not a model.

**Regime gate.** Fading in a trend is the dominant failure mode of the entire
style. ADX ≥25, or session range vs ADR, marks the session as trending and the
fade as hostile.

**Overnight → intraday reversal prior.** Close-to-open predicts open-to-close
negatively — documented across four asset classes including index futures (Della
Corte & Kosowski; Bondarenko & Muravyev; NY Fed), and strongest in the morning
session. Directional prior only.

**COT.** CFTC weekly, Tuesday data released Friday. For gold the signal is never
"commercials are net short" — they structurally are, as hedgers — it is how
stretched **managed money** is versus its own multi-year percentile. Top few
percent = crowded trade vulnerable to violent unwind. For Nasdaq the equity-index
COT is muddied by hedging and basis trades and is a weaker tool. Weekly horizon,
never intraday timing. **Off by default: symbol availability in Pine is unverified**
(D-018).

**Known weaknesses.** Noisiest data in the engine, held at ≥5m because a
flickering gate is worse than no gate. Internals feeds are availability-dependent;
`ignore_invalid_symbol` is on, so a missing feed must resolve to `active = false`,
never to neutral context. Gamma regime is manual and "Unknown" must not be treated
as favorable. **Never apply internals to gold** — TICK/ADD/VOLD/TRIN are
meaningless there.

---

### M8 — Overnight → intraday reversal prior  ·  **no category, bias only**
**Inputs:** enable, minimum overnight move (0.25 × ADR), saturation (0.75 × ADR),
decay window (150 minutes from RTH open), **maximum influence (0.05)**, show in
status table.

**Method.** Overnight close-to-open displacement as a fraction of ADR, mapped
`onRevMinPct`..`onRevSatPct` → 0..1, decaying to zero over `onRevAmMin` minutes
from the RTH open. `dir` **opposes** the overnight move.

**Why it is its own module (D-021).** This is the best-evidenced item in the entire
source research — close-to-open predicts open-to-close negatively, documented
across four asset classes including index futures, strongest in the morning
session. Buried inside M7 alongside internals and regime, its contribution could
never be observed or falsified separately. It now has an ID and a debug line.

**Why it is not a category.** It is a **daily-horizon prior**, not a bar-level
observation. The other seven modules answer *"what is true at this bar"*; M8
answers *"which way was today already leaning before this bar existed"*. Letting
it fill a confluence slot would let a statistical prior substitute for evidence
that something happened — exactly what D-019 exists to prevent.

**Why it is capped.** `side` is resolved by the gate *before* the bias applies, so
a bar with no qualifying side gets no adjustment however strong the prior. At 0.05
it can move a setup across at most one grade boundary and cannot manufacture a
grade from nothing. Evidence decides *whether*; the prior nudges *how good*.

**Known weaknesses.** Regime-dependent and decaying, like all documented
seasonality. The decay window is a guess. It has no weight in the weights group
because it does not have one — its influence *is* the cap.

---

## 4. Evidence ledger

Recorded so weights and future changes can be argued from evidence rather than
enthusiasm. The engine's weakest-evidenced components should never be its
highest-weighted.

| Claim | Standing |
|---|---|
| Order-flow imbalance predicts short-horizon price change | **Genuinely evidenced** — but decays within ~2 mid-price changes, generally sub-cost, spoofable |
| Overnight → intraday reversal | **Genuinely evidenced** — across four asset classes incl. index futures |
| VPIN as a toxicity/volatility gauge | **Genuinely evidenced** — not directional |
| VWAP-band reversion | Practitioner-supported, thin peer review |
| Volume-profile value-area reversion, market-profile day types | Practitioner-supported, thin peer review |
| RSI / Bollinger divergence standalone | **Largely folklore** — deliberately absent from this engine |
| Single footprint patterns in isolation | **Largely folklore** — and unavailable in Pine anyway |
| Day-of-week / time-of-day seasonality | Documented but regime-dependent and decaying |

**Methodological note carried over from the research:** regress imbalance out
before testing any "new" signal, or you will rediscover it under a new name. The
same applies inside this engine — M4's contribution should be residualized against
M1/M5 before its weight is raised.

---

## 5. Open questions

Resolved by the research notes: directionality (§2.1 — modules carry `dir`),
collinearity (§2.3 — category floor), NQ-vs-GC (one rule set, instrument-specific
context and sessions), hostile context (§3, M7), GC RTH (§2.5, pit window
confirmed).

Still open:

1. **Grade thresholds** (0.75/0.60/0.45), **weights**, and **`catDamp` = 0.5** —
   placeholders, no empirical basis.
2. **Category precedence** (D-020) — M2 over M3 for Location, M1 over M5 for
   Extension. Defensible but untested; if M3 is the stronger Location signal the
   push order should swap.
3. **Should M5 split** into separate Exhaustion and RVOL modules with separate
   weights? Note this would make E a three-module category and give damping real
   work to do there.
4. **M8's cap** (0.05) and decay window (150m) — both guesses.
5. **Naked POC decay** — how long does an unfilled POC stay relevant?
6. **Rule-2 hit rate.** If `{Q or F}` almost never fires, nothing will ever grade.
   That would indict M6's sweep definition (4–40 ticks, 10-minute reclaim) rather
   than the rule — but it is the first thing to measure once M6 exists.

Resolved since the last revision: directionality (`dir`), collinearity in both
gating (D-019) and scoring (D-020), M8's placement (D-021), and the D-013 volume
question (settled on notional, not contract count).

---

## 6. Benchmarks and kill criteria

From the source research, recorded here so the engine can be falsified rather than
endlessly tuned:

- **POC/level reaction rate below ~55%** → the location layer is not working;
  switch to trading with trend (band-walking, LVN breakouts) until balance returns.
- **Reversal win rate collapsing on trend days** → the regime gate (M7) is failing,
  not the modules.
- Track **ADX** or the **ratio of trend to range days** as the regime switch.
- Record the **toggle configuration** with every graded setup — grades are not
  comparable across configurations (§2.4).

---

## 7. Two-layer workflow

The engine is layer one of the setup the research recommends:

| Layer | Tool | Role |
|---|---|---|
| 1 · Screening | **This engine**, on GC / NQ (or ES) | Marks L + E + Q + C confluence zones. Pre-mark PDH/PDL/ONH/ONL, naked POCs, VWAP σ bands, and (manually) GEX walls. |
| 2 · Confirmation | Footprint / DOM platform | Supplies category **F** — absorption, exhaustion, stacked imbalance, unfinished auction, trapped traders. Requires Level 2 (~$15–16/mo per exchange). |
| 3 · Execution | MGC / MNQ | Risk-sized execution at the same price through the same matching engine. |

Reading microstructure on the full-size contract is the research's explicit
recommendation, and it holds for bar volume too — but the unit is **notional, not
contract count**. NQ is $20/pt against MNQ's $2/pt, so NQ's ~500k ADV carries ~3×
MNQ's ~1.6M in notional; GC's ~270k contracts (~27M oz) carry ~9× MGC's ~301k
(~3M oz). The full-size series is the heavier volume-at-price series in both
families.

`useFullSizeVol` still defaults **off** — but only because this workflow charts
NQ/GC directly, where the toggle is a no-op costing 2 `request.*` calls. **Turn it
on when charting MNQ/MGC** (D-013).

---

## 8. File map

| Path | Role |
|---|---|
| `SPEC.md` | This document. |
| `src/reversal_engine.pine` | The indicator. Scaffold, inputs, directional composite, grading. |
| `docs/PINE_LIMITS.md` | Platform constraints. Read before proposing a module. |
| `docs/DECISIONS.md` | Running log, D-001 onward. |

## 9. Disclaimer

Not financial advice. A research and education tool. Counter-trend trading has a
structurally low win rate and asymmetric blow-up risk. Nothing here is backtested
or guaranteed. Contract specs, fees and volumes change — verify against CME Group
before acting.
