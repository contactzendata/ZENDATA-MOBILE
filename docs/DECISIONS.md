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
**Status:** Accepted · 2026-08-29 · extends D-014 · **precedence mechanism superseded by D-043**

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

---

## D-043 — Category precedence is an input and an explicit rank
**Status:** Accepted · 2026-08-29 · supersedes D-020's precedence mechanism

D-020 set within-category precedence by **declared push order**: the first enabled
module in a category took factor 1.0, the rest `catDamp`. With M5 landing as a
second Extension module that becomes a live decision, and push order is the wrong
place to make it — it is invisible, and it would have silently decided the same
question again when M3 arrives as a second Location module.

Precedence is now an explicit **rank per module**, resolved in a second pass by
finding the lowest rank present in each category. `ePrimary` is an input
(`M1` / `M5`, default `M1`).

**Why an input rather than a constant.** The evidence ledger (`SPEC.md` §4) rates
VWAP-band reversion and ADR exhaustion **equally** — both "practitioner-supported,
thin peer review". Hardcoding either as primary encodes a preference the evidence
does not support. It is now testable the moment both modules exist.

**Denominator either way:** M1 1.0 + M2 1.0 + M5 0.5 + M6 1.0 = **3.5**, with the
damped module swapping. Max composite stays 1.000, since numerator and denominator
carry the same factors (D-039).

---

## D-044 — RVOL multiplies the composite; it is not an E sub-score
**Status:** Accepted · 2026-08-29

RVOL does not contribute to M5's score. It produces a bounded **multiplier** on the
composite, applied after the side is resolved and before M8's additive bias, with
both ends clamped.

**Rationale.** Relative volume is not evidence that a reversal is at hand. It says
how much participation is behind whatever the other modules found — it amplifies or
damps their reading. Scoring it inside category E would let heavy volume alone push
a setup toward a grade, and would let it fill the E category on its own, which is
the D-019 substitution problem in a new place.

**Bounded by `rvolMaxAmp`** (default 0.25, so 0.75x–1.25x). Like M8's cap, it can
move a setup across at most one grade boundary and cannot manufacture a grade from
nothing: the gate resolves the side first, and a bar with no qualifying side gets no
multiplier at all.

**Time-of-day normalised, per D-005's spirit.** The baseline is an EWMA **per clock
slot** (`rvolTodBucketMin`, default 30 min) over prior sessions of that same slot.
Futures volume is strongly U-shaped — heavy at the open and close, thin midday — so
a flat mean would read every open as permanently elevated RVOL. The baseline is read
**before** the current bar is folded into it, or RVOL would be self-referential, and
a slot is unusable until it has seen `rvolWarmN` prior sessions.

---

## D-045 — M5 measures the block's range, not the day's
**Status:** Accepted · 2026-08-29

Exhaustion is `block range / EWMA of that block's typical range`, using M1's auction
blocks (D-038) rather than a 24-hour or RTH-only ADR.

**Why.** A daily or RTH-only ADR would make M5 meaningful only inside RTH and dead
elsewhere — **the exact defect D-038 fixed in M1**, reintroduced one module later
and in the same category. Since M5 is the second E module, that would have left
category E with the same dead zone the block anchoring was built to remove.

The question M5 asks is *"has this auction spent its typical range"*, and under the
block architecture the auction **is** the block.

**Deviation from the source research, stated plainly:** the research says *daily*
ADR. This is a per-block ADR. It is the right unit given a block-anchored engine,
but it is not what the research measured, and a block ratio of 1.2x is not the same
claim as a daily ratio of 1.2x.

**Expected move stays daily**, anchored at the prior session close from the L0
registry — the conventional reading, and it needs no block treatment because the
IV-implied move is a daily magnitude. The EM term is counted only when its
direction agrees with the block-position direction; a disagreement means the two
are describing different moves, and it degrades to ADR-only rather than
contradicting itself.

**Degrade, do not disable.** When the IV symbol does not resolve, the blend
**renormalises** to ADR-only rather than dropping M5. Losing expected-move should
not cost the whole E contribution — a different failure mode from M4's
all-or-nothing self-disable, and deliberately so.

---

## D-046 — A second module in a category cannot move a category count
**Status:** Accepted · 2026-08-29

M5 is active on 1,405 bars and `+3rd cat` did not move by one. **This is not the
D-039 signature.** It is a category-versus-module confusion, and the confusion was
mine to prevent.

### M5 is genuinely reaching the composite

Verified from the source, not inferred: M5 is pushed with `CAT_E`, all four
parallel arrays (`mods`/`wts`/`cats`/`prec`) carry exactly 7 pushes, and
`f_sideEval` receives the `facs` built in the same bar from `prec`. There is no
stale category set and no missing push.

### Why the number could not move

`+3rd cat` counts **distinct categories**, and M1 already fills E. A second module
in the same category adds evidence to the *score* and nothing at all to the *count*.
M5 can only move the gate on bars where **all** of the following hold:

1. L and (Q or F) already present on that side, **and**
2. M1 is **not** active or does not agree with the side, **and**
3. M5 is active and does agree.

`M5 active = 1,405` is the wrong denominator for that question — it counts bars
across the whole chart, most of which have no L+Q at all.

**The diagnostic that settles it** (D-046, added): on the `L+(Q|F)` bars only,
classify who fills E — *neither / M1 only / M5 only / both* — as one
mutually-exclusive array summing to the L+Q count. **Bucket 2, "M5 only", is
exactly the number of bars M5 could have added.** If it is 0, M5 cannot help the
gate and no tuning of M5 will change that.

### The structural reason to expect bucket 2 to be small

M6 fires on the **reclaim**, which moves price *back toward the middle* of the
range. M1 requires price extended from VWAP; M5 requires the block range spent
**and price at a block extreme**. Both E modules want price *away* from the middle
at the moment M6 wants it *returning* to the middle.

This is Finding C from D-037 — M1/M6 anti-correlated in time — and it applies to
M5 for the same reason, because it comes from what category Q *is*, not from how
either E module is built. **The whole E category is anti-correlated with Q by
construction**, so adding E modules cannot fix an E∩Q coincidence problem.

If bucket 2 is near zero, the constraint was never E-availability, and the honest
options are: relax the timing coupling (M6's hold window is the only lever that
already exists), or accept that L+Q+E simultaneity is rare and the gate's third
category should come from C — the one category with no timing relationship to the
reclaim. That is a D-019 change and needs the measurement first.

### M5 state, reconciled and now labelled

