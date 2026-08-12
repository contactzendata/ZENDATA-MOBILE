# MGC Asia/London Confluence Indicator

A single-file **TradingView Pine Script v6 indicator** (`mgc_asia_london_confluence.pine`)
for **Micro Gold futures (MGC, COMEX)** on a **5-minute chart**, built around one
thesis:

> **Asia (18:00 → 02:00 ET) builds the range. London (03:00 → 07:00 ET) trades the break of it.**

It combines six confluence components into a 0–10 score per side, sizes positions
against a **Topstep $150K** risk profile, and renders everything on an on-chart
dashboard so the whole system fits in a single indicator slot.

> ⚠️ **Not financial advice.** Every threshold and parameter in this script is an
> **untested hypothesis** about how gold behaves in these sessions. Nothing here is
> validated or back-tested. Trade at your own risk.

---

## Setup

1. Open TradingView and load an **MGC** (or GC) chart on the **5-minute** timeframe.
2. Open the **Pine Editor**, paste the full contents of `mgc_asia_london_confluence.pine`,
   and click **Add to chart**.
3. Set the **Session timezone** input to match how you think about the sessions —
   `America/New_York` (default) or `America/Chicago`. The default session strings
   (`1800-0200`, `0300-0700`, …) are expressed in the selected timezone.
4. If you trade **GC** instead of MGC, change **`$ per tick`** from `1.0` to `10.0`.
5. To create alerts: **Add alert → Condition → "MGC Asia/London Confluence"**, then
   pick either the dynamic `alert()` output (rich message) or one of the
   `alertcondition()` entries (Long / Short / exhaustion warnings).

### Requirements / assumptions
- **TradingView Plus** plan (or higher). The script deliberately avoids
  `request.footprint()`, which is gated to Premium/Ultimate.
- Intended for the **5-minute** chart. The delta lower timeframe defaults to `1`
  (one minute) because sub-minute intervals are unreliable on Plus.

---

## What each input does

### Instrument
| Input | Default | Purpose |
|---|---|---|
| `$ per tick` | `1.0` | Dollar value of one min-tick move. MGC = $1.00 per 0.10. Set `10.0` for GC. |

### Sessions
| Input | Default | Purpose |
|---|---|---|
| `Session timezone` | `America/New_York` | Timezone all session windows are evaluated in. |
| `Asia RANGE build` | `1800-0200` | CME gold open → Tokyo close. **Builds the range; not a trade window.** |
| `Asia TRADE window` | `2000-0200` | Entries allowed here (after Shanghai open). |
| `London TRADE window` | `0300-0700` | Entries allowed here (London open onward). |
| `No-new-entries cutoff` | `0700-0715` | Hard cutoff; no new entries once this window begins. |
| `Enable Asia trade window` | `true` | A/B toggle for the Asia window. |
| `Enable London trade window` | `true` | A/B toggle for the London window. |

### Scoring
| Input | Default | Purpose |
|---|---|---|
| `Signal score (>=)` | `6` | Minimum score to fire a signal. |
| `Strong score (>=)` | `8` | Score at/above which a signal is marked "strong". |

### Anchored VWAP
| Input | Default | Purpose |
|---|---|---|
| `Show VWAP ±1σ bands` | `true` | Plot the ±1σ bands and their fill. |
| `London VWAP warm-up (bars)` | `6` | Keep using the CME anchor until the London anchor has this many confirmed bars. A freshly re-anchored VWAP sits on price with σ ≈ 0, which would make the VWAP component random exactly during the London open. |

### EMAs / HTF regime
| Input | Default | Purpose |
|---|---|---|
| `Fast EMA length` | `21` | Fast EMA (chart + HTF). |
| `Slow EMA length` | `50` | Slow EMA (chart + HTF). |
| `Min EMA separation (× ATR)` | `0.15` | EMAs must be separated by more than this × ATR (kills crossover whipsaw). |
| `EMA slope lookback (bars)` | `5` | Bars over which the fast EMA must be rising/falling. |
| `HTF regime timeframe` | `60` | Higher timeframe for the EMA 21/50 stack (1H). |
| `HTF confirm timeframe` | `15` | Timeframe whose EMA 21 slope must align (15m). |

### RVOL (time-of-day)
| Input | Default | Purpose |
|---|---|---|
| `RVOL threshold` | `1.5` | Relative volume needed to score the RVOL point. |
| `RVOL EWMA period (N)` | `20` | EWMA period for the per-clock-minute baseline (α = 2/(N+1)). |

### Delta / CVD
| Input | Default | Purpose |
|---|---|---|
| `Delta lower timeframe` | `1` | Intrabar timeframe used to approximate delta. |
| `CVD EMA length` | `21` | EMA of cumulative delta used in the CVD component. |
| `Delta-divergence lookback` | `10` | Bars for the "new high while CVD falls" veto. |

### RSI / divergence
| Input | Default | Purpose |
|---|---|---|
| `RSI length` | `14` | RSI period. |
| `Pivot left / right bars` | `5` / `2` | Pivot detection window. Divergence confirms `right` bars late. |
| `Max bars between pivots` | `40` | Ignore divergences spanning more than this many bars. |

### Range expansion filter
| Input | Default | Purpose |
|---|---|---|
| `Expansion day ratio (>=)` | `0.50` | Session range ÷ 20-day ADR ≥ this → expansion day. |
| `Rotation day ratio (<)` | `0.30` | Below this → rotation day; **all signals suppressed**. |
| `ADR lookback (days)` | `20` | Days used for the ADR baseline. |

