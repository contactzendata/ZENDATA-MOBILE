"""Prop-firm evaluation pass-probability simulator.

Resamples whole trading days from a real trade history to estimate how often a
strategy clears a prop-firm evaluation before its drawdown or time limits.

See `engine` for the simulation and the important caveats on both the day-
resampling model and the UNVERIFIED default ruleset.
"""

from propsim.engine import (
    PASS,
    TIMEOUT,
    TRAILING_DRAWDOWN,
    EvalResult,
    Ruleset,
    SimulationResult,
    run_eval,
    run_eval_sequence,
    simulate,
    size_sweep,
)
from propsim.ingest import IngestError, TradeData, load_days, load_trade_data

__all__ = [
    "PASS",
    "TIMEOUT",
    "TRAILING_DRAWDOWN",
    "EvalResult",
    "IngestError",
    "Ruleset",
    "SimulationResult",
    "TradeData",
    "load_days",
    "load_trade_data",
    "run_eval",
    "run_eval_sequence",
    "simulate",
    "size_sweep",
]
