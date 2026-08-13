# MGC Asia/London Strategy — Backtest Notes

`mgc_asia_london_strategy.pine` is the **backtestable `strategy()` twin** of the
live indicator `mgc_asia_london_confluence.pine`. Every signal-generation line
is copied verbatim from the indicator, so `longSignal` / `shortSignal` are
byte-identical. The strategy adds **only an execution layer** (entries, exits,
a Topstep model, and session A/B tooling). The indicator is untouched and is
still what you run for live alerts.

> **DISCLAIMER:** Not financial advice. Every threshold in this system is an
> untested hypothesis about Micro Gold. Nothing here is validated. The backtest
> is a *preliminary read*, not proof of an edge. Trade your own money at your
> own risk.

---

## 1. Strategy Tester properties — baked in vs. set manually

These are **baked into the `strategy()` declaration** — do **not** re-enter them
in the Properties tab (and if the Properties tab shows different values, the
declaration wins unless you tick "override"):

| Property | Value | Why |
|---|---|---|
| `initial_capital` | 150,000 | Topstep 150K account |
| `default_qty_type` | `strategy.fixed` | size comes from the script's `contracts` calc, not a % of equity |
| `commission_type` / `commission_value` | cash per contract, **$0.62/side** | ≈ $1.24 round-turn on MGC |
| `slippage` | **2 ticks** | deliberately pessimistic fill assumption |
| `pyramiding` | **0** | one position at a time; no stacking |
| `calc_on_every_tick` | **false** | bar-close evaluation only (no intrabar peeking) |
| `process_orders_on_close` | **true** | matches the indicator's `barstate.isconfirmed` gating; entries fill at the signal bar's close |
| `max_boxes/lines/labels` | 50/50/100 | drawing budget |

**You must set these manually in the Properties / Tester UI** (they are not part
of the declaration):

- **Chart symbol + timeframe** — load **MGC on the 5-minute chart**. The whole
  system is designed for 5m; a different timeframe changes every ATR, EMA, RVOL
  and CVD figure.
- **Backtest date range** — see §3. This is the single most important manual
  setting.
- **"Recalculate: On bar close"** should be on; leave "On every tick" off to
  match `calc_on_every_tick = false`.
- **Order size / commission overrides** — leave the Properties "Order size" and
  "Commission" fields at the defaults so they don't fight the declaration.
- **Session timezone / enable toggles / risk inputs** — these live in the
  script's **Inputs** tab, not Properties.

---

## 2. Plan limitation: Deep Backtesting & Bar Magnifier are Premium-only

You are on **TradingView Plus**, which means:

- **Deep Backtesting** (the multi-year historical run) is **Premium/Ultimate
  only** — not available to you.
- **Bar Magnifier** (intrabar fill precision) is **Premium/Ultimate only** —
  not available to you.

Practical consequence: your usable backtest window is **whatever history the 5m
chart actually loads** — roughly **2–4 months of 5-minute bars**. There is no
way on Plus to test years of data or to get sub-bar fill accuracy. Fills are
modeled at bar granularity with the 2-tick slippage assumption, which is why the
slippage figure is set pessimistically.

Because fills are bar-granular, a bar where **both** the stop and a target were
touched is resolved by TradingView's standard assumption (it generally assumes
the **worse** outcome — the stop — first). Treat any single trade's exit as
approximate; only the aggregate matters.

---

## 3. The `dataReady` caveat — pick a valid date range

`request.security_lower_tf()` (the 1-minute intrabar feed used for CVD) has
**limited historical depth**. On older bars it returns no data, so the CVD
component **silently scores zero**. The time-of-day **RVOL** baseline also needs
warm-up before it exists for each clock-minute. On those bars the system can
only reach **8/10** max score instead of 10 — a **different, weaker strategy**
than the one you run live.

The strategy guards against this with a **`dataReady`** flag, true only when
**both**:

1. the 1-minute delta array is present and non-empty (CVD is real), **and**
2. the RVOL baseline for the current clock-minute has been populated.

**`dataReady` is required for every entry** — no trade is taken on a bar where
CVD or the RVOL baseline is missing.

