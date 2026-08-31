# Design Decisions — Reversal Engine

Running log. Append, don't rewrite. Each entry records what was chosen, what it
was chosen *over*, and what would make it wrong — the last field matters most,
because it is what lets a future decision reverse this one honestly.

Status values: **Accepted** · **Provisional** (working default, expected to be
revisited) · **Superseded by D-xxx** · **Rejected**.

---

## D-001 — Volume profile sourcing: hybrid
**Status:** Accepted · 2026-08-29

Current and prior session profiles are built from intrabar data
(`request.security_lower_tf`, default 1m). Sessions older than the prior one are
profiled from chart bars, distributing each bar's volume across its own high–low
range.

**Over:** (a) intrabar for everything — highest fidelity, but the ~100k intrabar
cap is consumed within a few days of history, and the failure is silent
degradation of old data rather than an error; (b) chart bars for everything —
free and cap-immune, but the developing POC becomes an estimate of an estimate,
which is the one profile value the engine leans on most.

**Consequence that must be respected downstream:** naked POCs found in older
sessions are *lower resolution* than the current POC. They are not interchangeable
inputs. M3 must carry the resolution class alongside each level and must not let a
chart-bar-derived POC score as tightly as an intrabar-derived one.

**Wrong if:** intrabar history turns out to reach far enough back on the target
plan that full-resolution history fits inside the cap, or the naked-POC concept is
dropped and only the current/prior sessions matter — either would collapse this
back to a single sourcing path.

---

## D-002 — Composite weighting: off = excluded, inactive = 0.0
**Status:** Accepted · 2026-08-29 · **refined by D-039 — an unimplemented module is OFF, not inactive**

A module toggled **off** is removed from both numerator and denominator. A module
that is **on but not active at this bar** contributes 0.0 while its weight stays
in the denominator.

**Over:** (a) renormalizing over active modules only — keeps the composite
comparable, but lets one active module produce an A grade, which is the opposite
of confluence; (b) treating off and inactive identically as 0.0 — punishes you for
disabling a module whose data you cannot source, so a user on a plan without
seconds data would see every grade drop for a reason unrelated to the market.

**Rationale:** the two states mean different things. Off is *"not measured"*.
Inactive is *"measured, nothing there"* — real evidence against the setup, and it
should cost score.

**Consequence:** grades are comparable across bars for a given configuration, but
**not** comparable between two different toggle configurations. Any future
performance record must record the toggle state alongside the grade.

**Wrong if:** module `active` flags turn out to be sparse enough that a typical
good setup only ever has 2–3 modules active, which would make the denominator
dominated by permanently-idle weights and push every composite toward zero.
Watch this during first implementation; the `minActive` floor is the tell.

---

## D-003 — Confluence floor: minimum active modules
**Status:** Superseded by D-014 · 2026-08-29

Default 3. Below this count the composite is suppressed to no-grade regardless of
its value.

**Rationale:** a direct consequence of D-002. Under that contract a high composite
with one active module is arithmetically possible when the other enabled weights
are small. The floor makes "confluence" structural rather than a hoped-for
property of the weights.

**Provisional because:** 3 of 7 is a guess. It should be set from the observed
distribution of active-module counts once modules are real, not before.

---

## D-004 — Context filters act as a grade cap, not a veto
**Status:** Accepted · 2026-08-29

Hostile context (weak internals for NQ, adverse DXY/yields for GC) caps the
published grade at B by default. Context *also* contributes an ordinary weighted
sub-score. The cap is configurable, and setting it to "None" restores hard-veto
behavior.

**Over:** (a) hard veto — cleanest for automation, but it destroys the record of
what the gate rejected, so the gate can never be evaluated; (b) advisory only —
uniform and simple, but then it is not a gate and the "context filters as a gate"
requirement is unmet.

**Rationale:** the setup stays visible and reviewable. A gate you cannot audit is
a gate you cannot tune, and this one is built on the noisiest data in the system.

**Consequence:** context has two distinct channels — a sub-score and a hostile
flag. They must be computed independently; letting the cap fall out of a sub-score
threshold would collapse them back into one signal wearing two hats.

**Wrong if:** review shows capped-to-B setups perform indistinguishably from
uncapped B setups, meaning the cap is adding a grade level with no information in
it.

---

## D-005 — Timeframe-agnostic across 1m / 5m / 15m
**Status:** Accepted · 2026-08-29

No input is expressed in bars. Every lookback is in **minutes**, converted at
runtime by `f_bars()` using `timeframe.in_seconds()`.

**Over:** picking 5m and hardcoding bar counts (matches the existing MGC script,
but every count silently means something different if the chart is changed).

**Consequence:** two things do not survive the conversion and need explicit
handling — (1) M4's intrabar timeframe must be strictly lower than the chart TF,
so on a 1m chart it needs seconds data and self-disables when unavailable
(see PINE_LIMITS §5); (2) proximity thresholds are in **ticks**, not points or
percent, so they carry across NQ (0.25) and GC (0.10) without a per-instrument
table.

---

## D-006 — Micros as aliases, not separate profiles
**Status:** Accepted · 2026-08-29

MNQ resolves to the NQ profile and MGC to the GC profile, with identical settings.
Detection is substring matching on `syminfo.root`, with the micro tested first for
display naming only ("MNQ" contains "NQ").

**Rationale:** micros trade at the same price and the same tick size as the
full-size contract. Only the dollar multiplier differs, and this indicator does not
price risk in dollars.

**Wrong if:** dollar-denominated risk sizing is added later — at that point the
multiplier becomes load-bearing and the alias needs its own field.

**Note:** tick size is read from `syminfo.mintick` rather than hardcoded per
family, so a wrong family detection degrades session times, not tick arithmetic.

---

## D-007 — GC "RTH" means the COMEX pit window
**Status:** Provisional · 2026-08-29

GC structural levels are computed against **08:20–13:30 ET**, not the 23-hour
Globex session. NQ uses 09:30–16:00 ET.

**Rationale:** gold's conventional daily levels are quoted against the pit
equivalent, and a 23-hour "session" makes PDH/PDL/IB/opening-range nearly
meaningless.

**Provisional because:** this is a convention choice, and a gold trader who
frames the day around the London fix or the 18:00 Globex open would want
different anchors. Exposed as an input for exactly that reason.

---

## D-008 — Every `request.*` call goes through a wrapper
**Status:** Accepted · 2026-08-29

`request.security` and `request.security_lower_tf` are never called directly.
`f_sec()` hardcodes `lookahead = barmerge.lookahead_off`.
`request.security_lower_tf()` accepts no `lookahead` argument — it returns
intrabars of the current chart bar and cannot look ahead — so `f_secLTF()` earns
its place differently: it centralizes call-site auditing and the
"lower TF must be strictly lower than chart TF" guard (`f_ltfValid`) that M3 and
M4 both need in order to self-disable rather than return empty data.

**Rationale:** the no-repaint requirement is enforced by construction rather than
by review discipline. It also makes every external data dependency greppable in
one place, which is what keeps the ~40-call budget auditable.

**Standing rule:** a new `request.*` call site requires (1) the wrapper, (2) a
line in the header budget table in `src/reversal_engine.pine`, and (3) an entry
in this file. All three, or the call does not get merged.

---

## D-009 — Grade published, raw composite hidden
**Status:** Accepted · 2026-08-29

The user-facing output is A/B/C. The raw 0..1 composite is available only behind a
"development only" toggle, defaulting off, and via the Data Window.

**Rationale:** a visible number invites treating 0.71 and 0.69 as different when
they are inside the noise of seven approximated sub-scores. The three-tier grade
is an honest statement of the resolution the inputs actually support.

**Consequence:** grade thresholds become the tuning surface, and they are inputs.
The temptation to tune thresholds per session or per instrument should be resisted
until there is a record to tune against.

---

## D-010 — Evaluation and rendering strictly separated
**Status:** Accepted · 2026-08-29

`overlay = true` for now, but nothing above the RENDER section draws, and nothing
in RENDER computes.

**Rationale:** the stated goal of moving heavy internals to a companion pane
later. Pine has no cross-script state (PINE_LIMITS §9), so a companion pane means
duplicating evaluation into a second script or factoring it into a library. Either
path is only cheap if the seam already exists.

---

## D-011 — Modules ship as stubs returning `active = false`
**Status:** Accepted · 2026-08-29

All seven modules return `ModuleOut(0.0, false)` until implemented.

**Rationale:** a stub returning `active = true` with score 0.5 would make the
composite look plausible while measuring nothing. Under D-002 an inactive module
correctly contributes 0.0 and holds its weight, so the scaffold's composite is
honestly 0.0 and no setup can grade.

**Standing rule for implementation:** a module that cannot source its data returns
`active = false`. It must never return a neutral score, because the composite
cannot distinguish a real 0.5 from a fabricated one.

---

## D-012 — The engine is a screener, not a trigger
**Status:** Accepted · 2026-08-29

The published grade covers four of the source framework's five evidence
categories: Location, Extension, Liquidity event, Context. **Category F
(order-flow failure) is handed off to a footprint/DOM platform.** This is stated
in the file header, in `SPEC.md` §1.1, and should appear in any UI the engine
ever renders.

**Why this is a decision and not just a limitation:** the research is explicit
that location without order-flow confirmation is half a framework. Pine cannot
supply absorption, stacked imbalance, unfinished auctions, or trapped-trader
reads — no Level 2, no DOM, no bid/ask classification, no MBO. The only F input
available is M4's tick-rule proxy, which the same research flags as a frequent
"real divergence, no reversal" trap.

