# Pine Script v6 — What This Project Genuinely Cannot Do

Scope: constraints that materially shape the Reversal Engine's design. This is a
list of things no amount of clever Pine will fix, kept separately from ordinary
implementation difficulty. If a module in `SPEC.md` seems weaker than the idea
that motivated it, the reason is almost always on this page.

**Numeric caps below reflect TradingView's documented limits at time of writing.
They are plan- and platform-dependent and TradingView changes them. Re-verify the
ones marked ⚠ against the current Pine reference before relying on a headroom
argument.**

---

## 1. No Level 2 / DOM / market depth

Pine has no access to the order book at any depth. There is no bid size, no ask
size, no book imbalance, no iceberg or spoof detection, no resting-liquidity map.
The only prices available are trade prices (OHLC) and, in limited contexts, the
current best bid/ask on a realtime bar — never historically, and never with size.

**Consequence for this project:** every "liquidity" concept in the spec is
inferred from *price behavior around a level*, not from observed resting orders.
The sweep-and-reclaim module (M6) detects that price penetrated a level and came
back. It does not and cannot know that stops were resting there. The level is a
hypothesis about where liquidity sits; the sweep is evidence the hypothesis was
worth something. Do not describe M6 output as "liquidity taken" — describe it as
"failed penetration".

## 2. No true bid–ask trade classification

Pine cannot tell you whether a trade printed at the bid or the ask. There is no
aggressor side, no signed volume, no real delta.

**Consequence:** module M4 uses the **tick rule** on intrabar candles — intrabar
close > open counts the intrabar's volume as buying, close < open as selling,
close == open splits or contributes zero. This is a decades-old academic
approximation with a known error rate that rises sharply in fast, thin, or
one-tick-range conditions — exactly the conditions a reversal setup cares about.

M4 is therefore:
- labeled "approximation" in its input group heading, in the code, and in any UI it
  ever renders;
- down-weighted by default (0.5 vs 1.0 for structural modules);
- forbidden from being the module that carries a grade on its own (the
  minimum-active-modules floor enforces this structurally).

⚠ TradingView does expose real footprint/order-flow data (`request.footprint()`
and the footprint chart type) on higher-tier plans. If the target plan changes,
M4 should be re-specified rather than tuned — the approximation and the real thing
are different measurements, not the same measurement at different quality.

## 3. No market-by-order (MBO)

No per-order granularity, no queue position, no order lifecycle. Anything that
depends on distinguishing one large participant from many small ones is out of
reach. Where the spec mentions "absorption", it means *price failing to advance
while volume is elevated*, which is an inference from aggregate bars, not an
observation of a passive participant holding a level.

## 4. No native gamma exposure or options data

Pine has no options chain access. No strikes, no open interest by strike, no
implied volatility surface, no dealer positioning. GEX, charm, vanna, and
zero-gamma levels cannot be computed inside Pine, and cannot be fetched from an
external API — Pine has no HTTP client, no file I/O, and no way to reach any
network resource.

**Consequence:** the source research ranks GEX a *first-class* reversal tool for
NQ — positive-gamma regimes produce pinning and mean-reversion near call/put walls;
negative-gamma regimes amplify moves and must not be faded. None of it is
computable here. So M2 exposes three manual `input.float` level fields (gamma
flip, call wall, put wall) and M7 exposes a manual three-way regime selector.
There is no third option, and **no proxy is invented** — a "gamma-like" number
derived from price behavior would be a plausible-looking value with no measurement
behind it (see DECISIONS D-018).

Two asymmetries worth stating explicitly:
- **"Unknown" regime is not "favorable" regime.** The research's rule is
  one-sided — fade only in positive gamma, never in negative — so an unset
  selector must not unlock fades.
- Even where GEX *is* available externally it is **modeled, not observed**: OI
  updates end-of-day, dealer positioning is assumed, and for NQ it is computed on
  NDX/QQQ and applied to the futures. Regime context, never a trigger.