The reported buckets summed 1,000 short of bars while the in-Pine check said OK;
`s6 = 1177` (not 177) satisfies all three reported facts simultaneously — the sum,
the active count of 1,405, and the 16.2% ADR-only share. Per D-042 the row was
still packing three counts per cell; it is now **one bucket per row with its name**.

| state | bars | share |
|---|---|---|
| outside block | 1,722 | 14.9% |
| baseline warming | 462 | **4.0%** |
| **in ramp, range unspent** | **7,398** | **64.1%** |
| mid-range, no direction | 557 | 4.8% |
| ACTIVE adr-only | 228 | 2.0% |
| ACTIVE adr+em | 1,177 | 10.2% |

**Warm-up is not the problem — it is 4%.** The dominant state is *the block range
has not been spent*, which is M5 working correctly and rarely, exactly as intended.
The `m5AdrWarm` hypothesis is refuted.

---

## D-047 — M7's gate role and evidence role are separated by conditioning, not by splitting
**Status:** Accepted · 2026-08-29 · answers the "two jobs" question · refines D-004

**The question:** if M7 both fills category C (enabling a grade) and drives the
hostile-context cap (suppressing one), is that coherent?

**The concern is real**, and D-004 makes it sharper rather than softer: D-004
*requires* the sub-score and the hostile flag to be computed independently. Two
independent channels from one module can disagree — so M7 could supply the third
category that enables a grade and then cap the grade it just enabled.

### The resolution is not "split into two modules"

An evidence reading and a regime reading are not two opinions to be arbitrated.
The source research is explicit that **the regime determines how the evidence
should be read**: in range sessions a TICK extreme marks a reversal point, in
trends it confirms momentum. The same number means opposite things in the two
regimes.

So the regime does not sit *beside* the evidence competing with it — it
**conditions** it.

### What was built

| role | statistic | horizon | fills a category? |
|---|---|---|---|
| **Evidence** | point-in-time **extreme** (z-score of internals / macro) | this bar | yes — category C |
| **Gate** | session-level **trend** (ADX, block range vs ADR) | the session | **never** |

**Same symbols may feed both, but never the same statistic.** An extreme is not a
trend, and the two are permitted to disagree — that disagreement is information,
not a contradiction.

**`ctxSeparate` (default on):** a hostile regime **suppresses M7's evidence
entirely**, so C does not fill. The consequence is the point:

> The cap can then only ever act on a grade that **other** categories enabled. The
> pathological case — M7 supplying the third category and then capping the grade it
> just created — cannot arise.

Turning `ctxSeparate` off restores the independent behaviour, for comparison.

### The narrower reading of the {F,C} question

This is **not** a reversal of the earlier objection to routing the third category
into {F, C}. That objection was against *requiring* the third leg to come from the
weakest module (F) or a gate (C) as a matter of preference, and it stands. What the
E-source measurement showed is narrower: on 88% of L+Q bars **no E module is active
at all**, because E is anti-correlated with Q by construction. C is not preferred —
it is the only category with no timing relationship to the reclaim, and therefore
the only one that *can* fill at the fire bar.

### Other requirements, as specified

- **Every `request.security` self-disables.** Four family-mapped slots through
  `f_sec` (`ignore_invalid_symbol`); an unresolved symbol yields `na`, is counted,
  and is reported. `ctxNavail == 0` puts M7 in state 1 (`NO CONTEXT DATA`) rather
  than killing anything. GC's optional fourth slot is an `input.string` so an empty
  default cannot fail picker validation.
- **Consensus, not any-one-source.** Evidence divides by the number of slots that
  *resolved*, so a lone extreme among four sources scores as weak. Context is a
  claim about agreement.
- **The ungated grade is recorded** beside the capped one, in the status table, the
  Data Window, and a mutually-exclusive `capHist` (no grade / uncapped / reduced /
  suppressed) that sums to bars — so what the cap actually costs is measurable
  rather than assumed.
- **D-041 from the start:** `m7State` (6), `ctxAvailHist` (5) and `capHist` (4) are
  each mutually exclusive with their own sum-vs-bars check, displayed one bucket
  per row per D-042.

**Denominator is now 4.0** with M7 at weight 0.5 taking factor 1.0 as the only C
module. Four categories reachable — L, E, Q, C — so `minCats = 3` is satisfiable
without E for the first time.

**Wrong if:** the regime gate turns out to suppress M7 on most bars where L+Q
coincide, which would put C in the same position E is in and mean the gate itself
is the constraint. `m7State` bucket 2 measures exactly that.

---

## D-048 — The main body hit a hard Pine limit; renderers and pure-mutation blocks move into functions
**Status:** Accepted · 2026-08-29

`CE10295: The main body of the script is too long. Try wrapping code in functions.`
Pine caps the number of statements in the **global scope** specifically, and the
project had been written almost entirely at global scope. Nothing was wrong with
the logic — it simply outgrew a limit I was not tracking.

**The renderers were the bulk:** 399 `table.cell` calls across three diagnostic
tables, plus their local derivations. That is what the diagnostic discipline of the
last several rounds cost, and it was worth it — but it belonged in functions.

### What moved, and the rule that decided it

Pine functions **may mutate** a global array (`array.set` / `array.push` — a method
call on a reference) but **may not assign** to a global scalar (`x := …`). That
distinction determined what could be lifted:

| block | statements | why it was safe |
|---|---|---|
| `f_fillStatus` / `f_fillClassTable` / `f_fillGateTable` | 522 | render only; read globals, write nothing |
| `f_buildLevels` | 85 | `array.push` only |
| `f_pushModules` | 35 | `array.push` only |
| `f_telemetryClassify` | 65 | `array.set` only; the scalar counters stayed behind |

**~730 statements moved; the main body fell from ~1,770 to ~1,050.** The scalar
`gf*` counters could not move, because incrementing them is assignment.

### A real defect the mechanical extraction introduced

`f_buildLevels` swallowed the `CLS_TYP` declaration that sat between the registry
and the M6 engine, making a global constant **function-local**. It is read by M1's
barrier check and by the class-breakdown table, so this would have compiled as an
undeclared-identifier error far from its cause — or worse, in a language with
looser scoping, silently.

**The checker could not see it.** `tools/pinecheck.py` tracked declaration *order*,
not *scope*. It now detects **declared-inside-a-function-but-referenced-outside**,
which is exactly this class. Found once by a throwaway audit, now permanent —
the same correction made after the block-local use-before-declare miss.

### If the limit is still exceeded