**How to pick your range:**

1. Add the strategy to a 5m MGC chart.
2. Look for the **faint red background tint** — it marks bars where data is
   **NOT** ready (the invalid region). It is usually the **oldest** portion of
   the loaded history.
3. Check the dashboard **"Data ready"** row (top-right): it reads `YES (valid)`,
   `no CVD`, or `no RVOL`.
4. Set the **Strategy Tester date range to start *after* the red tint ends** —
   i.e. only over the region where `dataReady` is continuously true. Backtesting
   into the red region mixes in trades from the weaker 8/10 variant and
   contaminates the stats.

The valid window will typically be shorter than the full loaded history —
usually the **most recent** stretch. That trimmed window is your real test set.

---

## 4. Session A/B testing

Pine's Strategy Tester won't split summary stats by session, so:

- Use the **`Session mode`** input (`Both` / `Asia only` / `London only`). It
  wires into the existing `enableAsia` / `enableLondon` gates. **`Both` is
  byte-identical to the indicator.** Run the backtest three times — once per
  mode — over the *same* valid date range and compare the Tester's summary.
- As a convenience, the **bottom-right table** maintains running per-session
  counters (trades / wins / gross P&L, attributed by **entry** session) so you
  can also read the Asia-vs-London split from a single `Both` run. It's a
  read-out only and touches no signal logic; toggle it off with "Show
  per-session P&L table".

---

## 5. Exits (all configurable via Inputs → "Exits")

1. **Stop** at `ATR × stopMult` (same distance the indicator computes).
2. **Scale-out** `Scale-out % at T1 (1R)` (default **50%**) at the 1R target.
3. **Breakeven** — move the remaining stop to entry after T1 fills (default on).
4. **Runner** — remainder exits at T2 (2R) (default on).
5. **Exhaustion exit** — close longs on `regBear`, shorts on `regBull`
   (default on). This is what the indicator's exhaustion X-crosses were for.
6. **Session flatten** — **non-optional.** All positions are closed at the
   **07:00 cutoff bar**, well before the 07:15 window ends. Topstep's trailing
   drawdown trails on end-of-day balance, so carrying a position past the
   session is not the strategy being tested.

---

## 6. Topstep realism model (Inputs → "Risk" and "Topstep model")

- **Daily loss limit** (default **$3,000**): intraday P&L is tracked from the
  **18:00 CME session open**. Once the loss exceeds the limit, **no new entries**
  for the rest of that trading day. *Approximation note:* the real Topstep DLL
  counts **unrealized** P&L too; a bar-close backtest can only approximate that
  (the script uses `strategy.equity`, which includes open-trade P&L, sampled at
  each bar close — it cannot see true intrabar excursions).
- **Max trades per day** (default **3**): counted from the 18:00 CME open.
- **Trailing drawdown** (default **$4,500**): the script tracks peak end-of-day
  balance and the current distance from the trailing threshold, shown on the
  dashboard ("Dist to trail DD"). **Trading is *not* halted on it** — the point
  is to *see* whether the strategy would have blown the account, not to hide it.

Both the daily loss limit and the trade counter **reset at the 18:00 CME open**,
not at midnight.

---

## 7. ⚠️ Do not over-optimize

This system fires roughly **1–1.5 signals per day**. Over the ~2–4 months you
can actually load on Plus, three months yields only about **80–120 trades**.

That is a **preliminary read, not a validated edge.** A sample that small is
easily fooled by luck, and curve-fitting the inputs (threshold, ATR multiple,
scale %, exhaustion window, etc.) to maximize net profit on 80–120 trades is a
near-guaranteed way to produce a number that will not survive live. Use the
backtest to check that the execution logic behaves as intended and to compare
Asia vs London at a coarse level — **not** to hunt for the "best" parameter set.
If a change only helps on this specific window, assume it is noise.

---

## 8. If you think you found a bug

If something in the **signal logic** looks wrong, **tell me — do not fix it in
the strategy file.** The two files must stay in lockstep; a silent fix here
would make the backtest test a different system than the indicator plots. Fixes
go into the indicator first, then get copied across.