**No economic event calendar.** Pine has `request.economic()` for certain economic
*data series*, but no calendar of scheduled event times. The research says to stand
down into FOMC, CPI, NFP and PPI; there is no automatic way to know when those are.
A manual stand-down toggle plus a blackout window is the entire mechanism.

**COT data is uncertain, not impossible.** TradingView carries CFTC series, so a
`request.security` against one may work — but whether the specific series resolve
in this context is unverified, and a data source that silently returns `na` is
worse than an absent one. Scaffolded, defaulted off, and required to self-disable
rather than report neutral.

Related and equally hard: Pine cannot read an external file, call a webhook
inbound, or share state with another script. Alerts go out; nothing comes in.

## 5. `request.security_lower_tf()` intrabar caps ⚠

Intrabar data is the backbone of both M3 (volume profile) and M4 (delta), and it
is capped hard:

- A script can process a limited **total number of intrabars** across all
  `request.security_lower_tf()` calls — on the order of **100,000** on standard
  plans, roughly double that on the highest tiers. Beyond the cap, the call
  returns no data for older bars, silently degrading history rather than erroring.
- The lower timeframe must be **strictly lower** than the chart timeframe. On a
  1-minute chart that forces a seconds-based timeframe, which is unavailable or
  unreliable below the higher plan tiers.
- Intrabar data is only available for as far back as the exchange/plan provides
  it, which is materially shorter than daily history.

**Consequences, both load-bearing:**

1. **The hybrid profile (D-001).** Building every historical session's profile
   from 1-minute intrabars would exhaust the intrabar budget within a few days of
   history. So current + prior session use intrabars; older sessions fall back to
   chart-bar distribution. Naked POCs discovered from older sessions are therefore
   *lower-resolution* than the developing POC, and the spec must not treat them as
   equally precise.
2. **M4 self-disables on 1-minute charts** rather than silently returning a
   degraded or empty series. A delta module that quietly reports zero is worse
   than one that reports "unavailable", because the composite reads a zero as a
   real measurement.

## 6. Drawing object limits: 500 each

`max_boxes_count`, `max_lines_count`, `max_labels_count` cap at **500** each
(default 50 if unspecified). All three are set to 500 in
`src/reversal_engine.pine`. These are *totals for the whole script*, and Pine
deletes the oldest object when the ceiling is hit — silently, mid-chart.

This is a real budget, not a formality. The volume profile alone can consume it:
48 rows × (current + prior session) = 96 boxes before a single structural level,
sweep marker, or naked POC line is drawn. Adding HVN/LVN shading and 10 sessions
of naked POCs pushes past 500 quickly.

**Consequences:**
- Profile row count is an input, and its tooltip states that it shares a budget.
- Historical objects must be *reused* (`box.set_*` on existing objects) rather
  than created per bar wherever a module draws repeatedly.
- Any module that draws must degrade gracefully — draw recent objects, drop old
  ones deliberately — instead of relying on Pine's silent eviction.

## 7. ~40 `request.*()` calls per script ⚠

The documented ceiling is around **40** calls, counting `request.security`,
`request.security_lower_tf`, `request.dividends`, `request.economic`, and the rest
of the family. Pine v6 permits *dynamic* requests (call sites inside loops and
conditionals, with series symbol arguments), but this does not raise the ceiling —
it changes when a call site executes, not how many exist.

The engine's planned budget is documented in the file header and totals ~9 of 40.
The headroom is deliberate: context filters (M7) are the module most likely to
grow, and each additional context symbol is a call.

