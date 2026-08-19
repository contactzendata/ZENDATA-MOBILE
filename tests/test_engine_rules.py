"""Rule-level tests for the evaluation engine.

These use `run_eval_sequence`, which trades an explicit, ordered list of days
with no resampling — so every assertion below is deterministic.

The first two classes pin behaviors that are easy to get subtly wrong and that
silently inflate or deflate a pass probability when they are.
"""

import numpy as np
import pytest

from propsim.engine import (
    PASS,
    TIMEOUT,
    TRAILING_DRAWDOWN,
    Ruleset,
    run_eval_sequence,
)

RULES = Ruleset()  # start 50,000 | target 3,000 | trail 2,000 | daily loss 1,000


def day(*pnls: float) -> np.ndarray:
    return np.array(pnls, dtype=float)


class TestDailyLossLimitEndsTheDayNotTheEvaluation:
    """The daily loss limit is a LOCKOUT, not a failure.

    Hitting it must stop trading for that day and let the evaluation continue
    the next day. Treating it as a terminal failure would understate the pass
    rate badly, since a strategy is expected to hit it occasionally.
    """

    LOCKOUT_DAY = day(-600, -600, 5000)  # DLL breached on trade 2; trade 3 never taken

    def test_lockout_stops_the_day_and_forfeits_the_remaining_trades(self):
        result = run_eval_sequence([self.LOCKOUT_DAY], RULES)

        # The day ended, the evaluation did not fail.
        assert result.outcome != TRAILING_DRAWDOWN
        assert result.outcome == TIMEOUT  # simply ran out of days in the sequence
        assert result.days == 1

        # Equity reflects only the two trades before the lockout. If the +5,000
        # had been taken, equity would be 53,800.
        assert result.equity == pytest.approx(48_800)
        assert result.day_pnls == pytest.approx([-1_200])

    def test_evaluation_continues_the_next_day_and_can_still_pass(self):
        # One lockout day, then five clean days.
        sequence = [self.LOCKOUT_DAY] + [day(900)] * 5

        result = run_eval_sequence(sequence, RULES)

        assert result.outcome == PASS
        assert result.days == 6
        assert result.equity == pytest.approx(53_300)  # 48,800 + 5 x 900
        assert len(result.day_pnls) == 6

    def test_many_consecutive_lockout_days_still_do_not_end_the_evaluation(self):
        # Each day loses exactly the daily limit on its first trade; none of
        # these days is individually fatal.
        sequence = [day(-1_000, -5_000)] * 2  # -1,000/day; equity 48,000 after two

        result = run_eval_sequence(sequence, RULES)

        # Equity lands exactly on the initial threshold only after day 2, and
        # `<=` makes that a breach — so the failure comes from the drawdown
        # rule, on day 2, not from the lockouts themselves.
        assert result.outcome == TRAILING_DRAWDOWN
        assert result.days == 2
        assert result.day_pnls[0] == pytest.approx(-1_000)

    def test_drawdown_breach_wins_when_a_single_trade_does_both(self):
        # A trade that breaches the daily limit AND the trailing threshold is a
        # failure: the lockout must not rescue the evaluation.
        result = run_eval_sequence([day(-2_100)], RULES)

        assert result.outcome == TRAILING_DRAWDOWN
        assert result.days == 1

    def test_lockout_threshold_is_the_ruleset_value(self):
        rules = Ruleset(daily_loss=500)
        # -600 breaches a 500 limit on trade 1, so the +5,000 is forfeited.
        result = run_eval_sequence([day(-600, 5_000)], rules)

        assert result.equity == pytest.approx(49_400)
        assert result.outcome == TIMEOUT