**Over:** (a) pretending M4 satisfies category F and shipping a "complete"
checklist — this is the tempting option and it is dishonest, because it would let
an A grade publish with no order-flow evidence at all; (b) dropping category F
from the framework — which quietly redefines the strategy into something the
research does not support.

**Consequence:** `requireOF` exists but defaults **off**, because turning it on
gates every setup on the weakest module in the engine. The correct workflow is
`SPEC.md` §7: screen here, confirm on a footprint platform, execute on the micro.

**Wrong if:** the plan tier gains real footprint access (`request.footprint()` or
equivalent). At that point M4 is **re-specified**, not re-tuned, and this decision
is revisited — an approximation and the real measurement are different things, not
the same thing at different quality.

---

## D-013 — Volume sourced from the chart symbol, not the full-size contract
**Status:** Accepted · 2026-08-29 · *rationale corrected 2026-08-29*

`useFullSizeVol` defaults **off**. Volume-derived modules (M3, M4, M5) read the
chart symbol.

**Rationale (corrected).** An earlier version of this entry argued the default
from *contract count* — MNQ ~1.6M ADV vs NQ ~500k — and concluded the micro was
not the thinner series. **That comparison was invalid.** Contract count is not the
unit a volume-at-price distribution is built in; notional is. NQ is $20/point
against MNQ's $2/point, so:

| | full-size | micro | full-size advantage |
|---|---|---|---|
| NQ / MNQ | ~500k × $20/pt = ~$10M/pt | ~1.6M × $2/pt = ~$3.2M/pt | **~3×** |
| GC / MGC | ~270k × 100oz = ~27M oz | ~301k × 10oz = ~3.0M oz | **~9×** |

The full-size contract **is** the heavier volume-at-price series in both families,
by a wide margin. The research's "read full-size" recommendation is correct for
bar volume as well as for depth — the earlier entry had the direction of the
argument backwards.

**So why is the default still off?** Because the intended workflow charts NQ and
GC directly, where the toggle is a no-op that costs up to 2 `request.*` calls. The
default follows the workflow, not a claim about which series is better.

**Consequence:** the toggle's tooltip now states the notional ratios and tells you
to turn it **on** when charting MNQ/MGC. This is the opposite of the guidance the
previous rationale implied.

**Wrong if:** micro and full-size distributions turn out to differ in *shape*
rather than scale (a genuinely different participant mix), in which case the
choice becomes a modelling decision rather than a resolution question. The test
is unchanged: build the session profile both ways on the same day and compare POC
and VAH/VAL placement.

---

## D-014 — Confluence floor counts CATEGORIES, not modules
**Status:** Accepted · 2026-08-29 · supersedes D-003 · extended by D-019 (composition) and D-020 (damping)

The floor requires ≥3 **distinct evidence categories** (Location / Extension /
Order-flow / Liquidity / Context), default 3, matching the source checklist.

**Over:** D-003's minimum-active-module count, which was a guess and, worse, was
the wrong unit. M2 (structural levels) and M3 (volume profile) are both Location.
Under a module count they read as two independent confirmations; they are one.
The same is true of M1 and M5, both Extension.

**Rationale:** this is the structural answer to the collinearity problem raised in
the original spec's open questions. A sweep of a level (Q), proximity to that
level (L), and a POC sitting at that level (L) are largely *one observation*
scored three times. Counting categories caps how much a single observation can
pay out.

**Consequence:** the category assignment is now load-bearing and must be reviewed
whenever a module is added. Getting a category wrong is worse than getting a
weight wrong — a weight is a dial, a category is a structural claim about
independence.

**Wrong if:** the categories turn out not to be independent either. Location and
Extension co-occur by construction (an extended price is usually extended
*relative to a level*). If the observed category-hit correlation is high, the
floor needs to name *which* three, not just count them (`SPEC.md` §5 Q2).

---

## D-015 — An opposing module contributes 0.0 and keeps its weight
**Status:** Accepted · 2026-08-29

When evaluating the long side, a module with `dir = -1` contributes 0.0 to the
numerator but its weight stays in the denominator.

**Over:** (a) excluding opposing modules from the denominator, which would let a
setup score well *because* half the evidence pointed the other way; (b) letting
them contribute negatively, which puts the composite outside 0..1 and breaks the
grade thresholds.

**Rationale:** evidence for a low is not neutral when you are grading a high.

**Consequence:** both sides are evaluated every bar, and both qualifying is
treated as **CONFLICT → suppress**, not as "pick the bigger number". Incoherent
evidence is a reason to stand down.

---

## D-016 — Poor highs / poor lows score AGAINST the fade
**Status:** Accepted · 2026-08-29

A flat extreme across two or more TPO brackets with no excess tail is an
*unfinished auction*. Such extremes typically get revisited **and exceeded**, so
M3 must **reduce** the score for fading them.

**Recorded as a decision because the intuitive implementation is backwards.** A
naive reading treats any prominent extreme as a reversal candidate; a poor high is
prominent *and* is evidence the auction is not finished there. Getting the sign
wrong here does not merely weaken the engine — it biases it toward the setups most
likely to fail, while looking like it is working.

Corollary: excess tails and single prints are the *opposite* structure — genuine
rejection — and score positively.

---

## D-017 — Detect and flag back-adjusted continuous contracts
**Status:** Accepted · 2026-08-29

A ticker containing `1!` / `2!` is flagged in the status table.

**Rationale:** back-adjusted continuous series shift every historical price at each
roll, so absolute horizontal levels drawn on them are unreliable — which is
precisely what M2 and M3 produce. Continuous series are fine for trend context and
wrong for level work.

**Not enforced, only flagged:** forcing the front month would break the ability to
view history at all. Roll timing for reference — NQ/MNQ roll ~8 trading days before
the third-Friday expiry; GC/MGC roll ~5–7 business days before First Notice Day,
with December carrying the highest open interest.

---

## D-018 — GEX, gamma regime, and catalyst stand-down are manual; COT is off
**Status:** Accepted · 2026-08-29

Three inputs the research treats as first-class have no automatic path in Pine and
are exposed as manual controls, defaulting off/unknown:

- **GEX walls and gamma flip** — Pine has no options chain, OI, or IV surface, and
  no way to fetch any. Three `input.float` fields, 0.0 = unused.
- **Gamma regime** — a three-way manual selector. **"Unknown" must not be treated
  as favorable**, because the research's rule is asymmetric: fade only in positive
  gamma, never in negative. An unknown regime is not a permissive one.
- **Catalyst stand-down (FOMC/CPI/NFP/PPI)** — Pine has no economic event
  calendar. A manual toggle plus a blackout window is the whole mechanism.

**COT** is scaffolded but defaults **off**: TradingView exposes CFTC series, but
whether the specific series resolve through `request.security` in this context is
**unverified**, and an unverified data source that silently returns `na` is worse
than an absent one. The module must self-disable if the series does not resolve.

**Consequence:** all four are honest holes rather than approximations. Where an
approximation was possible (delta) it was built and labeled; where it is not
(gamma), no proxy is invented. Inventing a "gamma proxy" from price behavior would
be the same error as D-016 — a plausible-looking number with no measurement behind
it.

---

## D-019 — Category composition is enforced, only the count is configurable
**Status:** Accepted · 2026-08-29 · extends D-014

A grade requires **all three** of:

1. **Location present** — mandatory, no exceptions.
2. **At least one of {Liquidity, Order-flow}** — something must have *happened*.
3. **Total distinct categories ≥ `minCats`** — configurable, default 3.

`requireOF` narrows rule 2 from `{Q or F}` to `F` only. Off by default (D-012).

**Over:** D-014's bare count of ≥3. A count treats all category triples as
equivalent, and they are not. `{Location, Extension, Context}` satisfies a count of
three while describing a market that is merely *extended near a level in a
supportive regime* — a description that fits every band-walk on every trend day.
No event has occurred. That is a watch, not a setup.

**Rationale:** the two mandatory rules encode the framework's actual structure.
Location is where the whole thesis lives — without it there is no level to fail at,
and Extension alone is just "price moved a lot". Rule 2 is the *failure* evidence:
a sweep that reversed (Q) or aggression that stopped working (F). Location plus an
event is the irreducible core; the third category is corroboration.

**Consequence:** Extension and Context can now never be two of the three on their
own — they are corroborating categories by construction. This makes M1 and M5
(both E) and M7 (C) structurally incapable of producing a setup without M2/M3 and
M6/M4, which is the intended reading of the source framework.

**Consequence for the F category:** with `requireOF` off, **M6 (sweep and reclaim)
carries rule 2 alone in practice**, since M4 is the approximation. M6's quality
therefore gates the whole engine far more than its weight of 1.0 suggests. It
should be among the first modules built and the most carefully tested.

**Wrong if:** the observed hit rate for rule 2 is so low that almost nothing ever
grades — which would mean the sweep definition (4–40 ticks, 10-minute reclaim) is
too narrow rather than that the rule is wrong.

---

## D-020 — Within-category damping for the second and subsequent modules
**Status:** Accepted · 2026-08-29 · extends D-014

The second and subsequent **enabled** modules in a category contribute at
`catDamp` (default 0.5), applied to **both numerator and denominator**.

**The problem it fixes.** D-014's category floor stopped collinear modules from
*unlocking* a grade, but they could still *inflate the score*. M2 and M3 are both
Location: a POC sitting at prior-day high is largely one observation, and under
flat weighting it paid out twice into the composite. The gate was fixed; the score
was not.

