# MNQ ICT Confluence — Findings

**Status: build stopped at the diagnostic stage. Not converted to a strategy.**

Instrument: MNQ (Micro E-mini Nasdaq-100), 5-minute chart, Asia and London
sessions. Platform: TradingView Plus. Implementation: `mnq_ict_confluence.pine`.

Sample: ~40 trading days, roughly 11,500 five-minute bars, single load, single
instrument, single volatility regime.

This document records what was measured and what it showed. It is not a
post-mortem. The indicator file is left exactly as it was when the stop
condition was met — every diagnostic row in it is evidence for the numbers
below, and editing the file would invalidate them.

---

## 1. What was built

Six stages, each gated on the previous one being verified on a chart.

| Stage | Contents |
|---|---|
| 1 | Session engine (Asia/London, trading-day attribution anchored at the Asia open), ATR and rolling median session ranges, a tiered liquidity-pool map (session/day/week levels, equal highs/lows, swings), anti-repaint fractal pivots, debug table |
| 2 | Displacement bars, liquidity sweeps as an explicit per-pool state machine (PENETRATED → SWEPT \| BROKEN OUT \| EXPIRED), BOS/CHoCH/MSS from confirmed pivots, sweep↔MSS pairing |
| 3 | Fair value gaps, inverse FVGs, displacement-anchored order blocks, breakers, dealing range → premium/discount/OTE, and a **unified POI API** so an order block and an FVG left by the same leg are scored once, not twice |
| 4 | SMT divergence against ES, confluence only |
| 5 | Six-component confluence score out of 10 with a mandatory sweep+MSS gate |
| 6 | Entry trigger, structural stop, two-target plan, guard rails, position sizing, `alert()` calls |

**Architectural invariants held throughout:** every state mutation gated on
`barstate.isconfirmed`; every `request.security()` using `lookahead_off` plus a
`[1]` offset; all clock logic on the `"America/New_York"` string; no
Premium-only features.

**The scoring model as implemented:**

| Component | Weight | Range | Mandatory |
|---|---|---|---|
| Sweep × `poolWeight(tier)` | 3.0 | 0.90–3.00 | yes |
| MSS confirming that same sweep | 2.0 | 2.00 | yes |
| POI × quality | 1.5 | 0.60–1.50 | no |
| Dealing-range location | 1.5 | 0 / 0.75 / 1.50 | no |
| SMT × strength × session scale | 1.0 | 0–1.00 London, 0–0.50 Asia | no |
| Session premium/discount | 1.0 | 0 / 0.50 / 1.00 | no |

Threshold 7.0, strong band 8.0. Without a sweep **and** an MSS paired to that
same sweep, every component is zero.

---

## 2. What the diagnostics measured

Every figure below is a measurement off the loaded chart, with its denominator.

### Upstream stages — healthy

| Measure | Value |
|---|---|
| Sweeps confirmed : breakouts rejected | **370 : 240** (1.5:1), 9 pending-record upgrades |
| Liquidity pools by tier | T0 6 \| T1 16 \| T2 20 = 42 of 56 cap, 25 active |
| Armed setups (sweep+MSS pairs) | **64** over 40 days ≈ 1.6/day |
| Dealing range present while armed | **64 / 64 (100%)** |
| SMT candidates → passed pool gate | 736 → **205** (28%) after the gate was fixed |
| POI zone height, book | mean **20.6**, median **10.25** points |
| POI zone height, selected by `bestPOI` | mean **18.5** (n=10) |

### The funnel — where it stops

| Measure | Value |
|---|---|
| Armed setups reaching the 7.0 threshold | **10 / 64 = 16%** |
| Reachable score ceiling with OTE unavailable | **~7.9** against a 7.0 threshold |
| Entry triggers fired | **10** |
| Entries surviving the guard rails | **0** |
| — blocked by session boundary | 3 |
| — blocked by the 8–30 point stop band | 7, **all above 30** |
| Stop anchor, swept extreme | mean **49.1** points |
| Stop anchor, POI far edge | mean **30.9** points, `poiNa` 0 |