class TestTrailingDrawdownRatchetsThenLocks:
    """The trailing threshold follows the equity high-water mark UP, never
    down, and stops moving once it reaches the starting balance.

    Three distinct mistakes are possible here, and the sequence below
    distinguishes all of them:
      - never ratcheting (threshold stuck at start - trail)
      - ratcheting back DOWN when equity falls
      - ratcheting past the starting balance instead of locking there
    """

    def test_threshold_starts_one_trail_below_the_starting_balance(self):
        result = run_eval_sequence([day(0.0)], RULES)

        assert result.threshold == pytest.approx(48_000)

    def test_threshold_ratchets_up_with_the_high_water_mark(self):
        # +1,500 -> high-water 51,500 -> threshold 49,500 (still below start).
        result = run_eval_sequence([day(1_500)], RULES)

        assert result.high_water == pytest.approx(51_500)
        assert result.threshold == pytest.approx(49_500)

    def test_threshold_locks_at_the_starting_balance(self):
        # +2,500 -> high-water 52,500. An uncapped trail would put the
        # threshold at 50,500; it must cap at the 50,000 starting balance.
        result = run_eval_sequence([day(2_500)], RULES)

        assert result.high_water == pytest.approx(52_500)
        assert result.threshold == pytest.approx(50_000)

    def test_threshold_never_falls_back_once_ratcheted(self):
        # Climb to a high-water mark of 52,500 (threshold locked at 50,000),
        # then give most of it back. The threshold must not follow equity down.
        sequence = [day(1_500), day(1_000), day(-2_400)]

        result = run_eval_sequence(sequence, RULES)

        assert result.outcome == TIMEOUT  # survived: 50,100 is still above 50,000
        assert result.equity == pytest.approx(50_100)
        assert result.threshold == pytest.approx(50_000)
        assert result.high_water == pytest.approx(52_500)

    def test_locked_threshold_is_what_finally_fails_the_evaluation(self):
        # Same climb, then a slide through 50,000. This is the discriminating
        # case: a threshold stuck at 48,000 would survive 49,900, and an
        # uncapped one (50,500) would have failed a day earlier on the -2,400.
        sequence = [day(1_500), day(1_000), day(-2_400), day(-200)]

        result = run_eval_sequence(sequence, RULES)

        assert result.outcome == TRAILING_DRAWDOWN
        assert result.days == 4
        assert result.equity == pytest.approx(49_900)
        assert result.threshold == pytest.approx(50_000)

    def test_ratchet_tracks_intraday_equity_not_just_the_daily_close(self):
        # One day: up 2,500 then down 2,600, closing at 49,900. The high-water
        # mark is set intra-day, which locks the threshold at 50,000 and fails
        # the evaluation before the day is over. Ratcheting only on daily
        # closes would let this day pass unharmed.
        result = run_eval_sequence([day(2_500, -2_600)], RULES)

        assert result.outcome == TRAILING_DRAWDOWN
        assert result.days == 1
        assert result.high_water == pytest.approx(52_500)
        assert result.threshold == pytest.approx(50_000)

    def test_lock_point_follows_the_ruleset_not_a_hard_coded_50k(self):
        rules = Ruleset(start=100_000, target=6_000, trail=3_000, daily_loss=2_000)
        # +4,000 -> high-water 104,000 -> uncapped trail would be 101,000.
        result = run_eval_sequence([day(4_000)], rules)

        assert result.threshold == pytest.approx(100_000)


class TestPassConditions:
    """The remaining pass criteria, so the tests above cannot pass vacuously."""

    def test_profit_target_alone_is_not_enough_before_min_days(self):
        # Target cleared on day 1, but a pass needs five trading days.
        result = run_eval_sequence([day(3_500)], Ruleset(min_days=5, max_days=5))

        assert result.outcome == TIMEOUT
        assert result.days == 1
        assert result.equity == pytest.approx(53_500)

    def test_consistency_rule_blocks_a_pass_carried_by_one_big_day(self):
        # Day 1 is 3,000 of a 3,200 total: 94% > the 50% cap.
        sequence = [day(3_000)] + [day(50)] * 4

        result = run_eval_sequence(sequence, Ruleset(min_days=5, max_days=5))

        assert result.outcome == TIMEOUT

    def test_trading_on_dilutes_the_best_day_into_a_pass(self):
        # Same big day, then enough profit that 3,000 is at most half the total.
        sequence = [day(3_000)] + [day(750)] * 4

        result = run_eval_sequence(sequence, Ruleset(min_days=5, max_days=5))

        assert result.outcome == PASS
        assert result.days == 5
        assert max(result.day_pnls) <= 0.5 * (result.equity - 50_000)

    def test_horizon_truncates_a_longer_sequence(self):
        rules = Ruleset(min_days=1, max_days=3)
        result = run_eval_sequence([day(10)] * 50, rules)

        assert result.outcome == TIMEOUT
        assert result.days == 3
        assert len(result.day_pnls) == 3


class TestRulesetValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"start": 0},
            {"target": -1},
            {"trail": 0},
            {"daily_loss": -500},
            {"min_days": 0},
            {"max_days": 0},
            {"consistency": 0},
            {"consistency": 1.5},
            {"min_days": 10, "max_days": 5},
        ],
    )
    def test_impossible_rulesets_are_rejected(self, kwargs):
        with pytest.raises(ValueError):
            Ruleset(**kwargs)
