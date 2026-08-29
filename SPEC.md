# Reversal Engine — Technical Specification

**Target:** TradingView Pine Script v6, single indicator, `overlay = true`
**Instruments:** NQ (E-mini Nasdaq-100, CME) · GC (Gold, COMEX) — micros MNQ/MGC as aliases
**Chart timeframes:** 1m, 5m, 15m (all supported without retuning)
**Status:** Scaffold complete. No module logic implemented.

> **AWAITING RESEARCH NOTES.** Sections marked `⟨PENDING⟩` are structural
> placeholders. The trading logic, thresholds, and empirical claims belong in
> those sections and have deliberately **not** been invented here — a spec that
> guesses at its own hypotheses is worse than an incomplete one. Paste the notes
> and they get folded into the numbered subsections below without restructuring.

---

## 1. Purpose and scope

A reversal-context engine, not an entry system. It answers one question per bar:
*how much independent evidence currently supports a reversal here, and how good is
that evidence?* Output is a three-tier grade (A/B/C), or nothing.

**Explicitly out of scope** (record here if that changes): position sizing, stop
and target placement, dollar risk, trade management, and any form of order
execution or strategy backtesting. This is an `indicator`, not a `strategy`.

**Non-goals that are easy to drift into:** predicting direction independently of
context; producing a signal on every bar; being tunable per-session.

---

## 2. Architecture

Single script, seven modules, one composite. The pipeline per confirmed bar:

```
                       ┌─────────────────────────────────────┐
  instrument detect →  │  M1 VWAP extension                  │
  timeframe normalize  │  M2 Structural levels               │
  session resolve      │  M3 Volume profile                  │ each → {score 0..1,
                       │  M4 Delta / CVD  (APPROXIMATION)    │         active bool}
                       │  M5 Exhaustion & RVOL               │
                       │  M6 Sweep & reclaim                 │
                       │  M7 Context filters                 │
                       └──────────────┬──────────────────────┘
                                      │
                    weighted composite (D-002 contract)
                                      │
                     confluence floor (minActive, D-003)
                                      │
                        A / B / C threshold mapping
                                      │
                  context grade cap (D-004, hostile → max B)
                                      │
                              published grade
```

### 2.1 Module contract

Every module is a function returning a `ModuleOut`:

| Field | Type | Meaning |
|---|---|---|
| `score` | float | Normalized **0..1**. Only meaningful when `active` is true. |
| `active` | bool | This module has something to say about *this* bar. |
| `note` | string | Human-readable reason, for the eventual detail pane. |

Three rules, all load-bearing:

1. **Normalize honestly.** 0..1 must mean the same thing across modules —
   0 = no support, 1 = the strongest form of this evidence the module can express.
   Saturation points are inputs, not magic numbers.
2. **`active = false` when data is missing.** Never return a neutral 0.5 as a
   stand-in. The composite cannot distinguish a real 0.5 from a fabricated one
   (D-011).
3. **No drawing inside a module.** Modules compute; the RENDER section draws
   (D-010).

### 2.2 Composite

Per D-002:

```
module OFF      → excluded from numerator and denominator   ("not measured")
module ON, idle → contributes 0.0, weight stays in denominator ("nothing there")

composite = Σ(scoreᵢ × weightᵢ) / Σ(weightᵢ)   over enabled modules
```

Then:
- `activeCount < minActive` → suppressed to no-grade (D-003).
- Threshold map → A ≥ 0.75, B ≥ 0.60, C ≥ 0.45, below → nothing. All inputs.
- Hostile context caps the grade at the configured ceiling, default B (D-004).

**Grades are comparable across bars for a fixed configuration, and not comparable
between configurations.** Any performance record must capture the toggle state.

### 2.3 Instrument profiles

| | NQ / MNQ | GC / MGC |
|---|---|---|
| Exchange | CME | COMEX |
| Tick | 0.25 | 0.10 |
| RTH | 09:30–16:00 ET | 08:20–13:30 ET (pit-equivalent, D-007) |
| Overnight | 18:00–09:30 ET | 18:00–08:20 ET |
| Context symbols | `USI:TICK`, `USI:ADD`, `CBOE:VIX` | `TVC:DXY`, `TVC:US10Y`, `TVC:US02Y` |