### OTE reachability

| Measure | Value |
|---|---|
| POI-bars where a zone overlapped the OTE band | 1,670 / 26,209 = **6%** |
| DR-bars with **close** inside the OTE band | 156 / 3,171 = **5%** |
| DR-bars with the bar's **range** touching the band | **10%** |

### Dealing-range survival

| Measure | Value |
|---|---|
| Dealing ranges observed | **44** |
| — died by age (120 bars) | 11 |
| — died by close back through the swept extreme | **33** |
| Break deaths inside the entry window (measured from the sweep) | **21** |
| Break deaths at 26–60 bars / beyond 60 bars | 4 / 3 |
| Range width at MSS → at death | 91.8 → 124.7 points, capped on 23 / 44 |

### The deciding measurement

Of the 21 ranges that broke while the entry window was open:

| Measure | Value |
|---|---|
| CE was touched first — a fill, then the stop level reached (**world A**) | **14** |
| CE never touched — no fill, nothing lost (**world B**) | **7** |
| No eligible POI existed | **0** |
| Of the 14: stop inside the 8–30 band, so a real trade | **9** |
| Of those: TP1 reached before the break | **at most 4** |
| **Peak score, world A** | **6.3, range [5.3 – 7.6], n=14** |
| **Peak score, world B** | **5.4, range [0.0 – 7.8], n=7** |

---

## 3. The findings, ranked by how load-bearing they are

### 3.1 The confluence score does not separate world A from world B — **this stopped the build**

World B's peak-score range `[0.0 – 7.8]` **fully contains** world A's
`[5.3 – 7.6]`, and B's maximum is *higher* than A's. The 0.9-point difference in
means is inside sampling noise at n=14 / n=7.

The score does not select on the thing that determines the outcome. A setup that
filled and then reached its stop is not distinguishable, by score, from one that
never filled at all.

The decision rule was **written down before the numbers were seen**: material
separation with limited overlap → continue to strategy conversion; heavy overlap
→ stop rather than re-weight until separation appears. The second case obtained.
No component weights, thresholds or band positions were changed afterwards.

*Caveat, which does not change the conclusion:* world B's 0.0 floor is likely a
range whose gate dropped mid-life rather than a genuinely-scored setup. Even
discarding it, B's maximum still exceeds A's maximum.

### 3.2 The score and the trigger disagree about what "reaching a level" means

`inOTE()` evaluates band membership on the bar's **close**. The retest trigger
fires on `low <= p.ce` — a **wick**. Measured over 3,171 dealing-range bars:
close-in-band **5%**, range-touches-band **10%**. A factor of two.

The two halves of the model have used different definitions of "price reached
this level" since stage 3. This was left unfixed deliberately: finding 3.1 makes
location *precision* irrelevant, and changing it would have altered the file the
measurements were drawn from.

**Any rebuild should pick one price series and use it in both places.**

### 3.3 The 0.62–0.79 retracement band is close to structurally unreachable overnight

Price closes inside the band on 5% of dealing-range bars, while a dealing range
exists 100% of the time a setup is armed. Overnight MNQ sweeps a level, breaks
structure, and continues rather than retracing into the band.

The consequence is arithmetic, not stylistic. With OTE unavailable the reachable
ceiling is **~7.9 against a 7.0 threshold** — under one point of headroom in a
ten-point model — which explains the 16% pass rate directly.

The band was **not** moved. Moving it would have required either a consistent
alternative retracement depth in the data (never established — see 5.4) or an
accepted premise that price retraces at all.

### 3.4 The structural stop is too wide for the session's own range

The swept-extreme anchor measured **49.1 points** mean. Median London session
range is 60–85 points. At 1:1.5 a 49-point stop needs a 74-point target — 85% to
120% of the entire session range in one move.

