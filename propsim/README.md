# propsim

Monte Carlo simulator for prop-firm evaluations. Feed it a CSV of your trades
and it estimates how often that trade distribution clears an evaluation before
the drawdown or time limits end it.

```
pip install numpy            # runtime
pip install pytest           # tests only

python -m propsim trades.csv
```

## Read this before you trust a number

Two caveats are structural, not bugs:

- **The default ruleset is UNVERIFIED.** The limits below are carried over from
  the original prototype and have *not* been checked against current prop-firm
  documentation. Confirm them against your actual account and override with the
  ruleset flags if they differ.
- **Day resampling cannot produce multi-day losing streaks.** Whole trading days
  are drawn independently, so a strategy that bleeds through a trending week
  scores better here than it does in reality. Read the pass rate as an
  optimistic bound.

Whole days are resampled — rather than individual trades — precisely so that
intra-day trade order survives and the daily loss limit can be modeled at all.

## Layout

| module | role |
| --- | --- |
| `ingest.py` | CSV → list of per-day P&L arrays; infers the timestamp and net-P&L columns |
| `engine.py` | the simulation; rules live in a `Ruleset` dataclass |
| `cli.py` | `python -m propsim trades.csv` |

## Input CSV

Any export with a timestamp column and a per-trade net P&L column works. Both
are inferred from the header, tolerating names like `pnl`, `Net P/L`, `profit`,
`realized`, `Close Time`, `Trade Date`, `datetime`. A `Net P/L` column is
preferred over `Gross P/L`, and running totals (`cumulative_pnl`,
`account_balance`) are never mistaken for per-trade results. Override with
`--pnl-column` / `--timestamp-column` when a file defeats the inference.

Values may carry currency symbols, thousands separators, or accounting
negatives: `$1,234.50`, `(500)`, `-45`. Timestamps may be ISO-8601, `MM/DD/YYYY`,
`01-Mar-2024`, epoch seconds, and others; a UTC offset is dropped rather than
converted, so a trading day stays the local calendar day the export printed.

Trades are grouped into days by date, in timestamp order, with file order
breaking ties so date-only exports keep their intra-day sequence. For overnight
sessions, `--day-boundary-hour 18` puts 18:00+ trades on the next day's session.

A file with no rows, or with only a single trading day, is an **error** — the
engine resamples whole days, so one day would just be replayed in every run.

## Ruleset

Defaults (UNVERIFIED), all overridable from the CLI:

| flag | default | meaning |
| --- | --- | --- |
| `--start` | 50,000 | account starting balance |
| `--target` | 3,000 | profit target |
| `--trail` | 2,000 | trailing max drawdown from the equity high-water mark |
| `--daily-loss` | 1,000 | daily loss limit — **locks out the day, is not a failure** |
| `--min-days` | 5 | minimum trading days before a pass |
| `--consistency` | 0.50 | best single day must be ≤ this share of total profit |
| `--max-days` | 60 | give-up horizon |

Two rules carry most of the subtlety, and both are pinned by tests in
`tests/test_engine_rules.py`:

- Hitting the daily loss limit **ends the day, not the evaluation**. Remaining
  trades that day are forfeited; trading resumes tomorrow.
- The trailing drawdown threshold **ratchets up** with the intra-day equity
  high-water mark, never falls back, and **locks permanently** once it reaches
  the starting balance.

## Library use

```python
from propsim import Ruleset, load_days, simulate

days = load_days("trades.csv")
result = simulate(days, Ruleset(start=150_000, target=9_000, trail=5_000), n=10_000)
print(result.pass_rate, result.median_days_to_pass)
```

`run_eval_sequence(days, rules)` runs an explicit, ordered list of days with no
resampling — the deterministic seam the rule tests are built on.

## Tests

```
python -m pytest
```
