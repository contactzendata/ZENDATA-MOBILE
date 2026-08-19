"""
Load a CSV of individual trades into the list-of-day-arrays format the engine
expects.

Broker and platform exports disagree about column names, so the timestamp and
net-P&L columns are inferred rather than hard-coded. Trades are grouped into
trading days by date, and intra-day order is preserved.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


class IngestError(ValueError):
    """Raised when a CSV cannot be turned into usable trading days.

    Always carries a message naming the specific problem — a bad input must
    fail loudly rather than silently produce a pass probability.
    """


# Minimum distinct trading days. The engine resamples whole days, so a single
# day is not a distribution: every simulated evaluation would replay it.
MIN_TRADING_DAYS = 2

# Below this, results are dominated by whichever few days happened to be in the
# file. Not an error, but callers should warn.
ADVISORY_MIN_DAYS = 20

# --------------------------------------------------------------- column names
# Exact (normalized) header matches, best first.
_TIMESTAMP_NAMES = (
    "timestamp", "datetime", "date", "time", "tradedate", "tradetime",
    "closetime", "closedat", "closedtime", "exittime", "exitdatetime",
    "filltime", "filledat", "executiontime", "transactiondate", "opentime",
    "entrytime", "entrydatetime", "boughttimestamp", "soldtimestamp",
)
_PNL_NAMES = (
    "netpnl", "netpl", "netprofit", "netprofitloss", "netrealized",
    "realizedpnl", "realizedpl", "realized", "pnl", "pl", "pandl",
    "profitloss", "plusd", "pnlusd", "profit", "net", "gainloss",
    "result", "netamount", "amount",
)
# Substring fallbacks, applied only if no exact match is found.
_TIMESTAMP_HINTS = ("time", "date")
_PNL_HINTS = ("pnl", "pl", "profit", "realized", "net", "gain")

# A column matching any of these is never chosen as the net P&L column: they
# are running totals, per-unit figures, or costs rather than per-trade results.
_PNL_BLOCKLIST = (
    "gross", "cumulative", "cum", "running", "balance", "equity", "account",
    "fee", "commission", "swap", "percent", "pct", "ratio", "price", "qty",
    "quantity", "size", "contracts", "volume", "ticks", "points", "pips",
    "mae", "mfe", "target", "stop",
)


def _normalize(header: str) -> str:
    """Fold a header to a comparable key: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", header.strip().lower())


def _pick_column(
    headers: Sequence[str], names: Sequence[str], hints: Sequence[str],
    blocklist: Sequence[str] = (),
) -> str | None:
    """Choose the header that best matches `names`, then `hints`."""
    normalized = {h: _normalize(h) for h in headers}
    allowed = {
        h: n for h, n in normalized.items()
        if n and not any(bad in n for bad in blocklist)
    }
    for name in names:
        for header, norm in allowed.items():
            if norm == name:
                return header
    for hint in hints:
        for header, norm in allowed.items():
            if hint in norm:
                return header
    return None


# ---------------------------------------------------------------- value parsing
_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
    "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M", "%m/%d/%y",
    "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y",
    "%b %d, %Y %H:%M:%S", "%b %d, %Y %H:%M", "%b %d, %Y",
    "%Y%m%d %H:%M:%S", "%Y%m%d",
)


def parse_timestamp(raw: str, *, row: int, column: str) -> datetime:
    """Parse a timestamp from any of the common export formats.

    Returns a naive datetime. A UTC offset in the source (``...T09:31:00Z``)
    is dropped rather than converted, keeping the wall-clock time the export
    wrote — trading days are the exporter's local calendar days, and shifting
    them into UTC would silently move evening trades to the next day. Use
    `day_boundary_hour` to model an overnight session instead.
    """
    text = (raw or "").strip().strip('"').replace(" ", " ")
    if not text:
        raise IngestError(f"row {row}: empty timestamp in column {column!r}")

    # ISO-8601 first, including trailing 'Z'.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass

    # Epoch seconds or milliseconds.
    if re.fullmatch(r"\d{9,14}", text):
        value = int(text)
        if value > 10**12:  # microseconds
            value //= 1000
        if value > 10**10:  # milliseconds
            value /= 1000
        try:
            return datetime.fromtimestamp(value).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            pass

    compact = re.sub(r"\s+", " ", text)
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(compact, fmt).replace(tzinfo=None)
        except ValueError:
            continue

    raise IngestError(
        f"row {row}: could not parse timestamp {raw!r} in column {column!r}. "
        "Supported formats include ISO-8601 (2024-03-01T09:31:00), "
        "YYYY-MM-DD, MM/DD/YYYY, DD-Mon-YYYY, and epoch seconds."
    )


def parse_money(raw: str, *, row: int, column: str) -> float:
    """Parse a P&L value, tolerating currency symbols and accounting negatives."""
    text = (raw or "").strip().strip('"').replace(" ", "")
    if not text:
        raise IngestError(f"row {row}: empty P&L value in column {column!r}")

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[^0-9eE+\-.,]", "", text)  # drop $, £, spaces, "USD", ...
    text = text.replace(",", "")
    if text.startswith("+"):
        text = text[1:]

    try:
        value = float(text)
    except ValueError:
        raise IngestError(
            f"row {row}: could not parse P&L value {raw!r} in column {column!r}"
        ) from None
    if not np.isfinite(value):
        raise IngestError(f"row {row}: non-finite P&L value {raw!r} in column {column!r}")
    return -value if negative else value