All 7 stop-band suppressions were **above** the 30-point ceiling; none below.
This is why 20% (9 of 44 ranges) is the figure for fills that reach stop level
rather than the 32% a naive read of world A would give — the band blocked 5 of
the 14 before they became trades.

---

## 4. Defects found — these would recur in any rebuild

### 4.1 SMT pool gate tested a tautology *(fixed)*

`f_anyPoolNear()` had no tier filter. Stage 1 registers every confirmed pivot as
a `TIER_TRANSIENT` pool at exactly that pivot's price, earlier in the same
confirmed bar that the SMT test then runs. The proximity test was therefore
matching a pivot against a pool derived from *itself*, at distance exactly zero.
`smtRequireAtPool` gated nothing.

Symptom: SMT firing ~18×/day against an expected 1–3. Corroborating tell: the
strength floor sat at 0.70 because every detection collected the `+0.2` at-pool
bonus, so sub-0.7 values could not exist.

Fix: a separate `smtMinTier` input defaulting to tier ≤ 1. Result 736 → 205.

**Lesson: a gate that reads state written earlier in the same bar can be
self-referential. Check what else writes to the structure you are testing
against.**

### 4.2 The retest trigger was structurally unable to fire *(fixed)*

Stage 3's POI book excludes any zone whose CE has been tagged. Stage 3's state
machine runs earlier in the confirmed bar than stage 6's trigger. So on the exact
bar price first reached a zone's CE, the zone was promoted to `CE_TAGGED` and
dropped from the book **before** the entry logic looked at it. `bestPOI()` then
returned a different zone whose CE price had not reached, and the test was false.

Two rules written in different stages — "a CE tag is the gap's mitigation" and
"the retest is price reaching CE" — were directly contradictory.

Fix: snapshot the POI once per armed setup and test against the snapshot. This
is also the honest model of the trade: a limit rests at a zone's CE and does not
cancel itself because the fill tagged the level it rested on.

### 4.3 The entry window was squeezed to near-zero *(fixed)*

`getLiveSweep()` returned `na` at `confirmBarIdx + sweepValidBars` (12), while
the MSS was allowed `mssMaxBarsAfterSweep` (10) bars to land. The retest window
was whatever remained — as little as 2 bars. `entryRetestBars` was decorative.

Fix: `entryValidBars`, with the sweep record surviving
`max(sweepValidBars, mssMaxBarsAfterSweep + entryValidBars)`. Triggers 3 → 10.

### 4.4 The dealing range extended without bound *(fixed)*

`drHigh` extended on every new high while `drLow` stayed pinned at the swept
extreme, with nothing to stop it short of the 120-bar age limit. Measured widths
were running 1.5–3× the whole session range.

Fix: extension capped at `drMaxExtensionMult` × the width at the MSS bar. The
swept extreme never moves — it is a real price where real liquidity was taken,
and a stop anchored to a drifting level is not a stop.

*Note: this was correct on its own terms but was **not** the cause of the wide
stops. See 5.2.*

### 4.5 Suppression counters read zero because guards sat behind the trigger gate *(fixed)*

Ten of eleven guard rails were evaluated after `ok := fire`, so they counted only
*blocked triggers*. With ~1 trigger in 40 days there was nothing to block, and
every counter read zero while the guards worked correctly.

Fix: a `triggersRaw` denominator. **A suppression counter without a denominator
is uninterpretable** — zero could mean the guard never fired or that nothing ever
reached it.

### 4.6 Breakers were privileged survivors *(fixed)*

The OB state machine stopped running once state became `ST_BREAKER`, so
`mitigated` froze at the flip — and a block flips *by closing through the zone*,
the one branch that never sets `mitigated`. Breakers were the only zone type
that survived contact, which is why `bestPOI` kept returning BREAKER on both
sides at the quality floor.