Detection is substring matching on `syminfo.root`, micros first for display naming
only. Micros share the full-size profile exactly (D-006). Tick size is read from
`syminfo.mintick`, never hardcoded.

### 2.4 Timeframe normalization

No input is expressed in bars. Every duration is in **minutes**, converted by
`f_bars(minutes)` at runtime. Every price-distance threshold is in **ticks**.
Together these make the engine portable across 1m/5m/15m and across NQ/GC without
a per-combination lookup table (D-005).

### 2.5 No-repaint guarantee

- All external data flows through `f_sec()` / `f_secLTF()` (D-008). `f_sec()`
  hardcodes `lookahead = barmerge.lookahead_off`; `request.security_lower_tf()`
  takes no `lookahead` argument and cannot look ahead by construction, so its
  wrapper centralizes auditing and the `f_ltfValid()` strictly-lower-TF guard.
- Grade publication is gated on `barstate.isconfirmed`.
- Developing-bar values (session range, live VWAP sigma, developing POC) update
  within the bar by design; modules that use them must say so.
- `request.*` budget: ~9 of ~40 planned. See the header table in
  `src/reversal_engine.pine`; every addition needs a DECISIONS entry.

---

## 3. Modules

Each subsection has the same shape: **Inputs** (scaffolded, in the code today) ·
**Method** ⟨PENDING⟩ · **Score mapping** ⟨PENDING⟩ · **Active condition** ⟨PENDING⟩
· **Known weaknesses**.

### M1 — VWAP extension with sigma bands
**Inputs:** anchor (Session / RTH open / Week / Overnight open), inner sigma (2.0),
outer sigma (3.0), warm-up minutes (30), plot toggle.
**Method:** ⟨PENDING⟩
**Score mapping:** ⟨PENDING⟩ — intent is interpolation between inner and outer
sigma, saturating at the outer.
**Active condition:** ⟨PENDING⟩ — must be false during the warm-up window, since a
fresh anchor has sigma near zero and produces meaningless extension readings.
**Known weaknesses:** sigma is regime-dependent; 2σ in a compressed overnight is
not 2σ in a trend day. Whether the bands need volatility normalization is an open
question for the notes.

### M2 — Structural levels
**Inputs:** per-level toggles (PDH/PDL, PDC, ONH/ONL, IB, opening range, RTH open),
IB length (60m), opening-range length (15m), proximity (8 ticks), draw toggle.
**Method:** ⟨PENDING⟩
**Score mapping:** ⟨PENDING⟩ — intent is proximity plus level-class confluence
(two levels stacked at one price is stronger than one).
**Active condition:** ⟨PENDING⟩
**Known weaknesses:** level *stacking* and level *importance* are different things
and the scoring must not double-count them. GC's pit-session framing (D-007) is a
convention choice, not a fact.

### M3 — Volume profile
**Inputs:** rows (48), value area (70%), intrabar TF (1m), historical sessions
(10), naked POC toggle, HVN/LVN toggle, draw toggle.
**Method:** hybrid sourcing per D-001 — current and prior session from intrabars,
older sessions from chart bars. Remaining derivation ⟨PENDING⟩.
**Score mapping:** ⟨PENDING⟩
**Active condition:** ⟨PENDING⟩
**Known weaknesses:** **resolution asymmetry is structural.** Chart-bar-derived
POCs from older sessions are less precise than the intrabar-derived current POC
and must not score as tightly (D-001). Also the largest consumer of the 500-box
budget — 48 rows × 2 sessions is 96 boxes before anything else draws.