The next lift is mechanical but larger: convert the scalar `gf*` counters into a
single `gfCnt` array so the whole telemetry block becomes array mutation and can
move wholesale. That is also the D-041 shape — one source, derived views — so it is
a change worth making on its own terms rather than only to satisfy a compiler.

---

## D-049 — One renderer per section: the per-function external-element limit
**Status:** Accepted · 2026-08-29 · follows D-048

`CE10116: f_fillStatus uses 258 external elements. The limit is 254.` External
elements are the values returned by `request.*()` calls, the script's **inputs**,
and user-function parameters — with **int, float and bool counting for two**.

**D-048 traded one limit for another.** Collapsing the whole status table into a
single function concentrated every input reference the engine has into one scope.
The main body got shorter; that function got denser. The limits are on different
axes — statements in the global scope, external elements per function — and
satisfying one by moving code can violate the other.

### The fix

One function per **section**, split along the debug gates that already existed:

- status → `f_stCore`, `f_stSweep`, `f_stStruct`, `f_stVwap`, `f_stM5`, `f_stCtx`
- gate funnel → `f_gtFunnel`, `f_gtProbes`, `f_gtDerived`, `f_gtM5`, `f_gtRvol`,
  `f_gtESrc`, `f_gtM7`

Each section touches only its own module's inputs, so the count distributes instead
of accumulating. The `if <debugFlag>` gates moved to the call sites, which also
means an unused section costs nothing at render time.

### What the mechanical split broke, and the checker gap it exposed

Partitioning the gate table by table **row number** cut straight through
computation blocks: `dM1`…`d26` were computed in one section and displayed in the
next, `bN2` and `m5StateSum` likewise. Each function is now **self-contained** —
it recomputes the handful of `array.get` values it needs, which is cheap and
removes the ordering dependency entirely.

Two checker corrections came out of it:

1. It now recognises that a name declared in function `F` and referenced inside
   function `G` is **not a leak when `G` declares it too** — Pine gives each
   function its own scope, and the first version flagged eight false positives.
   A checker that cries wolf gets ignored, which is how the original blind spot
   survived.
2. Dead locals left behind by the split (`f_gtProbes` was computing fourteen values
   it no longer displayed) are now removed rather than tolerated.

### Two artefacts the split left behind

Dedenting a flagged segment by four also dedented the **function's own trailing
`0`**, dropping a bare `0` to column zero — which terminates the function and turns
the next indented line into an orphan (`CE10009`). A second function ended with two
`0` lines for the same reason. Both were mechanical consequences of the extraction,
invisible to every check I had.

`tools/pinecheck.py` now covers both, and this is the third checker gap found the
same way — by a compiler error my static pass should have caught first:

- **Orphaned indentation**: an indented line must follow another indented line or a
  block opener (`if`/`else`/`for`/`while`/`switch`/`type`/`=>`). This is what
  `CE10009` looks like in the source, and it is precisely what a mechanical
  function extraction leaves behind.
- **Return convention**: a function ending on a *void* call (`table.cell`,
  `array.push`, `array.set`, …) needs an explicit trailing `0`; duplicates are
  flagged too.

Both were written to fire on real defects only. The first drafts raised false
positives — the `type` block body, and every value-returning helper that
legitimately ends on an expression — and were narrowed before being kept, for the
reason recorded in D-049: a checker that cries wolf gets ignored, which is how the
original blind spots survived in the first place.

### The standing tension, stated plainly

The diagnostics have earned their place — D-039, D-046 and D-047 were each settled
by them, and D-042 was settled by fixing how one was *displayed*. But they now
outweigh the engine in statement count and compete with it for two fixed budgets.

If either limit tightens again, the honest move is retiring diagnostics whose
questions are **closed** — the derived-vs-independent cross-check has served its
purpose, and the M6 class breakdown settled D-032 and D-034 — rather than thinning
the engine to make room for instruments that are no longer asking anything.

---

## D-050 — `active` is a score>0 test, so a category fills on arbitrarily weak evidence
**Status:** Open finding · 2026-08-29 · **no change applied**

### 1. The cap is reachable; there were simply no grades

`ctxHostile = regimeTrending or gammaHostile or inBlackout` — computed on a path
that never touches M7's evidence score. `finalGrade` caps whenever `ctxHostile`
**and** a grade exists. So the cap is **not** structurally unreachable.

`CAP EFFECT` reading 0/0/0 means bucket 0 held every bar: **no grade has occurred
yet**, so there was nothing to cap. The row now reads `-- CAP: NO GRADES YET --`
when that is the case, and a `hostile bars` count is displayed beside it so the
cap's *opportunity* is visible independently of its *effect*.

**One asymmetry is by construction and worth stating:** with `ctxSeparate` on, C
can only fill when the regime is **not** trending, and the cap only fires when it
**is** (or on gamma/blackout). So the cap can never act on a grade whose third
category was C. That is exactly D-047's intent — the cap only ever acts on grades
that other categories enabled — and it is a designed property, not a gap.

### 2. The bigger finding: activation is decoupled from score

M7 active on 33.6% of bars is not a loose *threshold*. It is a loose *rule*, and
the rule is shared by every module:

| module | activation condition |
|---|---|
| M1 | `m1DistRaw > 0.0` |
| M5 | `m5Score > 0.0` |
| M6 | `m6Score > 0.0` |
| M7 | `m7Score > 0.0` |
| **M2** | `m2InWindow and m2Dir != 0` — **no score condition at all** |

A single context series at `|z| = 1.51` among four gives
`ctxEvid = 0.01/4 = 0.0025` — and `active = true`. For four independent normal
series, "at least one beyond 1.5σ" is ~44% of bars; correlated macro series bring
that down, and 33.6% is exactly what `ctxZstart = 1.5` predicts.

**So the confluence gate counts categories, and a category fills at score → 0.**
Three "categories" can be three modules scoring 0.001 each. M2 is worse: it fills
the *mandatory* Location category anywhere inside the proximity window, including
the far edge where proximity ≈ 0 and stacking = 0.

The gate reads as strict — Location mandatory, plus an event, plus a third — but
its unit of "filled" is the loosest available. This has been true since D-019 and
was invisible while nothing was grading.

### Proposed fix — not applied

A single input, `catFillMin`, applied uniformly: **a module counts toward its
category only if `score >= catFillMin`.** Keep `active` as-is for the composite, so
D-002's weighting contract is untouched; test the stronger condition only where
category hits are recorded in `f_sideEval`.