Fix: breakers are tracked in their inverted polarity and can be mitigated.

### 4.7 `f_poiQuality` was never updated to the agreed weights — **STILL OPEN**

The stage-5 redesign agreed to remove OTE from the POI quality formula, because
it was collinear with the standalone dealing-range location component:

```
agreed:     quality = 0.40 base + 0.35 MSS provenance + 0.25 coincidence
as built:   quality = 0.40 base + 0.25 OTE + 0.20 MSS + 0.15 coincidence
```

**The code still carries the original stage-3 weights.** OTE therefore feeds two
places — `f_poiQuality` (+0.25, ×1.5 = +0.375 points) and `f_locationGrade` (up
to 1.5 points) — which is precisely the double-count the redesign existed to
remove. The stage-5 commit message asserted the new formula; that assertion was
wrong.

**Impact on the findings: negligible.** OTE fires on 6% of POI-bars, so the
double-count reached almost no setups, and the deciding measurement in 3.1 does
not depend on it. It also means the measured ceiling of ~7.9 is correct as
measured — quality caps at 0.40 + 0.20 + 0.15 = 0.75 without OTE, giving
1.5 × 0.75 = 1.125 for the POI component.

**Deliberately not fixed.** The file is evidence for the numbers above and was
frozen when the stop condition was met. Any rebuild must apply the agreed
formula from the start.

**Lesson: a design decision agreed in discussion is not a design decision
implemented in code. Verify the diff, not the commit message.**

---

## 5. Hypotheses raised and refuted

The most reusable part of this document. Each of these was plausible, was acted
on, and was wrong.

### 5.1 "`bestPOI` prefers larger zones because `f_zoneInOte` tests overlap" — **refuted**

`f_zoneInOte` does test interval overlap rather than containment, and `inOte` is
worth 2 in the ranking plus a quality bonus, so a taller zone spanning more price
*should* have been favoured.

Measured: selected zone height **18.5** against a book mean of **20.6**.
`bestPOI` selects *below* the book average. And `inOte` fires on only 6% of
POI-bars, so the overlap test is severely **restrictive**, not permissive.
Tightening it to CE-containment would have driven that to 1–2% and deleted both
the ranking term and the quality bonus — making the model worse.

**Lesson: before concluding a test is too permissive, measure how often it fires
at all.**

### 5.2 "Wide stops are an artefact of POI selection" — **refuted**

The hypothesis: `bestPOI` breaks ties by proximity to close at arm time, when
price sits at the leg extreme, so it would prefer zones near the extreme and
inflate the stop.

Measured: POI anchor **30.9** points, *narrower* than the swept anchor at
**49.1**, with "Wider of the two" selecting swept on 7 of 7. `poiNa` was 0, so a
POI always existed. And `armedWithDR` was 100%, meaning zones ranked on OTE
rather than on proximity — the tie-break concern never applied.

### 5.3 "The 30.9 POI anchor contradicts the 18.5 zone height" — **refuted, no bug**

`dPoi = p.ce − (p.bottom − buf) = (top − bottom)/2 + buf`, so a mean anchor of
30.9 implied ~57-point zones, three times the measured 18.5.

Population-difference explanations were ruled out **by arithmetic before
measuring**: with a 10-sample mean of 18.5 and non-negative heights, the largest
possible mean for any 7-member subset is `18.5 × 10/7 = 26.4`, giving at most
13.2 + buf. It cannot reach 30.9.

Direct identity capture then confirmed `e == ce` and
`55.5/2 + 3.01 = 30.76` exactly. The arithmetic was always honest; the two
figures were drawn from different populations and nothing downstream depended on
the difference.

**Lesson: an identity can be checked directly at the point of computation.
Prefer that over choosing between competing explanations.**

### 5.4 "75% of ranges break the premise" — **refuted as stated**

