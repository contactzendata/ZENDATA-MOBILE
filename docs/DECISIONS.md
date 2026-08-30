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
**Status:** Accepted · 2026-08-29

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

## D-031 — PROPOSED: per-class re-arm gate (consumption). **Not implemented**
**Status:** Proposed · 2026-08-29 · awaiting post-D-030 numbers

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

**Do not implement until** the post-D-030 class breakdown is in. If the intact fix
alone brings the rate into single digits per session, this rule may be unnecessary
complexity — and it is easier to add it later than to disentangle it from a fix
that was already sufficient.