That separates two things currently conflated: *contributing score* and *counting
as a leg of the confluence*. Default 0.0 reproduces today's behaviour exactly, so
it can be introduced with no change and raised against measurement.

Raising `ctxZstart` alone would reduce M7's rate but leave the rule intact, and the
same defect would remain in M1, M5, M6 and — most importantly — M2.

### Diagnostics added

- **Third-category source on L+Q bars** (`cSrcHist`): none / E only / **C only** /
  both. Mirrors the E-source array so the two can be compared directly. `C only`
  is the measure of whether C does what E could not.
- **M7 evidence-score distribution** when active, six bands with bucket 0 as
  "not active" so it sums to bars. If the mass sits in `<0.05`, the module is
  active on noise.
- **Hostile-bar count**, so cap opportunity is visible separately from cap effect.

---

## D-051 — `catFillMin`: filling a category is separated from contributing score
**Status:** Accepted · 2026-08-29 · implements the D-050 proposal

A module counts toward its **category** only if `score >= catFillMin`. It still
contributes to the composite either way, so D-002's weighting contract is
untouched. The test is applied in exactly one place — where category hits are
recorded inside `f_sideEval`.

**At the default 0.0 this is provably a no-op.** Every module clamps its score with
`math.max(0.0, …)`, so `score >= 0.0` is true for every reachable value including
exactly 0. Same category hits, same numerator, same denominator. If the numbers
move at 0.0, the implementation changed something else and should be reverted
rather than explained.

**Measured before it is set.** A `FILL RATE vs catFillMin` block reports, per
category, how many bars would fill at **0.00 / 0.15 / 0.30 / 0.45**, plus what the
whole gate would pass at each. The specific question is whether a threshold that
makes C meaningful also starves L — M2 has no score condition at all today and is
the module most exposed. **L is mandatory, so if its fill rate collapses faster
than C's improves, the threshold is wrong regardless of what it does for context.**

The readout carries a **monotonicity assertion**: fill counts must be
non-increasing as the threshold rises. Violating that would mean the probe is
measuring something other than what it claims (D-041's habit applied to a
projection rather than a count).

---

## D-052 — A 95-row diagnostic table is itself a source of error
**Status:** Accepted · 2026-08-29

Two rows incremented **inside the same `if` block**, four lines apart, were
reported with sums of 16 and 4. That is arithmetically impossible: lines 1831 and
1835 of `f_telemetryClassify` sit in one gated block, so `eSrcHist` and `cSrcHist`
must always sum identically, and both must equal `gfStgLQ`.

**This is the fourth transcription discrepancy**, and blaming the reading would be
the wrong conclusion. The instrument grew to 95 rows across three tables while the
only way to read it is a human copying digits off a screen. D-042 established that
an instrument is its arithmetic *plus how it is read*; a table too tall to align a
row against its label fails that test no matter how correct the arithmetic is.

Two changes:

1. **An explicit agreement cell.** The `E src sum vs L+Q` row now prints
   **`AGREE`** when `eSum == cSum == gfStgLQ`, and otherwise prints all three
   values together. One cell replaces three separate readings that had to be
   cross-checked by hand.
2. **Closed diagnostics are retired from view.** The derived-vs-independent
   cross-check (D-042) confirmed the counters sound and its question is closed; it
   is now behind `showCrossCheck`, **default off**, removing 11 rows. The code
   stays for the day a counter is suspected again.

This is the retirement policy D-049 anticipated, applied for the first time: when
the instrument competes with legibility, retire the questions that are **answered**
rather than thinning the engine or asking the reader to be more careful.

---

## D-053 — `catFillMin` set to 0.15 on measurement; NQ preset audit
**Status:** Accepted · 2026-08-29

### The threshold, chosen against the fill-rate table (GC 5m, 11,552 bars)

| | 0.00 | 0.15 | change |
|---|---|---|---|
| **L (M2)** | 178 | 178 | **0.0%** |
| E (M1/M5) | 2318 | 1880 | −18.9% |
| Q (M6) | 1515 | 1459 | −3.7% |
| **C (M7)** | 3879 | 1653 | **−57.4%** |
| GATE pass | 19 | 7 | −63.2% |

**L does not move at all.** The proximity window already filters, so M2's missing
score condition was not the exposure it appeared to be — the concern was right to
raise and wrong on the facts. C absorbs nearly the whole cost, which is exactly
where the score distribution said the noise was (24% of its active bars under
0.05). 0.30 and 0.45 cut into E and Q, which are already scarce.

**The gate gets rarer, and that is the correct direction.** Nineteen passes
containing modules scoring 0.001 are worth less than seven that mean something.
Recording this explicitly because the opposite pressure — tuning until grades
appear — is the standing failure mode of this kind of work.

### NQ preset audit — what differs, and one thing that should but does not

**Already instrument-conditional:** RTH and overnight sessions, reversal windows,
VWAP auction blocks, round-number step (25 index points vs $10), IV symbol
(VIX vs GVZ), all four context symbols and their polarity, and the gamma path.

**Correctly instrument-agnostic:** everything expressed as a ratio or a duration —
VWAP sigma bands, ADR exhaustion ratios, RVOL, ADX, and M6's ATR-fractional
penetration and re-arm bands (D-023).

**The gap: `structProx` is still 8 TICKS.**

| | 8 ticks | as % of daily range |
|---|---|---|
| NQ | 2.00 index pts | 0.571% of ~350 pts |
| GC | $0.80/oz | 1.778% of ~$45 |

**The same tick count is ~3.1× wider on GC than on NQ relative to volatility.**
This is precisely the mistake D-023 identified and fixed in M6 — ticks normalise
the price *increment* across instruments but not the *volatility* — and M2 was
never brought along.

**Consequence for the NQ run:** L will be measured through a window roughly three
times tighter, relative to how far NQ moves, than the GC baseline. **L is
mandatory**, so if NQ's L fill rate comes back far below GC's 178, the tick unit
is a candidate explanation and not a finding about NQ.

**Deliberately not changed before the run.** Altering it now would mean the NQ
funnel measures a different engine than the GC baseline it is being compared
against. The fix — `structProx` as an ATR fraction, mirroring `sweepMinAtr` — is
one input and should follow the measurement, not precede it.

### The NQ unknown that gates everything else

`USI:TICK` / `USI:ADD` / `USI:VOLD` / `USI:TRIN` are not on every TradingView plan.
If they do not resolve, `ctxNavail == 0`, M7 sits in state 1 (`NO CONTEXT DATA`),
**C never fills on NQ**, and the category added specifically to escape the E∩Q
anti-correlation is unavailable on that instrument.