33 of 44 ranges died by a close back through the swept extreme. But the
retracement update was running **on the death bar itself**, and a long range dies
when `close < drLow`, which forces `(drHigh − low)/width > 1.0` by construction.
Every premise failure landed in the top retracement bucket automatically. The
observed "38 of 44 retraced beyond 0.79", with a mean deepest retracement of 1.1,
was measuring deaths, not retracements.

Separately, `drMaxAgeBars` is 120 bars while the entry window is ~25, so a range
that outlived its whole tradeable life and broke four hours later was counted
identically to one that broke on bar 6.

After excluding the death bar and conditioning on lifetime: **21** breaks inside
the entry window, not 33. And of those 21, only 14 had a fill first. The premise
fails on **20%** of ranges in a way that could cost a trade — not 75%.

**Lesson: a measurement taken on the bar a condition fires will encode that
condition. Bank the value from the bar before.**

### 5.5 Prediction accuracy

Trigger-count predictions were wrong repeatedly and in the same direction:
20–50 against an actual of 3; then 15–40 against an actual of 10. Structural
predictions (the stop band would cut world A; the POI anchor would not move when
the range was capped) were right. **Reasoning about mechanism was reliable;
reasoning about frequency was not.**

---

## 6. What would change the answer

### 6.1 Sample size

**21 break-in-window ranges is what killed this, and it is the binding
constraint on any re-test.**

The deciding test is a two-sample comparison of peak score between world A
(n=14) and world B (n=7). With the observed spread — B ranging across roughly 8
points — detecting a 0.9-point difference at conventional power needs on the
order of **100–150 samples per group**. At the observed 2:1 A:B ratio and 21
break-in-window ranges per 44 dealing ranges, that implies **roughly 600–900
dealing ranges**, or **1.5–2 years** of 5m data at the observed 1.1 ranges/day.

*This is an order-of-magnitude estimate from the observed spread, not a formal
power calculation.*

A separate question — where to place the retracement band — needs a **quantile**
estimate rather than a mean comparison. At n=44 the standard error on a tail
quantile is roughly ±0.07–0.10 in fraction terms, half the width of the current
band. That needs **150–200 ranges**, or **6–9 months**.

### 6.2 Preconditions that matter more than N

- **Split-half stability.** Split the history and confirm the modal bucket and
  median agree across halves. If they do not, pooling more data averages two
  regimes into a conclusion that fits neither. This is checkable at any N and is
  the cheapest test available.
- **Pre-register the decision rule.** Write down what shape justifies what
  change *before* looking. Done here, and it is why the stop was clean rather
  than a negotiation.
- **Regime coverage.** 40 days is one volatility regime. Overnight MNQ behaves
  differently in trending versus rotational conditions.

### 6.3 What a re-test would have to fix first

1. Apply the agreed `f_poiQuality` weights (4.7) so OTE is not double-counted.
2. Pick one price series — close or wick — and use it in both `inOTE()` and the
   entry trigger (3.2).
3. Resolve the stop geometry before measuring anything else. A 49-point
   structural stop against a 60–85 point session range is not viable at 1:1.5,
   and no scoring change addresses it. Either the entry sits closer to the swept
   extreme, or the stop anchors on the POI far edge, or these sessions do not
   support this model.

### 6.4 What would *not* change the answer

Re-weighting components, moving the threshold, or moving the OTE band. Finding
3.1 is that the score does not separate outcomes; adjusting the score's internals
until separation appears on the same 21 samples is fitting, not measuring.

---

## Appendix: reading the indicator's diagnostic table

`compactTable` is on by default. Rows are grouped: session context, the
sweep:breakout ratio with the armed-setup total, the score histogram,
suppression counters with their `trig` denominator, last signal, armed state,
then the temporary investigation rows.

Every counter is `var`-declared and there is no `varip` in the file, so all of
them reset cleanly on any input change or recompile. A reload always measures
the current configuration and never carries history from a previous one.
