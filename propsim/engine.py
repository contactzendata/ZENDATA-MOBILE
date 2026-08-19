"""
Monte Carlo engine for prop-firm evaluation pass probability.

Resamples WHOLE TRADING DAYS (not individual trades) so that:
  - intra-day trade order and clustering are preserved
  - the daily loss limit can be modeled at all

Known limitation: day resampling is i.i.d., so it cannot reproduce multi-day
losing streaks. A strategy that bleeds through trending weeks will score
better here than it does in reality. Treat the pass probability as an
optimistic upper bound, not a forecast.

RULESET DEFAULTS BELOW ARE UNVERIFIED. They are carried over from the original
prototype and have NOT been checked against current Topstep documentation.
Verify them (or pass your own `Ruleset`) before showing any output to a user.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Sequence

import numpy as np

# Outcome labels. `PASS` is the only success; everything else is a failure mode.
PASS = "PASS"
TRAILING_DRAWDOWN = "trailing_drawdown"
TIMEOUT = "timeout"

Day = np.ndarray  # one trading day: 1-D array of trade P&Ls, in order


@dataclass(frozen=True)
class Ruleset:
    """Evaluation rules for a single prop-firm account.

    UNVERIFIED defaults — see module docstring.

    start:       account starting balance
    target:      profit target (over `start`) required to pass
    trail:       trailing max drawdown, measured from the equity high-water mark
    daily_loss:  daily loss limit. Hitting it LOCKS OUT THE DAY; it is not a
                 failure, and the evaluation continues the next day.
    min_days:    minimum number of trading days before a pass can be awarded
    consistency: the best single day must be <= this share of total profit
    max_days:    give-up horizon; reaching it is a `timeout`
    """

    start: float = 50_000.0
    target: float = 3_000.0
    trail: float = 2_000.0
    daily_loss: float = 1_000.0
    min_days: int = 5
    consistency: float = 0.50
    max_days: int = 60

    def __post_init__(self) -> None:
        for name in ("start", "target", "trail", "daily_loss"):
            if getattr(self, name) <= 0:
                raise ValueError(f"Ruleset.{name} must be positive, got {getattr(self, name)!r}")
        for name in ("min_days", "max_days"):
            if getattr(self, name) < 1:
                raise ValueError(f"Ruleset.{name} must be >= 1, got {getattr(self, name)!r}")
        if self.min_days > self.max_days:
            raise ValueError(
                f"Ruleset.min_days ({self.min_days}) exceeds max_days ({self.max_days}); "
                "no evaluation could ever pass"
            )
        if not 0 < self.consistency <= 1:
            raise ValueError(
                f"Ruleset.consistency must be in (0, 1], got {self.consistency!r}"
            )


@dataclass(frozen=True)
class EvalResult:
    """Outcome of one simulated evaluation.

    outcome:    PASS, TRAILING_DRAWDOWN, or TIMEOUT
    days:       trading days elapsed when the evaluation ended
    equity:     account equity at the end
    threshold:  the trailing-drawdown threshold at the end (after ratcheting)
    high_water: highest intra-day equity reached
    day_pnls:   realized P&L of each completed day, in order
    """

    outcome: str
    days: int
    equity: float
    threshold: float
    high_water: float
    day_pnls: list[float] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.outcome == PASS


def run_eval_sequence(day_sequence: Iterable[Day], rules: Ruleset) -> EvalResult:
    """Run an evaluation over an explicit, ordered sequence of trading days.

    This is the deterministic core: no sampling happens here, so a caller (or a
    test) controls exactly which day is traded when. `run_eval` wraps it with
    resampling.

    The sequence is consumed lazily and truncated at `rules.max_days`.
    """
    equity = rules.start
    threshold = rules.start - rules.trail
    high_water = rules.start
    day_pnls: list[float] = []
    elapsed = 0

    for day in day_sequence:
        if elapsed >= rules.max_days:
            break
        elapsed += 1

        intraday, day_pnl = equity, 0.0

        for trade in day:
            intraday += trade
            day_pnl += trade
            high_water = max(high_water, intraday)
            # The trailing threshold ratchets up with the high-water mark, then
            # locks permanently once it reaches the starting balance.
            threshold = min(max(threshold, high_water - rules.trail), rules.start)

            if intraday <= threshold:
                return EvalResult(
                    TRAILING_DRAWDOWN, elapsed, intraday, threshold, high_water,
                    day_pnls + [day_pnl],
                )
            if day_pnl <= -rules.daily_loss:
                # Daily loss limit hit: locked out for the rest of THIS DAY.
                # The evaluation is not over — trading resumes tomorrow.
                break

        equity = intraday
        day_pnls.append(day_pnl)
        profit = equity - rules.start

        if profit >= rules.target and len(day_pnls) >= rules.min_days:
            if max(day_pnls) <= rules.consistency * profit:
                return EvalResult(PASS, elapsed, equity, threshold, high_water, day_pnls)
            # Consistency rule unmet -> keep trading to dilute the best day.

    return EvalResult(TIMEOUT, elapsed, equity, threshold, high_water, day_pnls)


def resample_days(
    days: Sequence[Day], count: int, rng: np.random.Generator
) -> Iterator[Day]:
    """Yield `count` days drawn i.i.d. with replacement from `days`."""
    if len(days) == 0:
        raise ValueError("cannot resample from an empty set of trading days")
    for _ in range(count):
        yield days[rng.integers(len(days))]


def run_eval(
    days: Sequence[Day], rules: Ruleset | None = None, rng: np.random.Generator | None = None
) -> EvalResult:
    """Simulate one evaluation by resampling whole days from `days`."""
    rules = rules or Ruleset()
    rng = rng if rng is not None else np.random.default_rng()
    return run_eval_sequence(resample_days(days, rules.max_days, rng), rules)


@dataclass(frozen=True)
class SimulationResult:
    """Aggregate of `n` simulated evaluations."""

    outcomes: Counter
    days_to_pass: list[int]
    n: int

    @property
    def pass_rate(self) -> float:
        return self.outcomes[PASS] / self.n if self.n else 0.0

    def rate(self, outcome: str) -> float:
        return self.outcomes[outcome] / self.n if self.n else 0.0

    @property
    def median_days_to_pass(self) -> float | None:
        if not self.days_to_pass:
            return None
        return float(np.median(self.days_to_pass))


def simulate(
    days: Sequence[Day],
    rules: Ruleset | None = None,
    n: int = 10_000,
    rng: np.random.Generator | None = None,
) -> SimulationResult:
    """Run `n` independent evaluations and aggregate the outcomes."""
    rules = rules or Ruleset()
    rng = rng if rng is not None else np.random.default_rng()
    outcomes: Counter = Counter()
    days_to_pass: list[int] = []

    for _ in range(n):
        result = run_eval(days, rules, rng)
        outcomes[result.outcome] += 1
        if result.passed:
            days_to_pass.append(result.days)

    return SimulationResult(outcomes, days_to_pass, n)


def size_sweep(
    days: Sequence[Day],
    rules: Ruleset | None = None,
    multipliers: Sequence[int] = (1, 2, 3, 4),
    n: int = 6_000,
    rng: np.random.Generator | None = None,
) -> dict[int, SimulationResult]:
    """Position-size sensitivity: identical expectancy, different sequence risk.

    Scaling every trade by `m` scales expectancy and variance together, but the
    ruleset's limits (drawdown, daily loss, target) do not scale — so the pass
    probability is not invariant.
    """
    rules = rules or Ruleset()
    rng = rng if rng is not None else np.random.default_rng()
    return {
        m: simulate([day * m for day in days], rules, n, rng) for m in multipliers
    }