`CTX SYMBOLS OK` answers this in one row and should be read before anything else
in the NQ funnel. If it comes back 0-symbol dominant, the contingency is a macro
context path for NQ (DXY / yields as risk-on-risk-off proxies, or VIX) rather than
breadth internals — the same four slots, different symbols, no structural change.

---

## D-054 — `structProx` becomes a fraction of DAILY ATR; and the sign of the artefact runs the other way

**Status:** implemented. `structProxAtr = 0.010` (was `structProx = 8` ticks).

### The unit

D-053 recorded that 8 ticks is not a unit: it is 2.00 index points on NQ and
$0.80 on GC, which against ~350 pt and ~$45 daily ATRs is 0.0057 and 0.0178 of
daily volatility. `proxDistPx` is now `structProxAtr × atrDaily`, floored at one
tick — a window narrower than a tick admits only an exact match, which is not
proximity. When the daily ATR has not resolved the window is `na` and M2 is
INACTIVE; it does **not** fall back to a tick count, because a fallback in the
other unit reintroduces exactly the incomparability this replaces, and does it
on the early bars nobody inspects.

### Daily ATR, not the chart-TF reference M6 uses

M6 measures an **event inside a bar** — a penetration — so its bands should scale
with the bar, which is why `sweepAtrRef` defaults to Chart TF (D-023). M2 asks a
**location** question: is price *at* the level. That answer must not change when
you switch the chart from 5m to 15m. So M2 takes `atrDaily` directly rather than
following `sweepAtrRef`, and the two modules deliberately do not share a
volatility reference. `atrDaily` already existed for M6; no new `request` call.

### Why 0.010

Two independent arguments land in the same place:

1. **Geometric midpoint** of what 8 ticks actually resolved to (0.0057, 0.0178).
   It widens NQ ×1.76 and narrows GC ×0.57. Anchoring on either instrument's
   current value would preserve one arbitrary tick count as the reference; the
   midpoint preserves neither, which is the point.
2. **Bar-range cross-check.** A 5m bar's range is roughly 1/20th–1/25th of daily
   ATR on both instruments, so 0.010 dATR is about a quarter of a bar's range —
   "at the level". 0.018 would be nearer 40% of a bar, which is "near it".

Resolved equivalents, published in the status table alongside the fraction:
**NQ ≈ 3.5 pts (14 ticks); GC ≈ $0.45 (4.5 ticks).** Read those before trusting
the fraction.

### The correction: the artefact does not explain the L gap

The working hypothesis for the re-run was that NQ's L fill of 698 against GC's
178 was mostly a units artefact. **The sign runs the other way.** D-053 measured
the window as ~3.1× looser on **GC**, not on NQ:

| | 8 ticks as fraction of daily ATR | L fill @0.15 |
|---|---|---|
| NQ | 0.0057 | 698 |
| GC | 0.0178 | 178 |

NQ fills L **3.9× more often through a window 3.1× tighter** relative to its own
volatility. Normalising both to 0.010 therefore **widens** the gap rather than
closing it — NQ's L should rise above 698 and GC's should fall below 178. If the
re-run is read expecting convergence, a growing gap will look like a regression
when it is the predicted result.

**So the L gap is not a units artefact and needs another explanation.** The
leading candidate is **round-number density**, which is instrument-conditional by
design: the NQ step is 25 points against a ~350 pt range (~14 round levels per
day); the GC step is $10 against a ~$45 range (~4.5 per day). That ratio, ~3.1,
is close to the observed L ratio of 3.9 — near enough that the level *registry*,
not the proximity *window*, is where the difference most likely lives. Not
measured: confirming it needs an L-fill breakdown by level class, which is not
built and is not being built pre-emptively.

### Risk being accepted

GC's sample is the thinner of the two (L 178, gate 7 at `catFillMin` 0.15).
Narrowing its window ×0.57 may take the GC gate close to zero and make that
funnel unreadable. That is accepted for one run because the unit has to be fixed
before either funnel means anything. If GC's gate does collapse, the response is
to raise the fraction **as a measured decision on the instrument that
constrains** — not to average the two.

---

## D-055 — Context availability is intermittent, and "not `na`" was never the same as "live"

**Status:** instrument built and wired. Measures only; changes no engine
behaviour. The suspected defect below is deliberately **not** fixed ahead of the
measurement.

### What the NQ run showed

`CTX SYMBOLS OK` on NQ1! 5m, 11558 bars:

| symbols resolving | bars | share |
|---|---|---|
| 0 | 1975 | 17.1% |
| 1 | 3701 | 32.0% |
| 2 | 1782 | 15.4% |
| 3 | 432 | 3.7% |
| 4 | 3668 | 31.7% |

**The standing conditional does not fire.** It was written for the case where
`CTX SYMBOLS OK` came back 0-symbol dominant, i.e. `USI:TICK/ADD/VOLD/TRIN`
unavailable to this account. They resolve — on 82.9% of bars at least one does,
and on 31.7% all four do. So the finding is *not* that NQ's context path is
structurally weaker than GC's for want of data, and no entry claiming that is
warranted. A DXY/VIX substitute is not needed and would not be justified here.

### Why the shape matters more than the totals

3668 bars with all four resolving is close to what the RTH block alone
contributes: blk3 is 0930–1600, 78 bars per session, and 11558 bars over ~44
sessions gives ~3400 RTH bars. That much fits the RTH-only reading.

What does **not** fit it is the middle. Clean session gating produces a *bimodal*
distribution — four symbols inside RTH, zero outside, with the intermediate
buckets near-empty. Instead buckets 1–3 hold **5915 bars, 51% of the sample**.
A gradient of that size is the signature of sources going unavailable *one at a
time and at different rates*, not of a session boundary.

### The mechanism this points at, and why it is worse than absence

`request.security()` with `gaps_off` **holds the last known value forward**. A
symbol that has stopped printing keeps returning a number, so `not na(ctxV)` is
true long after the source went quiet. The z-score is what actually goes `na`,
and it does so only once `ta.stdev` over the lookback reaches zero — which
happens at a different bar for each series depending on how much variance its
window still holds. That produces precisely the observed 4→3→2→1→0 gradient.

If that is what is happening, then during the decay window the engine is not
short of data — it is computing a z-score over a series that is **partly real and
partly a stale repeat of the last RTH print**, and scoring it as live evidence.
That violates the module contract stated in the file itself: *a module that
cannot source its data returns `active = false`, never a fabricated value.* The
composite cannot distinguish fabricated evidence from real evidence, which is the
same class of fault as D-039, arriving through a different door.