### Risk / sizing (Topstep 150K)
| Input | Default | Purpose |
|---|---|---|
| `ATR length` | `14` | ATR for the stop distance. |
| `Stop = ATR ×` | `1.5` | Stop distance multiplier. |
| `Risk per trade ($)` | `300` | Dollar risk budget per trade (~0.67% of the ~$4,500 buffer). |
| `Max contracts` | `20` | Hard cap on computed size. |
| `Daily loss limit ($)` | `3000` | Displayed reference (counts unrealized P&L). |
| `Trailing max drawdown ($)` | `4500` | Displayed reference (trails on EOD balance only). |

### Alerts
| Input | Default | Purpose |
|---|---|---|
| `Signal debounce (bars)` | `6` | Suppress repeat same-side signals within this many bars. |

---

## The six confluence components

| Component | Points | Requirement |
|---|---|---|
| Anchored VWAP | 2 | Price on the correct side **and** VWAP sloping the right way (slope taken per-anchor). |
| HTF regime | 2 | 1H EMA 21/50 stacked, separated by > `minSepATR × ATR(1H)`, sloping over `slopeLookback`, **and** 15m EMA 21 aligned. |
| Structure | 2 | **London:** 2 consecutive closes beyond the Asia range. **Asia:** 2 consecutive closes beyond the session VWAP. |
| RVOL | 1 | Time-of-day relative volume above threshold. |
| Cumulative delta | 2 | CVD on the correct side of its EMA **and** the current bar's delta agreeing. |
| RSI | 1 | RSI > 50 (long) / < 50 (short), **or** hidden divergence active. |

A signal fires at **score ≥ 6** ("strong" at ≥ 8) **and only when that side's score
exceeds the opposite side's**, subject to gating (below).

### Vetoes and filters
- **Delta-divergence veto:** a new N-bar high while CVD falls zeroes the long score
  (failed breakout); the mirror applies to shorts.
- **Range-expansion filter:** session range ÷ 20-day ADR. ≥ 0.50 = expansion,
  0.30–0.50 = neutral, < 0.30 = **rotation → all signals suppressed**.
  **Applied during London only.** The session range accumulates from the 18:00
  CME open, so during Asia only a couple of hours have elapsed and the ratio is
  inherently small — testing it there would flag nearly every session as rotation
  and suppress Asia permanently. Asia passes this gate unconditionally; the
  dashboard still shows the day type during Asia, marked `(info)`.
- **Gating:** signals fire only when inside an *enabled* trade window, before the
  cutoff, the expansion filter passes, and the bar is confirmed
  (`barstate.isconfirmed`).

### Divergence handling
- **Hidden divergence** (price higher-low + RSI lower-low, or the short mirror) =
  trend continuation → **contributes to the entry score.**
- **Regular divergence** (price higher-high + RSI lower-high, or the mirror) =
  exhaustion → plotted as an **X-cross exit/trail warning with its own alert**, and
  **never contributes to the entry score.**

---

## Position sizing

- Stop distance = `ATR(14) × stopMult`.
- Converted to ticks via `syminfo.mintick`, then to dollars via `$ per tick`.
- `contracts = floor(riskUSD / riskPerContract)`, capped by `maxContracts`.
- Targets: **T1 = 1R, T2 = 2R.**

The dashboard shows the computed contract count and the **actual dollar risk if
filled**, so you can sanity-check before entering.

---

## Dashboard (top-right)

Rendered on the last bar only: current session, bull/bear score, 1H regime, VWAP
state, RVOL, CVD vs its EMA, range/ADR %, day type, ATR stop in ticks, position
size, dollar risk if filled, any active veto, and which windows are enabled.
Cells are color-coded green / red / gray by state.

---

## Known limitations

- **Delta is an approximation, not order flow.** With no `request.footprint()` on
  Plus, delta is derived from 1-minute intrabars using the **tick rule**
  (intrabar close > open ⇒ buy volume, < open ⇒ sell, equal ⇒ split 50/50). It is a
  rough participation proxy, not true bid/ask delta. On a 5-minute chart there are
  only ~5 intrabars per bar, so the resolution is coarse.
- **Divergence confirms late.** Regular/hidden divergence relies on
  `ta.pivothigh`/`ta.pivotlow`, which confirm `pivotRight` bars (default 2) after
  the pivot. Signals that depend on a pivot are therefore inherently delayed.
- **Divergence is price-anchored.** Swings are detected on **price** (high/low),
  and the RSI value is sampled at that same pivot bar. Detecting swings on the
  RSI series instead would yield a different, generally noisier divergence set.
- **RVOL baseline warms up.** The time-of-day EWMA needs several sessions before the
  per-clock-minute baseline is meaningful; early on, RVOL may read `n/a`.
- **ADR / daily data.** The 20-day ADR uses completed daily bars (no look-ahead), so
  it reflects yesterday's 20-day average, not an intraday update.
- **Session strings are timezone-sensitive.** Changing the timezone input without
  adjusting the session windows will shift what counts as "Asia" or "London".
- **Asia has no range-expansion gate.** Because the rotation test is meaningless
  that early in the session (see above), Asia signals are *not* filtered for
  rotation days. Asia is the rotational session by thesis, so treat Asia signals
  as inherently lower-conviction than London ones.
- **The London VWAP anchor is delayed by design.** For the first `londonVwapWarmup`
  bars after 03:00 the script is still reading the CME-anchored VWAP, so the VWAP
  component reflects the whole overnight session rather than the London open.
- **Everything is an untested hypothesis.** Thresholds, weights, and windows are
  starting guesses, not optimized or validated parameters.

---

## Compliance notes

- `//@version=6`, indicator (not strategy), single file.
- Every `request.security()` / `request.security_lower_tf()` uses
  `lookahead = barmerge.lookahead_off` — **no repainting by design.**
- No `request.footprint()` (Plus-plan safe).