### M4 — Approximated delta / CVD  ⚠ NOT ORDER FLOW
**Inputs:** intrabar TF (1m), CVD reset (Session / RTH open / Day / Never),
divergence lookback (50m).
**Method:** tick rule on intrabar candles — intrabar close > open counts volume as
buying, close < open as selling, equal contributes zero. Remaining ⟨PENDING⟩.
**Score mapping:** ⟨PENDING⟩
**Active condition:** ⟨PENDING⟩ — **must** be false when the intrabar timeframe is
not strictly lower than the chart timeframe (the 1m-chart case).
**Known weaknesses:** this is an approximation with a known error rate that rises
in fast, thin, one-tick-range conditions — exactly reversal conditions. Weighted
0.5 by default and structurally barred from carrying a grade alone. See
`docs/PINE_LIMITS.md` §2. If the plan tier ever provides real footprint data, this
module gets **re-specified**, not re-tuned.

### M5 — Range exhaustion and time-of-day RVOL
**Inputs:** ADR days (20), exhaustion ratio (0.85), RVOL baseline sessions (20),
RVOL threshold (1.5), time-of-day bucket (30m).
**Method:** ⟨PENDING⟩ — RVOL normalizes against the same clock bucket on prior
sessions, not a flat average, so an 09:35 volume spike is judged against other
09:35s.
**Score mapping:** ⟨PENDING⟩
**Active condition:** ⟨PENDING⟩
**Known weaknesses:** exhaustion and RVOL are two distinct claims sharing one
module; whether they should be separate modules with separate weights is an open
question. Holiday and half-day sessions distort both baselines.

### M6 — Sweep and reclaim
**Inputs:** minimum penetration (4 ticks), maximum penetration (40 ticks), reclaim
window (10m), mark toggle.
**Method:** ⟨PENDING⟩ — penetration beyond a tracked level within the min/max
band, followed by a close back inside within the reclaim window.
**Score mapping:** ⟨PENDING⟩
**Active condition:** ⟨PENDING⟩
**Known weaknesses:** **confirmation is inherently late** — the reclaim window
cannot be evaluated until it elapses, so this module is structurally N bars behind
the extreme. Depends on M2/M3 for the levels it watches, which is the engine's one
real inter-module dependency and a collinearity risk: a sweep of a level and
proximity to that same level are not independent evidence.

### M7 — Context filters (gate)
**Inputs:** hostile-context cap (A/B/C/None, default B), three symbols per
instrument family, context TF (5m).
**Method:** ⟨PENDING⟩ — resolves both an ordinary sub-score **and**, independently,
a hostile flag. The two channels must not be derived from one threshold (D-004).
**Score mapping:** ⟨PENDING⟩
**Active condition:** ⟨PENDING⟩
**Known weaknesses:** noisiest data in the system; held at ≥5m for that reason. A
gate that flickers is worse than no gate. `USI:TICK` and `USI:ADD` availability is
plan- and feed-dependent — `ignore_invalid_symbol` is on, so the module must treat
a missing feed as `active = false` rather than as neutral context.

---

## 4. Open questions for the research notes

Listed so the notes can answer them directly rather than being reverse-engineered:

1. **Directionality.** Do modules score a reversal *magnitude* only, with direction
   resolved elsewhere, or does each module carry a signed bias? The current
   contract is unsigned 0..1, which means direction is currently undefined.
2. **Collinearity budget.** M2 proximity, M3 POC proximity, and M6 sweep all key
   off levels. Which pairs are permitted to score simultaneously?
3. **Grade thresholds.** 0.75/0.60/0.45 are placeholders with no evidence behind
   them.
4. **`minActive` = 3** is a guess (D-003) and should come from the observed
   distribution of active counts.
5. **Weights.** Currently 1.0 across the board except delta and context at 0.5.
   No empirical basis.
6. **Session handling for NQ vs GC** where the two disagree — is the engine one
   set of rules with different sessions, or two behavioral models?
7. **What counts as hostile context**, per instrument, concretely.

---

## 5. File map

| Path | Role |
|---|---|
| `SPEC.md` | This document. |
| `src/reversal_engine.pine` | The indicator. Scaffold + inputs + composite pipeline. |
| `docs/PINE_LIMITS.md` | Platform constraints that shape the design. Read before proposing a module. |
| `docs/DECISIONS.md` | Running log of tradeoffs, D-001 onward. |

---

## 6. Disclaimer

Not financial advice. A research and education tool. Every threshold in it is an
untested hypothesis until validated against your own data. Nothing here is
backtested or guaranteed.