This would be the **third appearance of the D-038 dead-zone pattern**, in a third
module — but with a sharper edge than the first two. M1's and M5's dead zones
were *absence*: the module knew it had nothing. This one is *stale presence*: the
module cannot tell.

### The instrument

Four extra `request.security` calls fetch each context symbol's own bar **time**
(budget: 10 of ~40 used). A source is LIVE on a bar if its bar time advanced;
otherwise the value is held forward. The test is "advanced" rather than "equals
the chart bar time" so it stays correct when `ctxTF` is below the chart TF; it
under-reports if `ctxTF` is above it, which the 5m default on a 5m chart is not.

New table `ct`, top-left, six columns by eighteen rows — its own table rather
than nineteen more rows on `gt`, which is at 88 of 95 and which D-052 already
recorded as a source of transcription error in its own right. Three counts per
(slot, auction block), because the **gaps between them are the diagnosis**:

| | meaning | what it isolates |
|---|---|---|
| RAW | the series returned a number, hold-forward included | whether the symbol resolves for this account at all |
| LIVE | the source's own bar time advanced | whether it actually printed here |
| Z | the z-score resolved — what the engine consumes | whether the lookback, not the data, is the constraint |

Reading it:

- **RAW 0 in every block** → the symbol is unavailable. This is the case the
  standing conditional was written for, per-symbol rather than in aggregate.
- **RAW high, LIVE low** → session-bound symbol, and the engine has been reading
  staleness as evidence. Confirms the mechanism above.
- **LIVE high, Z low** → the data is there and `ctxZlookMin` is the constraint.
  A different problem with a different fix.

Blocks are the existing M1 auction blocks (`m1BlkId`), so context availability is
reported on the same partition M1's dead-zone fix used — the two are directly
comparable, which is the point of reusing it. Block 0 is "outside every block".

### Two observations recorded but not acted on

1. **M7 is regime-gated on ~72% of NQ bars** (state 2 ≈ 8351 of 11558). Whatever
   the availability finding turns out to be, the regime gate suppresses M7 on far
   more bars than missing data does. Not touched — `ctxSeparate` and `adxTrend`
   are unmeasured placeholders and tuning them now would confound the
   availability measurement.
2. **The reported M7 state counts overshoot bars by 29** (1975 + 8351 + 0 + 1261
   = 11587 vs 11558), while the engine's own sum-vs-bars cell read OK. So one
   hand-copied figure is off by 29. It changes nothing — regime gating is ~72%
   either way — and it is the fifth instance of the D-052 pattern, which is why
   the OK/BAD cells exist and why `ct` carries its own `blk bars sum vs bars`
   row.

---

## D-056 — The registries were comparable all along, and the round-number hypothesis was never live

**Status:** verified in code; instrument built for what remains.

### The verification

`sRound = input.bool(false, "Round numbers", group = grpL0)`

It is a **single global input**, it defaults to **false**, and there is no
instrument branch anywhere — `isGC` never touches it. The only gate on the push is
`if sRound` at the registry build. Round numbers are therefore **absent from the
registry on both instruments at defaults**, and both runs used defaults.

So the registries *were* comparable. On both NQ and GC the registry is the same
twelve classes — PDH/PDL, PDC, ONH/ONL, IBH/IBL, ORH/ORL, RTHo, SwH/SwL — with
identical composition and identical count. The suspected asymmetry does not exist.

### What this costs D-054

**It kills the round-number-density hypothesis outright, and the fault is mine.**
D-054 offered "NQ has ~14 round levels per day against GC's ~4.5" as the leading
explanation for the L gap while those levels were not in the registry at all on
either instrument. The predicted ratio of 3.1 against an observed 3.9 was a
coincidence between two numbers that were never connected. This is the same shape
as D-039: reasoning in detail about a component that was not in play, and finding
the arithmetic agreeable enough not to check whether it was switched on.

The check cost one `grep` and required no chart run. It should have preceded the
hypothesis, not followed it.

### The instrument gap that made this readable in two ways

The M6 class table renders a disabled class and an enabled-but-never-penetrated
class **identically** — a row of zeros. Its only annotation, `[no-sw]`, is about
*sweepability*, not registry membership. So "Rnd+ / Rnd- show as off with zero
counts" and "Rnd+ / Rnd- are enabled but nothing has happened at them" were
indistinguishable from the table, on either instrument.

Fixed: classes absent from the registry now render `(NOT IN REG)`, and the new L
table carries an explicit `in reg` column. **Expect Rnd+ / Rnd- to read
`(NOT IN REG)` on NQ as well as GC** — that is the confirmation, and if NQ instead
reads `yes`, `sRound` was changed from default and the comparison genuinely was
unequal.

### So what is left to explain

Registry composition is identical and round numbers are out on both. The window is
now a common fraction of each instrument's own volatility. The remaining candidate
is **how tightly those twelve levels sit around price, relative to daily ATR** —
a property of the instrument's structure, not of the registry or of the window.

`lNearHist` measures exactly that: the distance from close to the nearest level of
any class, in daily-ATR units, bucketed. It is **window-invariant** — it describes
the registry's geometry and survives any future change to `structProxAtr`, which
neither the fill counts nor the exposure counts do. If NQ's distribution is shifted
left of GC's, the L gap is explained and quantified in a unit that does not depend
on the choice being tested.

Alongside it, per class: `win bars` (exposure — counted once per class per bar, so
duplicate levels at one price cannot inflate it) and `L fills` (attribution — the
class of the *nearest* level on bars where L actually fills). Exposure and
attribution are kept apart for the D-034 reason: a class that is near price
constantly gets more chances, and raw fill counts do not distinguish that from a
class that earns its hits.

### A caution on the post-D-054 NQ numbers

L fill went 698 → 2189 (×3.14) and gate 23 → 87 (×3.78) while the window widened
×1.76. **The superlinearity is not evidence of level clustering.** Widening the
window also raises `m2Prox` for every bar already inside it — `prox = 1 − d/window`
— and raises `m2Stack` by admitting more classes, so a widened window lifts scores
above `catFillMin` on bars that were already in the window and failing the score
test. The score threshold and the window are not independent. `lNearHist` is
immune to this, which is why it is the statistic to read rather than the ratio.

87 is not a result and is not being read as one.

---

## D-057 — Load-bearing readings move to the Data Window

