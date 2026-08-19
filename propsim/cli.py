"""Command-line interface: `python -m propsim trades.csv`."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import numpy as np

from propsim.engine import (
    PASS,
    Ruleset,
    SimulationResult,
    simulate,
    size_sweep,
)
from propsim.ingest import ADVISORY_MIN_DAYS, IngestError, load_trade_data

RULESET_WARNING = (
    "WARNING: the default ruleset is UNVERIFIED — it was carried over from a "
    "prototype and has not been checked against current prop-firm documentation. "
    "Confirm the limits below against your account's actual rules before acting "
    "on these numbers."
)

MODEL_WARNING = (
    "NOTE: whole trading days are resampled independently, so multi-day losing "
    "streaks are not reproduced. Read the pass rate as an optimistic bound."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m propsim",
        description="Estimate prop-firm evaluation pass probability from a trade CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("csv", help="CSV of individual trades")

    source = parser.add_argument_group("input")
    source.add_argument(
        "--timestamp-column", default=None,
        help="timestamp column name (inferred by default)",
    )
    source.add_argument(
        "--pnl-column", default=None,
        help="net P&L column name (inferred by default)",
    )
    source.add_argument(
        "--day-boundary-hour", type=int, default=0, metavar="H",
        help="hour at which a new trading day starts, for overnight sessions "
             "(e.g. 18 puts 18:00+ trades on the next day's session)",
    )

    rules = parser.add_argument_group("ruleset (UNVERIFIED defaults)")
    defaults = Ruleset()
    rules.add_argument("--start", type=float, default=defaults.start, help="starting balance")
    rules.add_argument("--target", type=float, default=defaults.target, help="profit target")
    rules.add_argument("--trail", type=float, default=defaults.trail, help="trailing max drawdown")
    rules.add_argument(
        "--daily-loss", type=float, default=defaults.daily_loss,
        help="daily loss limit (locks out the day, not a failure)",
    )
    rules.add_argument("--min-days", type=int, default=defaults.min_days, help="minimum trading days")
    rules.add_argument(
        "--consistency", type=float, default=defaults.consistency,
        help="best day must be <= this share of total profit",
    )
    rules.add_argument("--max-days", type=int, default=defaults.max_days, help="give-up horizon")

    run = parser.add_argument_group("simulation")
    run.add_argument("-n", "--runs", type=int, default=10_000, help="evaluations to simulate")
    run.add_argument("--sweep-runs", type=int, default=6_000, help="evaluations per sweep step")
    run.add_argument(
        "--sizes", type=int, nargs="+", default=[1, 2, 3, 4], metavar="M",
        help="position-size multipliers for the sweep",
    )
    run.add_argument("--seed", type=int, default=7, help="RNG seed")
    run.add_argument("--no-sweep", action="store_true", help="skip the position-size sweep")
    return parser


def _format_breakdown(result: SimulationResult) -> list[str]:
    lines = []
    for outcome, count in result.outcomes.most_common():
        label = "pass" if outcome == PASS else outcome
        lines.append(f"  {label:<20s} {count / result.n:6.1%}  ({count:,} / {result.n:,})")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        rules = Ruleset(
            start=args.start,
            target=args.target,
            trail=args.trail,
            daily_loss=args.daily_loss,
            min_days=args.min_days,
            consistency=args.consistency,
            max_days=args.max_days,
        )
    except ValueError as exc:
        print(f"error: invalid ruleset: {exc}", file=sys.stderr)
        return 2

    try:
        data = load_trade_data(
            args.csv,
            timestamp_column=args.timestamp_column,
            pnl_column=args.pnl_column,
            day_boundary_hour=args.day_boundary_hour,
        )
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(RULESET_WARNING, file=sys.stderr)
    print(MODEL_WARNING, file=sys.stderr)
    if len(data.days) < ADVISORY_MIN_DAYS:
        print(
            f"NOTE: only {len(data.days)} trading days in the sample; results are "
            f"dominated by these few days (>= {ADVISORY_MIN_DAYS} recommended).",
            file=sys.stderr,
        )
    print(file=sys.stderr)

    total_pnl = float(sum(day.sum() for day in data.days))
    print(f"source      : {args.csv}")
    print(f"columns     : timestamp={data.timestamp_column!r}  pnl={data.pnl_column!r}")
    print(
        f"sample      : {data.n_trades:,} trades over {len(data.days)} days "
        f"({data.dates[0]} -> {data.dates[-1]})"
    )
    print(
        f"expectancy  : {total_pnl / data.n_trades:,.2f} / trade, "
        f"{total_pnl / len(data.days):,.2f} / day"
    )
    print(
        f"ruleset     : start {rules.start:,.0f} | target +{rules.target:,.0f} | "
        f"trail {rules.trail:,.0f} | daily loss {rules.daily_loss:,.0f} | "
        f"min {rules.min_days}d | consistency {rules.consistency:.0%} | "
        f"horizon {rules.max_days}d"
    )
    print()

    rng = np.random.default_rng(args.seed)
    result = simulate(data.days, rules, args.runs, rng)

    print(f"PASS RATE   : {result.pass_rate:.1%}  ({args.runs:,} simulated evaluations)")
    print("outcomes:")
    for line in _format_breakdown(result):
        print(line)

    median = result.median_days_to_pass
    print(f"median days to pass: {int(median) if median is not None else '-'}")

    if not args.no_sweep:
        print()
        print(f"position-size sweep ({args.sweep_runs:,} evaluations per step):")
        print(f"  {'size':<8s} {'pass':>7s} {'trailDD':>9s} {'timeout':>9s} {'med days':>9s}")
        sweep = size_sweep(data.days, rules, tuple(args.sizes), args.sweep_runs, rng)
        for multiplier, sweep_result in sweep.items():
            median_days = sweep_result.median_days_to_pass
            print(
                f"  {multiplier:<8d} {sweep_result.pass_rate:>7.1%} "
                f"{sweep_result.rate('trailing_drawdown'):>9.1%} "
                f"{sweep_result.rate('timeout'):>9.1%} "
                f"{int(median_days) if median_days is not None else '-':>9}"
            )

    return 0
