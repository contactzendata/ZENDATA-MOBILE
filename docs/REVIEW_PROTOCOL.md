# M6 Blind Review Protocol

**Written before the results, deliberately.** The interpretation bands in §7 are
pre-registered so the outcome cannot be rationalised after the numbers arrive. If
they turn out to be the wrong bands, change them *and say so* — do not
reinterpret a result against bands invented once it is known.

**What this can establish:** whether M6's fires correspond to events a
discretionary reader would mark, and what kind of event it systematically misses.

**What it cannot establish:** whether marking those events profitably is possible.
This measures agreement with a human reader, not edge. A high agreement rate means
M6 approximates your judgement; it says nothing about whether your judgement makes
money.

---

## 1. Why blind

Reading the engine's marks and asking *"would I have taken that?"* is a much weaker
test, because the marks anchor the judgement. Marking first, independently, is the
only way to get an honest **yours-only** bucket.

**Use Bar Replay.** Marking reversals on a completed chart is trivially easy in
hindsight and will inflate yours-only with points nobody could have called live.
Every mark must be placed with the right-hand side of the chart hidden. This is the
single largest threat to the validity of the exercise.

---

## 2. Sample

- **5 sessions each on GC 5m and NQ 5m.** Recent sessions only — sweep labels
  accumulate against the 500-label budget, so older windows may have had fires
  evicted, and an empty old session must not be read as "no fires".
- Expect roughly 10 M6 fires per session, so ~50 per instrument.

**Sample limits, stated up front.** At n ≈ 50 the 95% interval on a proportion is
roughly ±14 points. That is enough to detect gross failure (recall near zero,
direction inverted) and not enough to distinguish 30% from 40%, or to compare GC
against NQ on anything but a large gap. Do not tune parameters on a difference this
sample cannot resolve.

---

## 3. Pass 1 — blind marking

Settings → **`0 - Blind review` → BLIND: hide all drawings**. The status table
header will read `** BLIND **`. Both diagnostic tables stay live; nothing is drawn.

For every point you would mark as a reversal, record:

| Field | Values |
|---|---|
| **Time** | session date + clock time of the bar |
| **Direction** | `L` (fading a low) or `S` (fading a high) |
| **Conviction** | `H` would have taken it · `M` would have watched it · `L` noted it |

Clock time matters beyond identification: if misses cluster at the RTH open or into
the London/NY overlap, that is a **session-structure** gap and points at the M6
definition rather than at which module comes next.

---

## 4. Pass 2 — overlay and match

Turn BLIND off. Each label reads:

```
v PDH          ^ = swept low (long)   v = swept high (short)
0.72           score
14tk 2b        penetration in ticks, bars to reclaim
```

Opacity is graded by score: solid ≥ 0.70, mid ≥ 0.45, faint below.

### The matching rule, and why it is asymmetric

**M6 fires at the reclaim bar, which is structurally after the extreme.** A human
marks the turn. Matching on the same bar would score genuine agreements as misses.

A fire **matches** a mark when both hold:

1. **Time:** fire bar within `[mark − 2, mark + reclaimBars + holdBars]`.
   On 5m with current defaults (reclaim 10m → 2 bars, hold 15m → 3 bars) that is
   **−2 to +5 bars**. Read the resolved bar counts off the status table rather than
   assuming; they change with timeframe.
2. **Price:** the swept level lies within **1× the M6 ATR reference** of the marked
   price. This stops a mark pairing with an unrelated simultaneous fire on a distant
   level.

Match on location first. Direction is *not* a matching criterion — it is the split
below.

---

## 5. Buckets

| Bucket | Definition | Visible to diagnostics? |
|---|---|---|
| **Matched–agree** | fire matches a mark, same direction | yes |
| **Matched–oppose** | fire matches a mark, **opposite** direction | yes |
| **M6-only** | fire with no matching mark | yes |
| **Yours-only** | mark with no matching fire | **no — structurally uninstrumentable** |

**Matched–oppose is worse than a miss** and would otherwise hide inside a good
agreement number: the engine found the right location and read the wrong side.

**Yours-only cannot be instrumented in Pine at any effort level.** A missed event
leaves no trace in any counter, because detecting it requires exactly the judgement
the engine is trying to approximate. It is the reason this exercise exists.

---

## 6. Tagging — this is what selects the next module

### Every yours-only miss gets one tag

| Tag | Meaning | Implicates |
|---|---|---|
| `EXT` | extended from the mean / far from VWAP | **M1** |
| `EXH` | session range spent, climax volume, RVOL | **M5** |
| `VOL` | profile structure — POC, VAH/VAL, HVN/LVN, naked POC | **M3** |
| `FLOW` | absorption or delta read | **M4** (approximation only — see PINE_LIMITS §2) |
| `CTX` | internals or macro | **M7** |
| `LVL` | a level the registry does not carry | **registry gap, not a module** |
| `DEF` | a sweep M6 *should* have caught and did not | **M6 definition defect** |
| `NONE` | none of the above; pure price action | — |

`DEF` and `LVL` are the important ones to keep separate from the rest: they route
work back into M6 and L0 rather than into a new module. A pile of `DEF` means the
sweep definition is wrong and nothing should be built on it yet.

### Every M6-only fire gets one tag

| Tag | Meaning |
|---|---|
| `OK` | actually a fine setup, you simply did not mark it — a *human* miss, not an engine error |
| `ROT` | ordinary rotation, no failed auction |
| `TREND` | with-trend continuation; fading it is wrong |
| `NOLVL` | the level was not meaningful |
| `LATE` | reclaim confirmed too late to be actionable |

`OK` matters: without it, every unmarked fire looks like a false positive, and
precision is understated.

---

## 7. Reading the result — pre-registered

Report per instrument:

- **Recall (H-conviction)** = matched-agree on `H` marks ÷ all `H` marks
- **Recall (all)** = matched-agree ÷ all marks
- **Precision** = (matched-agree + `OK`-tagged M6-only) ÷ all fires
- **Opposite-read rate** = matched-oppose ÷ all matched
- **Miss-tag distribution** over yours-only

Then:

| Condition | Meaning | Action |
|---|---|---|
| Opposite-read > ~10% of matched | direction logic is wrong somewhere | **investigate first — worse than low recall** |
| `DEF` is the largest miss tag | the sweep definition is the problem | **fix M6; build nothing on top** |
| Recall (H) < ~1/3 | M6 misses most of what a reader finds tradeable | **M6 definition changes before any new module** |
| Precision < ~1/4 | too much noise to review | tighten M6 |
| Recall (H) acceptable **and** misses concentrate on one module tag | the engine works and has a known blind spot | **that module goes next**, overriding the planned order |
| Misses spread evenly across tags | no single module closes the gap | build in planned order, expect slow gains |
| `LVL` is large | the registry is missing structure | extend L0, not the module list |

**The module order in `SPEC.md` is not binding.** It was written before any
evidence. If the misses say M3 before M1, that is the answer.