**Status:** implemented. The `ct` table stays; the Data Window is authoritative.

Chosen over widening the `ct` table because the two options are not equivalent in
kind. A roomier table makes the instrument more forgiving of a misread; the Data
Window emits exact values and **removes the reader from the measurement path**.
Four transcription discrepancies are on record (D-052), each reconciled
arithmetically rather than by assertion, and the staleness question is the one
whose answer decides whether M7's entire contribution comes out of the record. It
should not depend on reading compressed rows off a chart.

The table is not removed. It stays as the visual cross-check and keeps its
`blk bars sum vs bars` OK/BAD cell; where the two disagree, **the Data Window
wins**.

### The constraint that shaped the layout

Pine caps a script at **64 plots**, with no parameter to raise it, and 34 were
already committed. The 48 per-(slot, block) cells do not fit. The split:

- **Per-symbol totals, all four slots** — `c1..c4 RAW / LIVE / Z`, 12 plots.
  These answer the blocking question on their own: RAW high with LIVE low is
  hold-forward staleness, whatever the block breakdown says.
- **Per-block breakdown, one slot at a time** — `sel b0..b3 RAW / LIVE / Z`, 12
  plots, driven by `dwCtxSlot`. This answers *when*, at the cost of four reads.
- `00 BARS` and `00 selSLOT` — the denominator, and the selector echoed back so a
  reading cannot be mis-attributed to the wrong symbol.

Total 60 of 64. Documented in `PINE_LIMITS.md` §10, and `pinecheck.py` now counts
plots and warns from 56 upward — the limit is the kind that arrives unannounced,
because diagnostics are added one or two plots at a time.

These are **cumulative counters**: the value at the **last bar** is the total, not
the value at the cursor.

### What the reading decides

- **RAW ≈ bars, LIVE ≪ RAW** → the source is session-bound and the engine has been
  computing z-scores over held-forward prints. M7's numbers are contaminated: the
  1261 ACTIVE count, the whole C fill-rate column, and every gate reading that
  depended on C come out of the record for both instruments. `lNearHist` would be
  the only uncontaminated statistic in the build, because it touches nothing from
  `request.security` beyond the daily ATR.
- **RAW ≈ LIVE, Z ≪ LIVE** → the data is live and `ctxZlookMin` is the constraint.
  A different defect, and M7's history stands.
- **RAW = 0 for a slot** → that symbol is unavailable, per-symbol rather than in
  the aggregate the `CTX SYMBOLS OK` bucket count gave.

Nothing downstream is being read until this resolves. `lNearHist` and the NQ gate
count of 87 are held, per the same reasoning: if M7 was scoring hold-forward data,
the NQ gate numbers are contaminated through the C category and re-reading them
now would only add a second layer on top of a suspect first.

---

## D-058 — M7 was scoring held-forward prints. Its numbers are withdrawn, and the z-score is rebuilt on live samples only

**Status:** confirmed by measurement; fixed at the source. All prior M7 readings
are withdrawn from the record.

### The measurement

NQ1! 5m, 10014 bars, Data Window at the last bar:

| slot | RAW | LIVE | Z |
|---|---|---|---|
| c1 TICK | 10014 | 2809 | 3599 |
| c2 ADD | 10014 | 2809 | 3599 |
| c3 VOLD | 10014 | 2809 | 5495 |
| c4 TRIN | 10014 | 2808 | 5263 |

Slot 1 by auction block:

| block | RAW | LIVE | Z |
|---|---|---|---|
| b0 outside | 432 | **0** | **432** |
| b1 Asia | 4398 | **1** | **360** |
| b2 Europe/pre | 2376 | **0** | 0 |
| b3 RTH | 2808 | 2808 | 2807 |

The blocks reconcile exactly with the slot totals — RAW 432+4398+2376+2808 =
10014, LIVE 0+1+0+2808 = 2809, Z 432+360+0+2807 = 3599 — so the instrument itself
is sound and the numbers are the data, not an artefact of the counting.

**RAW equals the bar count on every slot while LIVE is 28.0%.** The internals are
session-bound and everything outside RTH was a repeated print. Worse, **Z exceeds
LIVE on every slot**: 790 excess z-scores on TICK and ADD, 2686 on VOLD — between
28% and 95% more evidence than there were live observations to support it. The
cleanest single indictment is b0: **432 bars, zero live prints, 432 z-scores.**

### Why the z-score inflated rather than merely persisted

Holding a value forward does not just repeat the last reading, it **collapses the
standard deviation** of the window it sits in. `ta.stdev` over a window that is
mostly one repeated number returns a small σ, and every subsequent deviation
divided by that small σ reads as an extreme. So the stale window did not produce
neutral evidence — it produced *systematically overstated* evidence, and M7's
`ctxEvid` is a function of `|z|`. The direction of the bias is toward more
context, more C fills, more third categories, more gates.

### Withdrawn

Every M7 figure in this build and the previous one comes out of the record:

- the **1261 ACTIVE** count and the M7 state distribution
- the entire **C fill-rate column** at every threshold, on which `catFillMin`
  0.15 was partly chosen (D-053)
- the **third-category source** split (`cSrcHist`) wherever C supplied it
- **every gate reading downstream of C** on NQ, including `GATE would pass` 23 and
  the post-D-054 87
- the M7 evidence-score distribution and the cap-effect counts

Not withdrawn: anything that never touched `request.security` at intraday TF —
M1, M2, M5's ADR term, M6, the level registry, `lNearHist`. The D-054 units
finding stands, since it is arithmetic about ticks and ATR.

### GC is suspect, not clean

GC's context path is `TVC:DXY`, `TVC:US10Y`, `TVC:US02Y` (slot 4 is empty by
default, so GC ran on three slots, not four). Whether those are session-bound the
same way **has not been measured, and is not being assumed in either direction** —
asserting that a macro series trades 24 hours would be exactly the reasoning that
produced the round-number error in D-056. The same Data Window readout answers it
on the GC re-run. Until then GC's C column is **suspect**, and if LIVE comes back
below RAW there it comes out too.

`m5IV` also comes through `request.security`, but at **daily** timeframe, where
holding one value across the day is the intended semantics rather than a defect.
The fault requires an intraday TF, where holding forward misrepresents intraday
variation. M5 is unaffected.

### The fix

`ta.sma` / `ta.stdev` over the raw series are gone. Statistics are now accumulated
from **live samples only** into an explicit per-slot buffer; a bar that did not
print contributes nothing to the window and receives no z-score.