**Why the denominator is damped too.** If only the numerator were damped, a second
agreeing module could *lower* the composite — it would add at most `damp × score ×
w` to the numerator while occupying a full `w` in the denominator. Confirming
evidence must never reduce a grade. Damping both keeps the composite a true
fraction of *available* evidence and preserves 1.0 as reachable.

**Precedence is declared push order, not score.** Currently: M1 primary Extension
(M5 secondary), M2 primary Location (M3 secondary). Each of F, Q and C has one
member, so damping is inert there today.

**Over:** ranking by contribution so the strongest module in a category takes full
weight. Rejected because it makes the **denominator score-dependent** — the same
evidence would yield different composites depending on which module happened to
score higher — and it leaves an idle module's weight undefined, breaking D-002.
Declared order is stable, auditable, and independent of the bar.

**Consequence:** the push order in the evaluation section is now load-bearing and
must be reviewed whenever a module is added or re-categorized. It is a design
statement ("structural levels are the primary location evidence"), not an
accident of code layout. `catDamp = 1.0` disables damping.

**Wrong if:** M3 turns out to be the stronger Location signal, in which case the
push order should swap rather than the mechanism change.

---

## D-021 — Overnight→intraday reversal is a bounded bias, not a category
**Status:** Accepted · 2026-08-29

Extracted from M7 into its own module **M8**, with its own input group and its own
status-table line — but it does **not** occupy a confluence category, cannot help
satisfy the gate, and applies only a bounded additive adjustment to the composite
of the already-resolved side. Cap is an input, default **0.05**.

**Why extract it.** It is the best-evidenced item in the entire source research —
close-to-open predicting open-to-close negatively, documented across four asset
classes including index futures. Burying it inside M7, the noisiest module,
alongside internals and regime meant its contribution could never be observed or
falsified separately. It now has an ID and a debug line.

**Why not a category.** It is a **daily-horizon prior**, not a bar-level
observation. The other seven modules answer "what is true at this bar"; M8 answers
"which way was today already leaning before this bar existed". Letting it satisfy
a confluence slot would let a statistical prior stand in for evidence that
something happened — precisely the substitution D-019 exists to prevent.

**Why capped.** At 0.05 the prior can move a setup across at most one grade
boundary and cannot manufacture a grade from nothing: `side` is resolved by the
gate before the bias is applied, so a bar with no qualifying side gets no
adjustment regardless of how strong the prior is. Evidence decides *whether*;
the prior only nudges *how good*.

**Consequence:** M8's weight is not in the weights group, because it does not have
one. Its influence is the cap, and nothing else.

**Wrong if:** measurement shows the prior is strong enough that 0.05 is
underweighting real information — in which case raise the cap, but keep it a cap.
Promoting it to a category would still be wrong for the reason above.

---

## D-022 — A shared level registry, built from chart bars, not a daily request
**Status:** Accepted · 2026-08-29

Levels (PDH/PDL/PDC, ONH/ONL, IB, opening range, RTH open, prior swings, round
numbers) are computed once in a **shared registry section** and consumed by M6
today, with M2, M3 and M4 to follow. Their toggles moved from the M2 group into a
new `L0 - Level registry (shared)` group.

**Built from chart bars, not `request.security(…, "D", …)`.** A daily request
returns the exchange's daily bar, which for GC is the **23-hour Globex session** —
not the 08:20–13:30 pit window D-007 specifies. Deriving the levels from intraday
bars using the session inputs is both correct for gold and free: **zero
`request.*` calls**, where the original budget had allocated 3.

**Over:** building levels privately inside M6. M2 would then have re-derived the
same values from the same bars, and the two definitions would drift the first time
one was tuned. M6 is simply the first consumer.

**Publication timing is part of the contract.** PDH/PDL/PDC publish at RTH session
**end**, not at the next session's open. Rolling at the open would leave them
pointing at the session-before-last for the entire overnight — precisely the window
in which M6 is sweeping them. ONH/ONL publish at overnight end, for the same
reason. This was a real defect caught in review, not a hypothetical.

**Consequence:** all registry state advances only on confirmed bars, so a forming
realtime bar cannot move a published level and then take it back.

---

## D-023 — Sweep penetration bands are ATR fractions, not ticks
**Status:** Accepted · 2026-08-29 · supersedes the tick-based M6 inputs

`sweepMinTicks` / `sweepMaxTicks` are replaced by `sweepMinAtr` (default 0.10) and
`sweepMaxAtr` (default 0.50), multiplied by a selectable ATR reference.

**Rationale.** NQ runs roughly 1200–1600 ticks of daily range against GC's
300–600. A fixed 4–40 tick window therefore described two categorically different
events: on NQ a marginal poke, on GC a substantial excursion. Ticks normalize the
*price increment* across instruments (D-005) but not the *volatility*, and a sweep
is a volatility-scaled event.

**`sweepAtrRef` is a genuine fork, exposed rather than decided:**
- **Chart TF** (default) self-normalizes to the resolution being traded — a sweep
  on 15m is a bigger event than on 5m, and the bands scale with it. But it means
  the same fraction is a different absolute distance on each timeframe, which sits
  in tension with D-005's "same wall-clock meaning across timeframes".
- **Daily** is timeframe-invariant and normalizes only across instruments, at the
  cost of one `request.*` call and of ignoring the chart's own resolution.

The tension is real and not resolvable from first principles, so **the resolved
tick equivalents are published in the status table**. "0.10 ATR" means nothing
until you can see it resolve to a tick count on the chart in front of you; the
readout is what makes this decision falsifiable rather than a preference.

**The reclaim window stays minutes-based** per D-005 — it is a duration, not a
distance, and durations were never the problem. The resolved bar count is
displayed and **warns below 2 bars**: at 1 bar the reclaim must land on the very
next bar, which is a materially different and much rarer event than the
input's wording implies. It warns rather than self-disabling, as specified.

**Chart TF confirmed as the default** (2026-08-29), and the earlier framing of the
tension was wrong. D-005's invariance governs **lookback semantics** — how far back
"50 minutes" reaches — not **event magnitude**. Those are different things, and
this entry originally conflated them.

A sweep is a *scale-dependent event*: it is an excursion at the resolution being
watched. A 15m chart correctly should not fire on an excursion only visible at 1m,
and Daily ATR would make the same absolute distance count as a sweep on a 1m chart
where it is noise. Chart-TF ATR is not a compromise against D-005 — it is the
correct measure for a magnitude that is *supposed* to scale with resolution. The
Daily option stays for cross-instrument comparison and diagnostics.

**Wrong if:** the tick readouts show chart-TF producing absurd numbers somewhere
in the 1m/5m/15m set — but note that "absurd" now means absurd *relative to what a
sweep means on that timeframe*, not absurd relative to the 5m numbers.

---

## D-024 — M6 ships with its own fire-rate instrumentation
**Status:** Accepted · 2026-08-29

M6 carries a penetration funnel and a per-session fire counter, surfaced in the
status table: penetrations seen → within the max band → reclaimed and fired, plus
fires per session and a session count.

**Why it is in the script rather than in a report.** The fire rate cannot be
computed anywhere except on a chart with data — there is no way to derive it from
the source material, and asserting a number without running it would be
fabrication. Building the counter is the only honest way to deliver the
measurement.

**Why the funnel and not just the count.** A fire rate of zero has at least three
distinct causes with three different fixes: nothing penetrates (`sweepMinAtr` too
high), everything over-penetrates (`sweepMaxAtr` too low), or nothing reclaims in
time (`reclaimMin` too short). A bare count cannot distinguish them; the funnel
can, at a glance.

**This is the gating measurement for the whole engine.** Per D-019, M6 carries
gate rule 2 alone while `requireOF` is off. If its fire rate is near zero, no
setup can ever grade regardless of how well M1–M5 are built — so this number
decides whether the sweep definition is usable before any further module work.

**Consequence:** counters are cumulative over the loaded history and reset only on
recompile. `m6Sessions` counts RTH opens seen, so the average is over whatever
history the chart holds — read the session count alongside the rate.

---

## D-025 — M6 fires are held for a decaying window, not a single bar
**Status:** Accepted · 2026-08-29

After a confirmed reclaim, M6 stays `active` for `sweepHoldMin` (default 15
minutes) with the score decaying linearly.

**Rationale.** Without a hold window M6 is live on exactly one bar. The confluence
gate requires Location **and** an event **and** a third category to be true on the
*same* bar — and the other modules confirm at different speeds (M1's band-walk
guard, M3's TPO brackets, M4's divergence lookback). A one-bar M6 would almost
never coincide with them, and since M6 carries gate rule 2 alone (D-019), the
engine would grade approximately nothing for a reason that has nothing to do with
the market.

**Decay rather than a flat hold:** the evidence genuinely goes stale. A reclaim
twelve minutes ago is weaker support for a reversal *now* than one that just
happened, and a flat hold would misrepresent that.

**Wrong if:** the hold turns out to be what makes setups grade — i.e. the same
sweep keeps paying out across many bars and inflates the fire-to-grade ratio.
Watch for grades clustering immediately after a single sweep. The fix would be a
one-grade-per-sweep debounce, not a shorter hold.

---

## D-026 — M6 contribution age is logged at grade onset
**Status:** Accepted · 2026-08-29

Every grade records the age, in bars, of the M6 sweep contributing to it. Surfaced
on the grade label, in a status-table freshness histogram (fresh / mid / stale
against the hold window), and in the Data Window.

**Why.** The hold window (D-025) is the parameter most likely to **manufacture
confluence**. Keep M6 warm for long enough and it will eventually overlap with
something, the categories fill, and a grade appears — not because a setup formed
but because a timer had not expired. The hold is defensible on its own terms and
still capable of producing exactly this artefact.

