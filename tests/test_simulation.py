"""Distribution-level tests: many resampled evaluations, aggregate behavior."""

import numpy as np
import pytest

from propsim.engine import (
    PASS,
    TIMEOUT,
    TRAILING_DRAWDOWN,
    Ruleset,
    run_eval,
    simulate,
    size_sweep,
)

RULES = Ruleset()


def days(*values: float) -> list[np.ndarray]:
    return [np.array([v], dtype=float) for v in values]


# A losing strategy: half the days make +100, half lose -400, so expectancy is
# -150/day. Passing would need +3,000 net inside 60 days — at least 30 winning
# days with no more than 6 losers among them — while surviving a 2,000
# drawdown. That is not merely unlikely, it is a ~1e-13 event, so asserting an
# exact zero here is not a flaky assertion.
NEGATIVE_EXPECTANCY = days(*([100.0] * 30 + [-400.0] * 30))

# Same shape, sign flipped: +400 on winning days, -100 on losing days.
POSITIVE_EXPECTANCY = days(*([400.0] * 30 + [-100.0] * 30))


class TestNegativeExpectancyNeverPasses:
    def test_no_evaluation_passes(self):
        result = simulate(NEGATIVE_EXPECTANCY, RULES, n=2_000, rng=np.random.default_rng(11))

        assert result.outcomes[PASS] == 0
        assert result.pass_rate == 0.0
        assert result.days_to_pass == []
        assert result.median_days_to_pass is None

    def test_failures_are_drawdown_not_timeout(self):
        # A losing strategy should be killed by the trailing drawdown, not run
        # quietly to the horizon — a pass rate of zero would be uninformative
        # if nothing ever actually failed.
        result = simulate(NEGATIVE_EXPECTANCY, RULES, n=2_000, rng=np.random.default_rng(12))

        assert result.rate(TRAILING_DRAWDOWN) > 0.95
        assert result.outcomes[TIMEOUT] + result.outcomes[TRAILING_DRAWDOWN] == 2_000

    def test_the_zero_is_not_vacuous(self):
        # The mirror-image winning strategy must pass often, proving the zero
        # above comes from the strategy and not from a broken pass condition.
        result = simulate(POSITIVE_EXPECTANCY, RULES, n=2_000, rng=np.random.default_rng(11))

        assert result.pass_rate > 0.5
        assert result.median_days_to_pass is not None

    def test_a_bigger_position_does_not_rescue_a_losing_strategy(self):
        scaled = [day * 3 for day in NEGATIVE_EXPECTANCY]

        result = simulate(scaled, RULES, n=1_000, rng=np.random.default_rng(13))

        assert result.outcomes[PASS] == 0


class TestSimulationMechanics:
    def test_same_seed_gives_the_same_answer(self):
        a = simulate(POSITIVE_EXPECTANCY, RULES, n=200, rng=np.random.default_rng(3))
        b = simulate(POSITIVE_EXPECTANCY, RULES, n=200, rng=np.random.default_rng(3))

        assert a.outcomes == b.outcomes
        assert a.days_to_pass == b.days_to_pass

    def test_outcome_counts_sum_to_the_run_count(self):
        result = simulate(POSITIVE_EXPECTANCY, RULES, n=500, rng=np.random.default_rng(4))

        assert sum(result.outcomes.values()) == 500
        assert set(result.outcomes) <= {PASS, TRAILING_DRAWDOWN, TIMEOUT}

    def test_days_to_pass_is_recorded_only_for_passes(self):
        result = simulate(POSITIVE_EXPECTANCY, RULES, n=300, rng=np.random.default_rng(5))

        assert len(result.days_to_pass) == result.outcomes[PASS]
        assert all(RULES.min_days <= d <= RULES.max_days for d in result.days_to_pass)

    def test_resampling_never_exceeds_the_horizon(self):
        result = run_eval(POSITIVE_EXPECTANCY, RULES, np.random.default_rng(6))

        assert result.days <= RULES.max_days

    def test_empty_day_set_is_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            run_eval([], RULES, np.random.default_rng(1))


class TestSizeSweep:
    def test_larger_positions_trade_pass_rate_for_drawdown_risk(self):
        sweep = size_sweep(
            POSITIVE_EXPECTANCY, RULES, multipliers=(1, 4), n=800,
            rng=np.random.default_rng(9),
        )

        assert set(sweep) == {1, 4}
        # Expectancy per unit of risk is unchanged, but the fixed drawdown
        # limit does not scale — so sequence risk rises with size.
        assert sweep[4].rate(TRAILING_DRAWDOWN) > sweep[1].rate(TRAILING_DRAWDOWN)
        assert sweep[4].pass_rate < sweep[1].pass_rate

    def test_sweep_leaves_the_input_days_untouched(self):
        original = [day.copy() for day in POSITIVE_EXPECTANCY]

        size_sweep(POSITIVE_EXPECTANCY, RULES, multipliers=(3,), n=50,
                   rng=np.random.default_rng(2))

        for before, after in zip(original, POSITIVE_EXPECTANCY):
            assert before == pytest.approx(after)