Gating only the current bar would not have been enough, and this is the part that
is easy to get wrong: **the lookback is contaminated too.** A z-score taken at
10:00 against a window reaching back into the overnight hold is measured against a
distribution that is mostly one repeated number. Both ends had to move.

Two implementation points that would otherwise bite:

- The buffer is pushed only on `barstate.isconfirmed`. Pine re-executes on every
  tick of the forming bar, and an unguarded push would insert the same bar
  repeatedly and weight the newest observation by tick count.
- A **full** window of live samples is required before any z is emitted. A
  z-score over a part-filled window is the same fabricated-confidence failure in
  a smaller form.

### The residual choice, surfaced rather than decided

A continuous live-only window means the z-score at the cash open is measured
against the last 120 printing minutes — the tail of the *previous* session. That
spans the overnight gap, which is what D-038 refused to do for VWAP.

The alternative clears the window whenever the source resumes after a gap, making
every z-score within one continuous printing session — at the cost of blanking the
first `lookback` live bars of every session, which is the cash open, the highest-
value reversal window on NQ.

Exposed as `ctxZreset`, **default off**, because blanking the open is a certain
cost against a speculative one. This is a measurement to run, not a preference to
reason about, and hardcoding either side would encode a judgement that has not
been earned.

### The invariant that should have caught this

**Z can never exceed LIVE in any cell.** It is one comparison, it holds by
construction after the fix, and it would have surfaced this without a four-round
investigation. Added to the `ct` table (`cells with Z > LIVE`, OK/BAD over all 16)
and to the Data Window as `00 zGTlive`.

The general form is worth stating: **every counter derived from
`request.security` at an intraday timeframe needs a liveness denominator**, and
the check is that the derived count cannot exceed it.

### The constraint this establishes — already measured, not predicted

NQ's internals print on **2809 of 10014 bars, 28.0%**, and essentially all of it is
the cash session. So **category C is structurally available on roughly a quarter of
NQ bars, and only during RTH.** That is not a defect and cannot be tuned away.

It bears directly on why C was built. C was added because E is anti-correlated
with Q by construction — M6 fires on the reclaim, while E needs price away from the
middle — leaving 88% of L+Q bars with no E module active. C was the escape from
that. **The escape is unavailable outside the cash session**, which is where a
large share of NQ bars sit. The E∩Q problem is therefore unsolved overnight rather
than solved, and the earlier readings only looked otherwise because the gap was
being filled with repeated prints.

---

## D-059 — The consensus divisor is not comparable, between instruments or between bars

**Status:** recorded, not fixed. Nothing built until D-058's invariant is confirmed
and GC has been re-read.

`ctxEvid = min(1, |ctxSigned| / ctxNavail)` — divided by the number of slots that
resolved. The intent, stated in the code, is that *"a lone extreme among four
sources scores as weak consensus rather than strong evidence."* Two things break
that intent, and neither was visible until the slot asymmetry was raised.

### Between instruments: GC runs three slots, NQ runs four

`ctxGC4` defaults to an empty string, so GC's fourth slot never resolves. The
divisor is 3 on GC and 4 on NQ, and the same evidence therefore does not mean the
same thing:

| | lone extreme (term 1.0) | term a lone slot needs to reach `catFillMin` 0.15 | one slot dissenting, rest at 1.0 |
|---|---|---|---|
| NQ, 4 slots | 0.250 | 0.60 | 0.500 |
| GC, 3 slots | 0.333 | 0.45 | 0.333 |

**A lone extreme scores 33% higher on GC**, and needs a quarter less raw extremity
to fill category C. Dissent is also weighted differently: one disagreeing slot
costs a third of the signal on GC against a quarter on NQ, so GC is simultaneously
*easier to fill* and *easier to veto*.

This is the same class of fault as `structProx` in ticks (D-054): a quantity that
looks instrument-neutral because the formula is identical, while an arbitrary
configuration difference — there a tick size, here an empty input — makes the same
number mean different things on the two products. It was not caused by the D-058
fix; it has been true since M7 shipped, and every cross-instrument C comparison
made so far inherits it.

### Between bars: the D-058 fix made the divisor vary within an instrument

This one **is** a consequence of the fix, and it should be on the record as such
rather than discovered later.

`ctxNavail` now counts slots with a *live* z-score. Liveness is per-symbol and the
buffers fill independently, so within one session the divisor can be 1, 2, 3 or 4
as slots come online — and identical breadth readings score differently depending
on how many of their neighbours happened to be warm. The old code had the same
divisor logic, but the divisor was near-constant because held-forward values kept
every slot permanently "available". **Removing the fabricated availability exposed
a variance the fix did not create but did make visible.**

The first bars after each cash open are where this bites hardest, since that is
when buffers are refilling — and it is also the highest-value reversal window.

### Options, none taken

1. **Fill GC's fourth slot** with a real symbol, so both instruments run four.
   Cheapest, but it is a symbol choice that needs its own justification and the
   research does not obviously supply a fourth for gold.
2. **Fixed divisor of 4** regardless of what resolved. Makes the scale identical
   everywhere, at the cost that GC can never reach `ctxEvid = 1.0` and that a
   partially-warm NQ is scored as if the missing slots dissented — which is not
   what a missing slot means.
3. **Require a minimum slot count** before M7 activates at all, so the divisor is
   at least stable above a floor. Costs the warm-up window entirely.
4. **Accept and document**, treating `ctxEvid` as within-instrument only and never
   comparing C fill rates across products.

Recommending none of them here. The choice depends on the GC liveness numbers,
which have not been read: if GC's macro series turn out to be session-bound too,
option 1 changes character completely, because a fourth GC slot would be dark for
the same hours as the other three.

---

## D-060 — `ctxZreset` stays off, and the reasoning is recorded rather than settled

**Status:** deliberately undecided. Default off.

The tradeoff is in D-058. What is added here is the reasoning for leaving it, so
that the choice is not silently re-litigated later:

> Blanking the cash open is a **certain** cost. The overnight-gap contamination is
> **bounded by the lookback window** rather than structural — it affects the first
> `ctxZlookMin` worth of live bars after a gap, and decays out, whereas a reset
> removes the same window from *every* session unconditionally.

A bounded, decaying cost against an unbounded, recurring one. That is the argument
for the current default, and it is an argument rather than a measurement — which
is precisely why the input exists and why this entry does not close.

What would settle it: M7's contribution to graded setups in the first
`ctxZlookMin` of the session, with the flag off and on. That measurement needs
grades that are not contaminated, so it queues behind the re-runs.
