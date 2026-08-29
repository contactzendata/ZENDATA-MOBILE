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
**Status:** Provisional · 2026-08-29

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