The failure is invisible without instrumentation: a grade carried by a 12-minute-old
sweep and a grade carried by a 1-bar-old sweep look identical in the output. If
A-grades cluster in the stale bucket, the window is too generous and the engine is
grading its own memory.

**Counted at grade ONSET only.** A grade persisting across bars is one setup, not N
of them; per-bar counting would make every long-lived grade look like a cluster.

**Buckets** are thirds of `holdBars`, so they rescale automatically with the hold
window and the chart timeframe rather than encoding a bar count.

**`gradesNoM6`** counts grades where M6 did not contribute to the graded side at
all. While `requireOF` is off and M4 is a stub, this should be **zero** — M6 carries
gate rule 2 alone (D-019). A non-zero count means either M4 went live or something
is filling category Q unexpectedly, and it is worth investigating rather than
assuming.

**Wrong if:** onset-only counting hides a real pattern — e.g. grades that upgrade
C→A several bars in, where the interesting age is the age at *upgrade*, not at
onset. If that shows up, count transitions rather than onsets.

---

## D-027 — M2/M6 cross-category collinearity: damp proximity, not stacking
**Status:** Accepted · 2026-08-29

When M6 has an active sweep on the level M2 is scoring, **M2's proximity term is
damped by `structSweptDamp` (default 0.3). Its stacking term is untouched.**
Mediated by a `lvlSwept` array in the shared registry: M6 writes it, M2 reads it,
neither touches the other's variables.

**The diagnosis.** The dependency is asymmetric and mechanical, not a vague
overlap: a reclaim *is* a close back through the level, so

> P(M2 proximity-active | M6 fired on level L) ≈ 1

at the fire bar. The converse does not hold — M2 active without M6 is informative
(price approaching an untested level). Conditional on M6 firing, M2's proximity
adds approximately nothing.

**But only proximity is redundant.** M2's score has two terms answering different
questions:

| Term | Given M6 fired on L | |
|---|---|---|
| Proximity — is price at a level *now* | Forced at the fire bar | **redundant** |
| Stacking — how many distinct classes agree at that price | M6's score is speed × depth and knows nothing about level quality | **independent** |

So stacking takes full credit always, and the two terms are scored, logged and
displayed separately for exactly this reason.

**Why suppression was rejected** (both originally-proposed options — M2 skips swept
levels, or the sweep consumes the level):

1. **M2 is the antidote to a stale M6.** Proximity is forced at the fire bar but
   *not* at bar 10 of the hold window. By then price may have left the level, and
   M2 going quiet is the **only** signal in the engine that a warm M6 is stale.
   Suppressing M2 on the swept level would delete the one check on D-025's hold —
   the very failure mode D-026 exists to measure.
2. **It would empty a mandatory category.** Location is required by D-019. On a
   lone-level sweep — sweep of PDH with nothing else nearby, the most common
   reversal setup there is — suppression leaves Location empty and the setup could
   never grade.

**The active gate does the antidote work structurally**, not the weight: outside
the proximity window M2 is `active = false` regardless of stacking. So price
leaving the level collapses M2 no matter how the blend is set.

**Consequence.** Under D-002 the semantics land correctly: on a lone swept level M2
is *active with a low score* — "measured, nothing further there." Location fills,
the gate passes, the composite is not inflated. A sweep of PDH+ONH+POC stacked
still outscores a sweep of a lone PDH, which is the intended ordering.

**Cost:** M2's score is now conditionally defined and cannot be read in isolation;
one input; one registry array; and a fixed cross-category special case that needs
revisiting if a second category-Q module ever exists.

**Open: fixed vs age-dependent damping.** Age-dependent is more principled —
redundancy is highest at age 0 and gone by hold expiry. But with comparable
weights it *flattens the composite across age* (M6 high + M2 damped ≈ M6 decayed +
M2 full), which would destroy the engine's ability to distinguish fresh sweeps
from stale ones. Fixed damping ships; the D-026 age histogram decides.

---

## D-028 — OPEN: M1/M6 collinearity and the within-E split
**Status:** Open · 2026-08-29 · **do not implement without data**

**The problem.** The collinearity does not stop at M2/M6. Sweeps happen at session
extremes; session extremes are where VWAP extension is largest. So M1 (category E)
is also correlated with M6, and a sweep of PDH at 2σ fills **L + Q + E from
arguably one event** — which satisfies D-019's gate completely.

### Candidate 1 — restrict the third category to {F, C} · **held, likely wrong**

Tighten D-019 so the third category must come from Order-flow or Context, the two
plausibly independent of the level interaction.