# ------------------------------------------------------------------- loading
@dataclass(frozen=True)
class Trade:
    timestamp: datetime
    pnl: float
    order: int  # position in the source file, used to break timestamp ties


@dataclass(frozen=True)
class TradeData:
    """Trading days plus the provenance a caller needs to report on them."""

    days: list[np.ndarray]
    dates: list[date]
    timestamp_column: str
    pnl_column: str

    @property
    def n_trades(self) -> int:
        return sum(len(day) for day in self.days)


def _trading_date(moment: datetime, day_boundary_hour: int) -> date:
    """Calendar date of the trading day `moment` belongs to.

    With `day_boundary_hour=18`, a trade at 20:00 belongs to the NEXT calendar
    date's session — which is how overnight futures sessions are usually
    accounted for.
    """
    if day_boundary_hour == 0:
        return moment.date()
    return (moment + timedelta(hours=24 - day_boundary_hour)).date()


def load_trade_data(
    path: str | Path,
    *,
    timestamp_column: str | None = None,
    pnl_column: str | None = None,
    day_boundary_hour: int = 0,
    min_days: int = MIN_TRADING_DAYS,
) -> TradeData:
    """Read `path` and group its trades into trading days.

    Column names are inferred unless given explicitly. Raises `IngestError`
    with a specific message for any file that cannot yield usable days.
    """
    if not 0 <= day_boundary_hour <= 23:
        raise IngestError(f"day_boundary_hour must be 0-23, got {day_boundary_hour}")

    path = Path(path)
    if not path.exists():
        raise IngestError(f"CSV not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames
        if not headers or not any((h or "").strip() for h in headers):
            raise IngestError(
                f"{path}: no header row found — the file is empty or has no columns"
            )
        rows = list(reader)

    if not rows:
        raise IngestError(
            f"{path}: header row only, no trades. Columns seen: {', '.join(headers)}"
        )

    ts_col = timestamp_column or _pick_column(headers, _TIMESTAMP_NAMES, _TIMESTAMP_HINTS)
    if ts_col is None:
        raise IngestError(
            f"{path}: could not infer a timestamp column from: {', '.join(headers)}. "
            "Pass one explicitly (CLI: --timestamp-column)."
        )
    if ts_col not in headers:
        raise IngestError(
            f"{path}: timestamp column {ts_col!r} not in file. Columns: {', '.join(headers)}"
        )

    pnl_col = pnl_column or _pick_column(headers, _PNL_NAMES, _PNL_HINTS, _PNL_BLOCKLIST)
    if pnl_col is None:
        raise IngestError(
            f"{path}: could not infer a net P&L column from: {', '.join(headers)}. "
            "Pass one explicitly (CLI: --pnl-column)."
        )
    if pnl_col not in headers:
        raise IngestError(
            f"{path}: P&L column {pnl_col!r} not in file. Columns: {', '.join(headers)}"
        )
    if pnl_col == ts_col:
        raise IngestError(
            f"{path}: column {pnl_col!r} was chosen for both timestamp and P&L; "
            "pass both explicitly (--timestamp-column / --pnl-column)."
        )

    trades: list[Trade] = []
    for index, row in enumerate(rows):
        line = index + 2  # +1 for the header, +1 for 1-based line numbers
        raw_ts = (row.get(ts_col) or "").strip()
        raw_pnl = (row.get(pnl_col) or "").strip()
        if not raw_ts and not raw_pnl:
            continue  # blank padding row
        trades.append(
            Trade(
                timestamp=parse_timestamp(raw_ts, row=line, column=ts_col),
                pnl=parse_money(raw_pnl, row=line, column=pnl_col),
                order=index,
            )
        )

    if not trades:
        raise IngestError(f"{path}: no trade rows with data (all rows were blank)")

    # Stable sort: file order breaks ties between identical timestamps, so
    # intra-day sequence survives exports that only carry a date.
    trades.sort(key=lambda t: (t.timestamp, t.order))

    grouped: dict[date, list[float]] = {}
    for trade in trades:
        grouped.setdefault(_trading_date(trade.timestamp, day_boundary_hour), []).append(trade.pnl)

    dates = sorted(grouped)
    if len(dates) < min_days:
        raise IngestError(
            f"{path}: found {len(dates)} trading day(s) "
            f"({', '.join(d.isoformat() for d in dates)}) across {len(trades)} trade(s), "
            f"but at least {min_days} are required. The simulator resamples whole "
            "days, so a single day would just be replayed in every run — the pass "
            "probability would be meaningless."
        )

    days = [np.asarray(grouped[d], dtype=float) for d in dates]
    return TradeData(days=days, dates=dates, timestamp_column=ts_col, pnl_column=pnl_col)


def load_days(path: str | Path, **kwargs) -> list[np.ndarray]:
    """Convenience wrapper: just the list-of-day-arrays the engine wants."""
    return load_trade_data(path, **kwargs).days


def days_from_trades(
    trades: Iterable[tuple[datetime, float]], *, day_boundary_hour: int = 0
) -> list[np.ndarray]:
    """Group already-parsed (timestamp, pnl) pairs into day arrays."""
    grouped: dict[date, list[float]] = {}
    for order, (timestamp, pnl) in enumerate(sorted(trades, key=lambda t: t[0])):
        grouped.setdefault(_trading_date(timestamp, day_boundary_hour), []).append(float(pnl))
    return [np.asarray(grouped[d], dtype=float) for d in sorted(grouped)]