**Consequence:** context symbols are fixed inputs (three per instrument family,
only one family's set requested at a time), not an arbitrary user-supplied list.

## 8. Repainting rules for higher-timeframe data

The core problem: on a historical bar, a naive `request.security()` can hand the
script data from an HTF bar that had not finished forming at that point in real
time. The backtest then looks better than the live behavior, and the difference
appears only after deployment.

Rules this project holds to:

- **`lookahead = barmerge.lookahead_off` on every call that accepts it, without
  exception.** Enforced structurally: `request.security` is never called directly,
  only through `f_sec()`, which hardcodes it. (`request.security_lower_tf()` takes
  no `lookahead` argument — it returns intrabars of the *current* chart bar and
  cannot look ahead by construction; its wrapper `f_secLTF()` exists for call-site
  auditability and the lower-TF guard.) Any new external data dependency goes
  through a wrapper and gets an entry in `DECISIONS.md`.
- **Signal evaluation is gated on `barstate.isconfirmed`**, so a setup cannot
  appear, disappear, and reappear within a forming bar.
- **`lookahead_off` fixes lookahead, not lag.** With it, the HTF value on a
  historical bar is the last *completed* HTF bar's value, so an HTF series is
  stale for the duration of the forming HTF bar. That lag is correct and honest;
  it must be designed around, not tuned away.
- **The realtime bar still updates.** Anything computed from the developing bar
  (developing POC, session range, live VWAP sigma) legitimately changes until the
  bar closes. This is not repainting, but it *looks* like it, so modules that use
  developing values must expose that they do.
- The one genuinely unfixable case: a script recalculating from scratch on chart
  reload cannot reproduce intra-bar history it never stored. Realtime-only state
  (how a bar got to its close) is gone after a reload.

## 9. Smaller constraints that still bite

- **No true session volume profile primitive.** TradingView's own volume profile
  indicators use data Pine scripts do not get. M3 rebuilds it from bars.
- **No tick data.** The finest available granularity is the lowest chart/intrabar
  timeframe, not individual trades.
- **`var`/`varip` state does not survive a chart reload or a settings change.**
  Any "since session open" accumulator rebuilds from history on reload, which is
  fine only because it is computed from bar data that still exists.
- **No cross-script communication.** Moving heavy internals to a companion pane
  later (an explicit architecture goal) means *duplicating* the evaluation code in
  a second script, not importing it — unless it is factored into a Pine **library**,
  which is the only real code-sharing mechanism and carries its own publishing
  workflow.
- **Execution is bar-by-bar, left to right, with no way to look forward.** Every
  "confirmation" costs bars, and any module needing N bars of confirmation is
  structurally N bars late. M6's reclaim window is the clearest example.
- **String/label rendering is the only text output.** There is no logging, no
  console, no debugger. Development instrumentation costs drawing-object budget.
- **Back-adjusted continuous contracts are not level-safe.** A `1!` series shifts
  every historical price at each roll, so absolute horizontal levels — exactly what
  M2 and M3 produce — are unreliable on them. Pine cannot un-adjust the series;
  the engine detects and flags the case (DECISIONS D-017) and the levels should be
  read on the live front month.
- **Volume is contract count, not notional.** This matters for the "read full-size,
  execute micro" recommendation: that advice is about *book depth*, which Pine
  cannot see. By contract count MNQ actually trades more than NQ, so switching the
  volume source to the full-size contract is not automatically an upgrade
  (DECISIONS D-013).

---

## 10. Plot outputs — 64 per script, no override

`plot()`, `plotshape()`, `plotchar()`, `plotcandle()`, `plotbar()` and
`plotarrow()` share one budget of **64 per script**, and there is no
`max_plots_count` to raise it the way there is for boxes, lines and labels.
`display = display.data_window` does **not** exempt a plot: an invisible
diagnostic output costs exactly as much as a drawn one.

This binds harder than it first looks, because plots accumulate one or two at a
time as diagnostics are added, so the ceiling is reached without warning during
routine work rather than at a moment when anyone is thinking about it.

**Current usage: 60 of 64.** The 48 per-(slot, block) context cells of D-055
could not all be emitted; D-057 splits them into per-symbol totals for all four
slots plus a selector-driven per-block breakdown for one, which is what fits.

`pinecheck.py` counts them and warns from 56 upward. Beyond that, the way to
make room is to retire the data-window plots of closed diagnostics — the same
disposal that D-052 applied to table rows.