**Objection (raised in review, and it holds):** this routes the requirement into
*the module Pine cannot build* (F is M4's tick-rule approximation, D-012) and *the
one that is a gate rather than evidence* (C is M7, which already caps grades under
D-004). That is a redirection into weakness, not a tightening — it would make the
engine's third leg depend on its least trustworthy input while appearing more
rigorous.

### Candidate 2 — split within E, mirroring D-027 · **preferred**

M1's VWAP distance is level-correlated at a swept extreme. **M5's ADR exhaustion
is not:** whether the session has run 1.3× its average range is a property of the
whole session, independent of which level just got swept. If that holds, damp the
correlated term rather than restricting the category — exactly the D-027 pattern
one level up.

**Caveat to test, not assume.** M5 is not perfectly independent either. A sweep
that prints a new session extreme *extends the session range*, and sweeps of
extreme-type levels (PDH/ONH/IBH) plausibly cluster in already-extended sessions.
That is a selection correlation rather than a mechanical one, and much weaker than
M1's — but "much weaker" is a claim requiring measurement.

**A structural difference from D-027 worth noting:** M1's redundancy is not with
the *level identity* but with *being at a session extreme*. So the `lvlSwept` flag
that mediates D-027 does not directly serve this; the registry would need to expose
level **class** (extreme-type vs interior-type), and M1 would damp when an active
sweep sits on an extreme-type level.

### What data settles it

1. **Implement M1 and M5 with per-term sub-score logging**, as M2 now has.
2. **Conditional distribution test.** Compare each module's sub-score distribution
   when M6 is active on an extreme-type level against when M6 is idle. If M1's
   distribution shifts materially and M5's does not, Candidate 2 is correct and the
   damping goes on M1 alone.
3. **Grade attribution.** Of graded setups whose third category is E, record which
   module supplied it. If E is nearly always M1 *and* nearly always coincident with
   M6, the collinearity is confirmed and load-bearing.
4. **Correlate M1's score against `m2ProxRaw`** (already logged). A high
   correlation independent of M6 would mean the problem is broader than the sweep
   case and belongs in the composite rather than in a module.

Until 1–4 exist there is no basis for choosing, and either change made blind would
double-count or destroy the most common reversal setup in the framework — the same
risk D-027 was written to avoid.

---

## D-029 — M6 diagnostics are per-class, and count events three ways
**Status:** Accepted · 2026-08-29

The M6 funnel is broken out by level class, with distinct penetration *bars*
reported alongside the raw counter, plus repeat fires, intact-test rejections,
pivot churn, and a live dump of the registry contents.

**Why the raw counter was not enough.** `m6PenSeen` increments **per level, per
bar, per direction**. It is a count of level-bar observations, not of events, so
"6249 penetrations" over 41 sessions never meant 6249 things happened. The ratio
arguments built on it survive (numerator and denominator share the basis) but the
magnitude arguments do not. `m6PenBars` counts bars with at least one penetration;
the gap between the two measures the inflation.

**The level dump earns its place.** A reported 42 live levels against a registry
with exactly 14 push sites and non-`var` arrays is unexplainable from the code.
Rather than theorise, the table prints the level names. An instrument that
disagrees with the source is a reason to read the instrument, not to build a
theory on the reading.

---

## D-030 — "Intact" means N bars on one side, not one
**Status:** Accepted · 2026-08-29 · replaces the one-bar test in M6

A level counts as intact for an upside sweep only if **every close in the last
`intactMin` minutes** was below it (mirrored for downside). Default 30 minutes.
Implemented as `ta.highest(close, intactBars)[1] < lv` — computed **once**, outside
the level loop, since the extreme close does not depend on which level is being
tested. The `[1]` offset excludes the penetrating bar, which may legitimately close
beyond the level with the reclaim arriving later.

**What was wrong.** `close[1] < lv` is a one-bar lookback. A level being chopped
flips intact/broken/intact on alternating bars, so — with no cooldown anywhere in
M6 — **a chopping level re-fires every second bar, indefinitely.** That is the
mechanism behind the label wall, and it is a design omission rather than a
mis-set parameter.

**Scope of the fix, stated honestly.** This addresses chop around *stable* levels
(PDH/PDL/ONH/ONL/IB/OR/RTHo). It does **not** address swing levels, and the reason
is instructive: `lastPH` is the highest high of its window, so every close in that
window is at or below it by construction. **A freshly confirmed pivot passes the
intact test automatically.** If SwH/SwL dominate the class breakdown, they need a
different treatment — a minimum age, a minimum separation from price, or exclusion
from M6's sweepable set — and that should be chosen from the numbers, not guessed.

**Consequence for sequencing:** this fix may absorb most of what a consumption rule
was meant to do. Measure after it before building D-031.

**Wrong if:** the rejection counter shows it discarding genuine first touches — a
level approached for the first time after price crossed it needs `intactBars` clean
closes before it can be swept, which delays but should not prevent.

---

## D-031 — Per-class re-arm gate (consumption)
**Status:** Accepted · 2026-08-29 · implemented after the post-D-030 measurement

**The requirement.** Permanent consumption is wrong: PDH swept at 10:00 and swept
again at 14:00 is a double top, one of the better setups in the framework, and a
first-sweep-consumes rule produces nothing the second time. The rule must separate
*a level being chopped* from *a level retested after price meaningfully left and
returned*.

**Proposed rule.** A level is **armed** by default and becomes **spent** on firing.
It re-arms only when **both**:

1. **Excursion** — price has traded at least `reArmAtr × ATR` away from the level,
   on the side it reclaimed to, at any point since the fire.
2. **Time** — at least `reArmMin` minutes have elapsed since the fire.

Both, not either. Time alone lets slow chop re-arm; distance alone lets a fast
spike re-arm. The excursion is ATR-scaled for the same reason penetration is
(D-023).

**Keyed by CLASS, not by price.** The registry rebuilds `lvlP` every bar, so
price-keyed state would need an unbounded keyed store. But each class holds at most
one price at a time, so three persistent arrays of 14 — spent price, spent bar, max
excursion since — suffice, and a class's state resets when its price changes.

That keying exposes something useful: a relocating swing pivot is a *new price*, so
it resets its own state and re-arms immediately. The rule would therefore do almost
nothing for swing levels — further evidence that swing levels are a separate
problem (D-030) rather than a consumption problem.

**Costs and risks.**
- A genuinely tight double top — one where the pullback is under `reArmAtr` — gets
  suppressed. That is a real loss, not a hypothetical, so `reArmAtr` should start
  modest (~0.75–1.0) and **the suppressed fires must be counted**, so the rule can
  be judged on what it discards as well as what it admits. Same principle as D-024
  and D-026.
- Interaction with D-027: M2's proximity damping should stay keyed to M6's *hold
  window*, not to the spent state. The redundancy D-027 corrects is mechanical to
  the reclaim, not to the level having been used.
- Session boundaries deliberately get no special case: excursion-plus-time should
  handle an overnight sweep followed by an RTH retest without an extra assumption.

**Ranked second, as a possible backstop rather than a replacement:** a hard cap of
N fires per class per session. Blunt, carries no notion of what happened in
between, but it bounds the label wall directly and is trivial to reason about.

**Implemented as specified.** The post-D-030 measurement settled it: the intact fix
alone cut GC from 50.2 to 21.5 fires/session (−57%), but **46% of the remaining 882
fires were repeats on a level that had already fired that session**. Too large to
leave, and it persists beyond the swing removal — PDC (2.1/session) and RTHo
(1.7/session) are both above the 1.0–1.3 of the other stable classes.

Defaults: `reArmAtr` 0.75, `reArmMin` 45 minutes.

**Suppression is counted, but the counter is an upper bound and is labelled as
one.** `m6ReArmSup` counts *in-band penetrations skipped because the class was
spent*, not fires that would have occurred — an exact count would need a shadow
reclaim state machine running on suppressed levels. The observed in-band→fire
ratio was 882/1494 ≈ 59%, so the table shows `~N × 0.59 fires` as an estimate
beside the raw count. Read it as an estimate.

**Unarmed levels are excluded from candidate selection, not merely from firing.**
M6 keeps one pending per side and takes the deepest in-band penetration. If a spent
level could win that selection and then be suppressed at fire time, it would block
an armed level's opportunity on the same bar. So the filter is applied where the
candidate is chosen.

**If the rate lands below ~3/session, `reArmAtr` is the first thing to loosen** —
that is the parameter that suppresses tight double tops, which are real setups.

---

## D-032 — Swing pivots stay in the registry but leave M6's sweepable set
**Status:** Accepted · 2026-08-29

`sweepUseSwings` defaults **off**. SwH/SwL remain in the level registry and remain
available to M2 as location context; they are simply not sweepable.

**Measured.** On GC 5m over 41 sessions, SwH and SwL — 2 of 12 classes — produced
**35% of penetrations (949/2715) and 40% of fires (354/882)**, at 4.0 and 4.6 per
session against 1.0–2.1 for every other class.

**The mismatch is definitional, not a matter of degree**, which is why the fix is
removal rather than a minimum-age or minimum-separation filter:

1. `lastPH` is the highest high of its own window, so **every close in that window
   is at or below it by construction**. A freshly confirmed pivot passes any
   intact test automatically — D-030 cannot touch it, and no stricter version
   could.
2. The level is **relocated to wherever price just was**, so it is almost always
   the nearest level to price and therefore the most penetration-prone.
3. Under D-031 a relocated pivot is a *new price*, so it resets its own re-arm
   state and re-arms immediately. Consumption cannot touch it either.

A filter tuned against any of these three would be fighting the definition. A swing
pivot is a description of where price has recently been; a sweep is an excursion
through a level that was *established before* price arrived. Those are different
objects.

**Why they stay in the registry.** Proximity to a recent extreme is real location
information and M2 should have it. Removing them from the registry entirely would
discard that to fix an unrelated problem.

**Side effect, and it is a benefit.** M2 and M6 now operate on **partially
different level sets**. That reduces the D-027 cross-category collinearity
*structurally* rather than by damping: a swing level can supply M2's Location
without any possibility of M6 also claiming Liquidity for the same price. D-027's
damping still applies to the levels both modules share.

**Reversible by input**, so the measured 4.0 and 4.6 per session can be restored
for comparison.

**Wrong if:** M6's fire rate on the remaining classes turns out too sparse to
satisfy gate rule 2 (D-019), where M6 carries the requirement alone. The answer
then is a better-defined swing level — one established and then *left* before being
tested — not re-admitting the current definition.

---

## D-033 — The REPEAT counter measures a population D-031 does not gate
**Status:** Accepted · 2026-08-29 · diagnosis, then instrumentation

**The observation.** After D-031/D-032 on GC 5m: fires fell 882 → 408, but the
repeat share moved 46% → 48%. The gate more than halved total fires while appearing
not to touch repeats at all.

**The diagnosis: the two are measuring different populations.**

`m6RepeatFire` increments on **any fire at a price that has already fired since the
last RTH open**, regardless of elapsed time or distance travelled. It is
session-scoped and price-keyed.

D-031 blocks a fire only while the class is spent **and** has not yet satisfied
excursion-plus-time. Once both are satisfied the level re-arms and is *supposed* to
fire again — that is the double-top case the rule was written to preserve.

**So a legitimate 10:00/14:00 double top increments the REPEAT counter.** The 48%
is not evidence the gate failed. It is also not evidence it worked: the counter
cannot distinguish a leak from an intended re-arm, so it can support neither
conclusion.

**A composition effect explains the flat share.** Swing levels relocate ~33 times
per session, so each fire was usually at a *new* price and was therefore counted as
a non-repeat. Removing them (D-032) removed mostly non-repeat fires, which
mechanically raises the repeat share of what remains. 46% → 48% across a change of
population is not a comparison of like with like.

**The ~0.59 suppression estimate was wrong and is removed.** It projected 785
skipped in-band penetrations into ~463 suppressed fires, against an actual
non-swing reduction of ~120. The ratio was derived from a population counted per
*pending*, then applied to one counted per *level-bar* — many of the 785 are the
same level re-penetrated on consecutive bars while spent, which would never have
been separate fires. The row now reports skipped level-bars and skipped *bars*,
with no projection.

### Instrumentation added

- `m6FireSpent` — fires where the class was spent at fire time. **This is the
  D-031-relevant repeat count**, class-keyed and not session-scoped.
- `m6ReArmedOK` — of those, had satisfied both conditions. Intended behaviour.
- `m6Leak` — of those, had **not**. **Must be zero.** Non-zero is a gate leak.
- `repeatByClass` — repeats broken out per class.
- Mean re-arm margin: excursion as a multiple of threshold, and elapsed bars.
  A mean near 1.0× says repeats are scraping through and the threshold is
  marginal; a mean well above says they are clearing it comfortably and the
  threshold is not what is admitting them.

### A leak path exists in the current code

`pHi` and `pLo` pendings are independent, and `armed` is evaluated at **candidate
selection**, not at fire. So on one class: a low-sweep pending fires and marks the
class spent, and a high-sweep pending created earlier on the same class can then
fire on a later bar while spent. `m6Leak` is precisely the assertion that detects
this. If it comes back non-zero, the fix is to re-check `armed` at fire time as
well as at selection — not to change the thresholds.

**Do not tune `reArmAtr` or `reArmMin` until `m6Leak` is known.** If it is zero the
gate is tight and 48% is entirely intended retests; if it is non-zero the thresholds
are innocent and the bug is the double-pending path above.

---

## D-034 — Barrier-type vs reference-type levels: classify and measure
**Status:** Accepted · CLOSED by measurement · 2026-08-29

**The argument, which is sound.** A sweep is a liquidity event: resting stops beyond
a level are triggered and price rejects. Stops cluster beyond **extremes** —
PDH/PDL, ONH/ONL, IBH/IBL, ORH/ORL — because those are what a position is protected
against. Nobody parks a protective stop at yesterday's *close* or at the RTH *open*.

Measured on GC 5m: **PDC 1.5/session and RTHo 1.2 lead every extreme-type level**,
including PDH 0.9 and PDL 0.7. If the argument holds, that ordering is the same
definitional mismatch as swings wearing a different class.

**The better name is barrier vs reference.** PDC and RTHo are **magnets** — price
rotates around them by construction, all session. A sweep needs a **barrier**:
something price must break *through*, with orders resting beyond it. Rotation
across a magnet is not a failed auction, it is the auction working.

**One measurement could invert this, and it should be taken first.** Fire count is
partly a function of **exposure** — how much time a level spends near price. PDC and
RTHo sit in the middle of the range and are near price constantly; PDH and PDL are
far away most of the session. Their raw penetration counts are also the highest
(245 and 218), which is consistent with exposure rather than with level type.

The correct normalization is **fires per bar-of-proximity**, not fires per session.
If PDC still leads after normalizing, the definitional argument is confirmed and
exclusion is right. If it falls below PDH/PDL, the raw ordering was an exposure
artifact and excluding it would discard a level type that is *better* behaved per
unit of opportunity.

This differs from the swing case (D-032), where the definitional argument stood on
its own and needed no counts: a pivot passes any intact test by construction. Here
the argument is structural but the evidence offered for it is a raw rate, and raw
rates are exposure-confounded.

**Implemented as a measurement, not yet as a filter.**

1. `CLS_TYP`, a class-indexed constant: 0 = BARRIER (PDH/PDL, ONH/ONL, IBH/IBL,
   ORH/ORL, SwH/SwL), 1 = REFERENCE (PDC, RTHo, Rnd±). **This is the same field
   D-028 needs** for the M1 damping question — M1's redundancy is with *being at a
   session extreme*, which is exactly this distinction. Added once, serving both;
   do not add a second.
2. **Exposure** is counted per class as bars in which the level sat within one
   `maxPen` of price — bars on which a sweep of it was *geometrically possible*.
   That is the correct denominator. Proximity in M2's sense (`structProx`) would be
   the wrong window: it measures where a setup could be scored, not where a sweep
   could occur.
3. `sweepUseReference` defaults **ON**, deliberately, so the two groups can be
   compared rather than one being assumed wrong.
4. The table reports per-class `expBar` and `f/100xb`, plus BARRIER and REFERENCE
   aggregates. **Flip the default only if reference still leads on `f/100xb`.**

**Why the raw ordering could not settle it.** Fires/session is exposure-confounded:
a mid-range level is near price far more often than PDH is, so it gets more chances
to fire. PDC and RTHo having the top two *penetration* counts (245, 218) is exactly
what mid-range exposure predicts, independent of whether they are the wrong kind of
level. If they still lead per bar-of-proximity, the structural argument is
confirmed. If they fall below PDH/PDL, the raw ordering was an artifact and
excluding them would discard the *better-behaved* level type.

This is the reverse of D-032, where the definitional argument stood without counts:
a pivot passes any intact test by construction, so no measurement could rescue it.
Here the argument is structural but the evidence offered for it was a raw rate.

### RESULT (GC 5m, 41 sessions) — the raw ordering was an artifact, and it was inverted

| | fires | f/100 exposure-bars |
|---|---|---|
| **BARRIER** | — | **3.64** |
| **REFERENCE** | — | **2.35** |

Barrier leads by **55%**. Per class, **PDH is the strongest at 3.88 and PDC the
weakest at 1.94** — the exact reverse of the fires-per-session ordering (PDC 1.5
vs PDH 0.9) that motivated the hypothesis.

**`sweepUseReference` stays ON.** The structural argument had the right direction —
barriers do outperform references — but the evidence originally offered for it
pointed the opposite way, because PDC and RTHo sit mid-range and were simply near
price far more often. Excluding them would have removed levels that fire *less* per
unit of opportunity than the barriers being kept, while also removing the barrier
advantage from view.

**The general lesson, worth carrying into every later module:** a rate is only
evidence when its denominator is the set of opportunities, not the set of sessions.
Any future "class X fires too much" claim needs the same normalization before it
justifies a filter. D-032 remains the exception — there the argument was
definitional and no denominator could rescue it.

**Noted for when the numbers arrive:** round numbers are classified REFERENCE, but
they carry a second defect — `ceil(close/step)*step` **relocates** whenever price
crosses a step boundary, which is the D-032 swing problem again. They are off by
default; if they are ever enabled they need a fixed anchoring, not just a type.

---

## D-035 — Blind review mode, and the number the diagnostics cannot see
**Status:** Accepted · 2026-08-29

`blindMode` suppresses every drawing — level lines, level labels, sweep markers,
grade labels — while leaving both diagnostic tables live. The status table header
reads `** BLIND **` so the state is never ambiguous.

**Why an input rather than just switching the indicator off.** Turning the
indicator off takes the tables with it. The review needs the diagnostics available
during the overlay pass, and needs the marks absent during the marking pass.

**Why the protocol is blind at all.** Reading the engine's marks and asking "would
I have taken that?" is a much weaker test — the marks anchor the judgement. Marking
the session first, independently, is the only way to get an honest third bucket.

**The three buckets, and which one matters most:**

| Bucket | Visible to diagnostics? |
|---|---|
| matched | yes |
| M6-only | yes — every counter in the script measures this population |
| **yours-only** | **no. A missed event leaves no trace in any counter.** |

Every number produced so far — fire rate, funnel, per-class breakdown, exposure
normalization, leak assertion — measures whether M6 does what it says. **None of
them measure whether what it says is worth saying.** A perfectly counted 10
fires/session of events no discretionary reader would mark is a well-built detector
of nothing. The yours-only bucket is the only instrument that can detect that, and
it cannot be built in Pine because it requires the judgement the engine is trying
to approximate.

**Consequence for module order.** If agreement is poor, M6's definition changes and
anything built on it gets rebuilt — so M1/M3/M5 wait. If it is decent, the
composition of the *yours-only* misses selects the next module: misses that need
extension context argue for M1/M5, misses that need volume context argue for M3.
The next module is chosen by what M6 structurally cannot see, not by the planned
order.

**Supporting change:** sweep labels now carry class, score, penetration in ticks and
bars-to-reclaim, with opacity graded by score (solid >= 0.70, mid >= 0.45, faint
below), so agreement can be scored at a glance without hovering each marker.

**The scoring definition lives in `docs/REVIEW_PROTOCOL.md`**, written before the
results so the interpretation is pre-registered rather than reconstructed after the
numbers arrive.

**DEFERRED 2026-08-29, not cancelled.** Not run, for a reason worth recording:
insufficient discretionary screen time on GC/NQ for the marks to be a meaningful
baseline, and a working definition close enough to M6's own logic that agreement
would have been **circular**. A pass under those conditions yields a number that
looks like validation and is not — and which would then be cited in every later
decision as though it meant something. Declining to generate it is the right call.

The cost is carried in `OPEN_ITEMS.md` §1 rather than being written off: M6's
definition is unvalidated, the *yours-only* and *matched-oppose* populations remain
structurally invisible, and every module built above M6 inherits that unknown
through D-019's category-Q gate keeping. Revisit with more screen time, or once the
engine is grading and can be watched live — marks taken from watching it be wrong
in real time are a different and arguably better baseline than a cold chart.

**Implementation note.** The level-drawing CLEAR now runs unconditionally rather
than inside the draw condition. Previously, disabling drawings left the last
rebuild stranded on the chart — which would have defeated blind mode on any
partial recalculation.

---

## D-036 — M1 logs distance and damping as separate terms
**Status:** Accepted · 2026-08-29

M1's score is `distance x band-walk damping x barrier damping`, with each factor
scored, logged and plotted **separately**, mirroring M2's proximity/stacking split
(D-027).

**Why separable.** D-028 asks whether M1's redundancy with M6 lives in the
**distance** term specifically — sweeps happen at extremes, and extremes are where
VWAP extension is largest. A blended score cannot answer that question. The split
is what makes the measurement possible later without rebuilding the module.

**A band-walk sets `active = false`, not merely `score = 0`.** This is the
load-bearing detail. Under D-002 a zero-scored active module still contributes its
weight — but `active` also fills the **category**, and category E filling is what
lets the D-019 gate reach three. A trending market must never satisfy the gate's
third category. `bandWalkDamp` defaults to 0.0 (full suppression); raising it above
zero keeps M1 active with a reduced score, which is a deliberate and different
choice.

**D-028's check is wired and inert.** `m1ExtremeDamp` defaults to 1.0. The
barrier-vs-reference classification it needs (`CLS_TYP`) already exists from D-034,
and M6's fired class is now retained through the hold window, so the D-028
measurements can run the moment M5 lands — no further registry or module change.

**Anchor resets are evaluated unconditionally.** `timeframe.change()` carries series
state, so all three (`D`/`W`/`M`) are computed every bar and the anchor selection
picks among the results. Putting them inside the branch would corrupt the ones not
taken.

**Sigma is a running volume-weighted standard deviation** about the anchored VWAP,
from `sum(v)`, `sum(pv)` and `sum(p^2 v)` since the anchor — not a rolling stdev of
price. Bands default to 1.0 / 2.0 / 2.5 sigma, with the score ramp aligned to
2.0 → 2.5 so the plotted bands and the scored thresholds are the same objects.

**Wrong if:** the warm-up (30 min) turns out too short — a freshly anchored VWAP
has near-zero sigma, which inflates |z| and would make M1 fire hardest exactly when
it knows least. Watch the first graded setups after each anchor reset.

---

## D-037 — Gate funnel, and two M1 defects found by reading the code
**Status:** Accepted (diagnostic) · 2026-08-29 · **defects confirmed and fixed in D-038**

M1 landed, category E became fillable, and **nothing graded** on GC 5m across the
full window. Two of the three candidate explanations are answerable from the source
without running anything, and both are defects introduced in D-036.

### Defect A — the band-walk guard caps M1's own active window

`m1Outside` uses `|z| >= vwapSigmaLo`, and `m1DistRaw > 0` — M1's activation
condition — requires `|z| > vwapSigmaLo`. **The same threshold gates both.** So the
band-walk counter starts incrementing on the exact bar M1 becomes eligible, and:

> **M1 can be active for at most `bandWalkBars − 1` consecutive bars per excursion.**
> On GC 5m that is **3 bars**, from `f_bars(20) = 4`.

The guard was meant to catch a *trend walking the band*. As written it fires on any
excursion lasting 20 minutes, which is an ordinary extended move — the exact
condition M1 exists to detect. It does not distinguish "price is beyond the band"
from "price is *still advancing* beyond the band".

**Proposed fix (not applied):** separate the two thresholds, and make the
walk condition directional. A band-walk is price beyond the band **and still making
new extremes** — e.g. the running max of `|z|` continuing to rise — not merely
sitting outside it. A stalled excursion is exactly what should score.

### Defect B — M1 is frozen outside RTH while M6 fires around the clock

`vwapRthOnly` defaults true and `vwapAnchor` defaults to `RTH open`, so
`m1UseBar = inRTH` and **no accumulation happens outside RTH**. For GC, RTH is
08:20–13:30 = **62 of 288 daily 5m bars (21.5%)**.

Outside that window VWAP and sigma hold yesterday's closing values while price
drifts away, so `|z|` inflates on a stale anchor, the band-walk guard then
suppresses it, and M1 is effectively dead for ~78% of the session. **M6 fires
across all 24 hours.** Most M6 fires therefore land where M1 cannot contribute.

**Proposed fix (not applied):** either accumulate across the whole session while
keeping the RTH anchor, or make M1 explicitly `active = false` outside RTH rather
than reporting a z-score against a frozen mean. The current state is the worst of
both — silently wrong rather than honestly absent.

### Finding C — M1 and M6 are anti-correlated in time, by construction

Not a defect; a structural property worth recording, and it sharpens D-028.

**M6 fires on the reclaim, which is a move back toward VWAP.** M1's extension is
maximal at the sweep extreme and is *already decaying* by the time M6 confirms. The
hold window (D-025) mitigates this but cannot remove it.

So the M1/M6 relationship may not be **redundancy** at all — the two may be
measuring the same event **at different phases**. If so, D-028's proposed damping
would be exactly the wrong treatment: it would penalise a pairing that is
complementary in time rather than duplicative in information. The gate funnel's
`M1 & M6` count is the first direct measurement of this.

### The funnel

Same shape as the M6 funnel — show which *stage* is starving rather than only that
the output is empty. Per-bar counts of each module active, all three pairwise
coincidences, the triple, then the gate stages (L → L+(Q|F) → +3rd category →
PASS), grade counts, the max composite ever reached, and a six-bucket composite
histogram over bars where anything was active.

Two probes target the hypotheses directly:

- **`M1 walk-blocked ...while M6 live`** — bars where M1 was otherwise eligible but
  suppressed by the band-walk *on a bar where M6 was live*. This is Defect A and
  the mutual-exclusion hypothesis measured as one number.
- **`M6 live in RTH / outside`** — Defect B measured directly. If the outside count
  dominates, M1's anchor configuration is the binding constraint, not any threshold.

**No thresholds, weights or `catDamp` touched.** Fitting a threshold to a gate that
never opens would move the failure somewhere less visible.

---

## D-038 — M1 fixes: session-block anchoring, and a directional band-walk
**Status:** Accepted · 2026-08-29 · fixes the defects diagnosed in D-037

### The measurement that settled it (GC 5m, 11,268 bars)

| | |
|---|---|
| M1 active | 641 (5.7%) |
| M2 active | 2408 (21.4%) |
| M6 active | 1491 (13.2%) |
| ALL THREE | **72** |
| stage L → L+(Q\|F) → +3rd | 2408 → 332 → **17** |
| GATE PASS | 17 (0.41/session) |
| graded C/B/A | **0 / 0 / 0** |
| max composite | **0.432** against a 0.45 floor |
| M6 live outside RTH | **1021 of 1491 = 68%** |
| M1 walk-blocked while M6 live | 180 = 12.1% of M6 |

**Defect B was the binding constraint** at 68%; Defect A real but secondary at
12.1%; and the composite topped out *below the C floor*, so even the 17 bars that
cleared the gate had nothing to grade. Three failures stacked, which is why the
output was not merely sparse but exactly zero.

### Fix B — session-block anchoring, not full-session accumulation

Of the two options in D-037, **accumulating across the whole session while keeping
the RTH anchor is wrong for GC specifically**. D-007 already holds that the
23-hour Globex session is not one auction; a VWAP anchored at the pit open but
accumulating Asian volume would be a mean over a period the instrument does not
trade as one thing — statistically well-defined and economically meaningless.

Instead the anchor is now **session-aware**: three configurable auction blocks per
instrument family, anchored at the start of each and accumulating within it.

- **GC:** Asia `1800-0300`, London `0300-0820`, NY pit `0820-1330`
- **NQ:** Asia `1800-0400`, Europe/pre `0400-0930`, RTH `0930-1600`

`Session blocks` is the new default. **`RTH open` remains available and is the
right choice for NQ**, where the cash session genuinely is the auction — the
blocks are exposed as inputs precisely so that stays a choice rather than an
assumption.

**Outside every block, M1 is now `active = false`.** The old behaviour — holding a
frozen VWAP and reporting a z-score against a mean that stopped updating hours ago
— was worse than absence, because it was confidently wrong rather than silent.
`vwapRthOnly` is removed; the accumulation window is now implied by the anchor.

### Fix A — a band-walk must be *advancing*, not merely *outside*

The old test was `|z| >= vwapSigmaLo` for `bandWalkBars` consecutive bars — the
same threshold that makes M1 active, so the counter started on the bar M1 became
eligible and capped its active window at `bandWalkBars − 1` bars.

The new test tracks the running peak of `|z|` for the current excursion and how
long since that peak was extended:

> **band-walk = outside for `bandWalkBars` **and** the peak extended within the
> last `m1StallMin` minutes.**

A stalled excursion — beyond the band but no longer making new extremes — is
exactly the setup, and now scores. A peak that keeps rising is a trend, and is
suppressed.

**The threshold separation proposed in D-037 was dropped as unnecessary.** Once the
condition is directional the mechanical cap disappears on its own, because a
stalled excursion no longer trips the counter regardless of sharing a threshold.
One fewer knob with no evidence behind it.

### Thresholds deliberately untouched

`0.432` was measured with M1 dead 78% of the time and self-capped at 3 bars in the
remainder. **It is not evidence about the 0.45 floor.** Any threshold fitted to
that number would be fitted to two defects. Re-measure first.

**Wrong if:** the blocks turn out to fragment a genuinely continuous auction — the
London/NY overlap is one move on gold, and the `0820` boundary cuts through it. If
the NY block's VWAP looks wrong in the first hour, the London block should extend
through the overlap rather than the boundary being moved.

---

## D-039 — An unimplemented module is OFF, not idle
**Status:** Accepted · 2026-08-29 · refines D-002 · **fixes a ceiling that masked every result since the gate first opened**

Module implementation state is now a compile-time constant (`M1_IMPL` … `M7_IMPL`)
ANDed into the push. Stubs are excluded from the composite entirely.

### The bug

All seven `use*` toggles default **true**, so all seven modules were pushed —
including four stubs. D-002 reads an enabled-but-idle module as *"measured, nothing
there"* and correctly retains its weight in the denominator.

**But nothing was measured.** A stub is semantically **OFF** — *"not measured"* —
which D-002 assigns to the excluded state. The four stubs were miscategorised, and
the composite was arithmetically correct over a denominator that was wrong.

### The arithmetic

| Module | cat | weight | category factor | effective |
|---|---|---|---|---|
| M1 | E | 1.0 | 1.0 (first E) | 1.0 |
| M2 | L | 1.0 | 1.0 (first L) | 1.0 |
| **M3** | L | 1.0 | 0.5 (second L) | **0.5** |
| **M4** | F | 0.5 | 1.0 | **0.5** |
| **M5** | E | 1.0 | 0.5 (second E) | **0.5** |
| M6 | Q | 1.0 | 1.0 | 1.0 |
| **M7** | C | 0.5 | 1.0 | **0.5** |
| | | | **denominator** | **5.0** |

Maximum numerator from the three live modules is **3.0**, so:

> **the composite was capped at 0.600** — with the A threshold at 0.75, **grade A
> was unreachable by construction**, and C at 0.45 required all three live modules
> to average **0.75 simultaneously**.

Observed peak was 0.432 = a numerator of 2.160, i.e. a mean of 0.720 across the
three. **The floor was not structurally unreachable — it was missed by 0.03 of mean
module score**, which is why it looked like a behavioural problem for two rounds.

### After the fix

Denominator **3.0**, maximum composite **1.000**, scale factor **×1.667**. The
observed peak bar re-scores at **0.720 — a B grade**. `catDamp` also goes inert,
correctly: each live category now holds exactly one module, so there is nothing to
damp until M3 or M5 lands.

### Why this hid for so long

It produced no error and no anomaly. Every diagnostic reported real numbers about
a system whose ceiling sat below its own threshold, and each round the shortfall
looked like the module under investigation. Two genuine M1 defects (D-038) were
found and fixed underneath it — both real, neither the binding constraint. Removing
a constraint that suppressed M1 on 68% of M6-live bars moved the max composite by
**0.000**, and that invariance was the tell.

**The lesson, and it generalises:** when a fix that should have moved a number
moves it by nothing, stop fixing and check whether the number *can* move. A ceiling
is invisible to every instrument pointed below it.

### Guard

The denominator and the theoretical max are now displayed in both the status table
and the gate funnel. A structural ceiling cannot hide again without someone
ignoring a number on screen.

**Constants, not inputs, on purpose:** implementation state is a fact about the
source, not a user preference, and must not be settable into a state that
contradicts the code. Flipping the constant is part of implementing the module.

---

## D-040 — Retroactive ceiling audit, applied as a standing instrument
**Status:** Accepted · 2026-08-29 · generalises D-039

D-039's lesson — *an invariant number under a fix that should have moved it is
evidence about the measurement, not the mechanism* — applied backwards over every
diagnostic in the script. Three real findings.

### 1. `minCats` can exceed the number of categories that can ever fill

Only three categories are reachable with M1 (E), M2 (L) and M6 (Q) implemented.
`minCats` accepts up to **5**. Setting it to 4 or 5 guarantees **zero output**, and
that zero would look exactly like a behavioural result — the same failure mode as
D-039, one level up.

Now displayed: `cats reachable N of 5` against `minCats`, flagged **UNREACHABLE**
when the demand exceeds the supply.

### 2. `requireOF` is a guaranteed-zero setting while M4 is a stub

Category F cannot fill, so turning `requireOF` on makes every grade impossible.
The tooltip warned about weakness; it did not say the setting is currently
*inert-to-zero*. Now displayed as `F fillable: NO`.

### 3. The grade-age histogram is a near-binary instrument

`holdBars = 3` on GC 5m, so `m6ContribAge` can only ever take **4 values (0–3)**,
and the fresh/mid/stale cuts land at 1.02 and 2.01 — ages 0,1 → fresh; 2 → mid;
3 → stale. The histogram cannot resolve the question D-026 asks it much better than
a coin flip. **Not a ceiling but a resolution limit**, and one that argues the
D-026 question needs a longer hold window or a continuous age readout rather than
buckets. Now displayed: possible ages and the actual cut points.

### Also added: a bucket self-check

`gradesFresh + gradesMid + gradesStale + gradesNoM6` must equal `gradesTotal` —
every path through the telemetry block increments exactly one of the four. The
status table now displays **`!! BUCKET MISMATCH`** with both values when it does
not, rather than showing a plausible-looking row.

This was added because a reported reading of `0/0/0 (noM6 0 of 8)` is
**arithmetically impossible from the source**, and no amount of re-reading the code
resolves it. Rather than invent a mechanism, the invariant is now asserted on
screen: the next run either shows the row consistent (the earlier reading was
misread) or prints the mismatch (the counters really are wrong, and it is a Pine
behaviour not visible in the source).

### Diagnostics audited and found sound

Fire rate and the M6 funnel, `m6RepeatFire`, exposure-normalised `f/100xb`,
`m6ReArmedOK` / `m6Leak`, and `denomEff` all have no ceiling below their useful
range. `gfMaxComp` and the top three `gfHist` buckets *did* — that was D-039, now
fixed and displayed.

**`gradesNoM6` is a deliberate invariant, not a masked ceiling:** it is
structurally 0 while M6 carries gate rule 2 alone, and only becomes informative
when M4 lands. Recorded so it is not mistaken for a finding.

---

## D-041 — Single-source instruments after two impossible readings
**Status:** Accepted · 2026-08-29

Two diagnostics reported values the source cannot produce. Rather than continue
re-reading code that says the outputs are impossible, both were rebuilt so that the
displayed numbers are **derived from one array** and cannot contradict each other.

### The two impossible readings

**Grade-age buckets.** `0/0/0 (noM6 0 of 8)`. Every path through the telemetry
increments `gradesTotal` **and exactly one** of `{noM6, fresh, mid, stale}`, so
`0+0+0+0 = 8` cannot happen. The D-040 mismatch flag then did **not** fire, which
means `gradesFresh + gradesMid + gradesStale + gradesNoM6 == gradesTotal` evaluated
true — so the summed values and the displayed values disagreed with each other,
inside one `table.cell` call built from the same variable names.

**Module coincidence.** `ALL THREE` fell 79 → 41 while every individual and
pairwise count held identical, on *more* bars (11,268 → 11,539). `gfAll3` reads
`m1Active and m2Active and m6Active` on the same line-block as the pairwise
counters — the flags are computed in the module engines, upstream of the push
guards D-039 changed, so the counter is measuring what its name says. For the
triple to halve while all three pairwise intersections hold fixed, M1 would have to
have lost 38 triple-members and gained exactly 38 replacement M1∩M6 members outside
M2, simultaneously preserving M1∩M2 — a coincidence across three counters at once.

**Neither is explicable from the source.** The honest conclusion is not a mechanism
but a method failure: independent counters that can drift from their own total are
un-auditable, and I built several of them.

### The fix: derive, don't accumulate

- **Grade ages** are pushed to `gradeAgeLog`, one entry per grade onset (`-1` for no
  M6 contribution). Fresh/mid/stale/noM6 and the total are all **derived from that
  array at render**. The old counters are retained *only* as a cross-check, and the
  row flips to **`!! COUNTER DISAGREE`** printing both sets when they differ. The
  raw last-10 ages are printed, so the actual values are visible rather than
  inferred from bucket counts.
- **Module coincidence** is now a 3-bit pattern (`1=M1, 2=M2, 4=M6`) accumulated
  into `comboHist[8]`. Every individual, pairwise and triple count is derived from
  it — `M1∩M2 = c3+c7`, `ALL3 = c7` — so they are **arithmetically incapable** of
  contradicting one another. The independent counters are displayed beside the
  derived ones and flagged **`!! DERIVED DISAGREE`** on any mismatch. The row also
  checks `sum(comboHist) == gfBars`, catching any bar counted zero or twice.

### The generalisation

D-039: an invariant number under a fix that should have moved it is evidence about
the measurement. **D-041 extends it:** *a set of counters that can disagree with
their own total is not an instrument, it is several instruments that happen to be
printed together.* Where a quantity has an invariant — buckets summing to a total,
pairwise counts implied by a joint distribution — accumulate the **joint
distribution** and derive the views. Then a contradiction is impossible by
construction rather than merely unexpected.

Applies to every diagnostic added from here: prefer one source with derived views
over several parallel counters, even when the parallel counters look simpler.

**Follow-up, and an admission.** The first build of this fix did not compile:
the derivation block was inserted *after* the `table.cell` call that used it, and
Pine has no hoisting. My static checker missed it because it only tracked
**top-level** declarations, not block-local ones — so it had been blind to an
entire class of error the whole project. The checker now tracks first-assignment
line at **any scope**, including for-loop induction variables and function
parameters, and lives in `tools/pinecheck.py` so it is run rather than
reconstructed. Two prior compile errors (the wrapped ternary, this one) would both
have been caught by it.

---

## D-042 — The cross-check was correct; the way it was displayed was not
**Status:** Accepted · 2026-08-29

The derived-vs-independent cross-check reported an apparent 20x gap on M2&M6
(26 vs 558). It was not a derivation bug. **Reconciling the reported histogram
against every constraint identifies exactly one value that satisfies all eight
simultaneously.**

| constraint | with `c3 = 39` | with `c3 = 139` |
|---|---|---|
| M1 = c1+c3+c5+c7 | 715 vs 815 ✗ | 815 ✓ |
| M2 = c2+c3+c6+c7 | 2352 vs 2452 ✗ | 2452 ✓ |
| M6 = c4+c5+c6+c7 | 1511 ✓ | 1511 ✓ |
| M1&M2 = c3+c7 | 80 vs 180 ✗ | 180 ✓ |
| M1&M6 = c5+c7 | 124 ✓ | 124 ✓ |
| M2&M6 = c6+c7 | 558 ✓ | 558 ✓ |
| ALL3 = c7 | 41 ✓ | 41 ✓ |
| sum = bars | 11443 vs 11543 ✗ | 11543 ✓ |

The decisive one is **sum vs bars**, because that check is computed *in Pine from
the same array* and was reported as passing. A histogram summing to 11,543 requires
`c3 = 139`. With it, the bit masks (`M1&M2 = c3+c7`, `M2&M6 = c6+c7`) are correct
and every derived value matches its independent counter.

**So the instrument was sound and the earlier readings were transcription
artifacts.** That also disposes of the 79 → 41 question: `ALL3 = c7 = 41` agrees
with the independent counter, and the 79 came from a build predating the
single-source histogram, read through the same hand-transcription path.

### The actual defect, which is mine

Two display choices made the instrument hostile to the only way it can be read —
a human copying numbers off a screen:

1. **Packed cells.** Three counts crammed into one cell as `a/b/c`. A dropped
   leading digit in a run of digits is invisible and silently changes the
   conclusion. I did this repeatedly across all three tables.
2. **An aggregate flag on a specific row.** `okAll` covered singles, pairs *and*
   the triple, but sat on the singles row, so it reads as "the singles agree". A
   pass/fail marker must sit on the thing it tests, or it misdirects exactly when
   it matters.

### Fixed

The cross-check is now **one comparison per row** — M1, M2, M6, each pair, and the
triple — each with derived and independent in separate columns and its own
`OK`/`BAD` marker. The histogram prints **one bucket per cell**, so no cell carries
a run of digits. The sum-vs-bars check gets its own row and marker.

**Standing rule, extending D-041:** an instrument is not just its arithmetic, it is
its arithmetic *plus how it is read*. A correct number in an unreadable layout has
the same effect as a wrong number. Never pack multiple values into one cell in a
diagnostic table, and never attach an aggregate pass/fail to a row that displays
only part of what it covers.
