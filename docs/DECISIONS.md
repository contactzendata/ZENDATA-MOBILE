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
