"""Tests for CSV loading: column inference, day grouping, and loud failures."""

import numpy as np
import pytest

from propsim.ingest import (
    IngestError,
    days_from_trades,
    load_days,
    load_trade_data,
)


def write_csv(tmp_path, text, name="trades.csv"):
    path = tmp_path / name
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


TWO_DAYS = """
timestamp,pnl
2024-03-01 09:31:00,120.5
2024-03-01 10:02:00,-45
2024-03-04 09:45:00,310
"""


class TestBadInputRaisesRatherThanReturningANumber:
    """An unusable file must fail with a specific message. Silently producing
    a pass probability from one day (or from nothing) is the worst outcome
    here, because the number looks just as authoritative as a real one."""

    def test_completely_empty_file(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")

        with pytest.raises(IngestError, match="no header row"):
            load_days(path)

    def test_header_only_file(self, tmp_path):
        path = write_csv(tmp_path, "timestamp,pnl")

        with pytest.raises(IngestError, match="no trades"):
            load_days(path)

    def test_file_of_blank_rows(self, tmp_path):
        path = write_csv(tmp_path, "timestamp,pnl\n,\n,\n")

        with pytest.raises(IngestError, match="no trade rows"):
            load_days(path)

    def test_single_day_of_trades(self, tmp_path):
        path = write_csv(
            tmp_path,
            """
            timestamp,pnl
            2024-03-01 09:31:00,120.5
            2024-03-01 10:02:00,-45
            2024-03-01 14:55:00,80
            """.replace("            ", ""),
        )

        with pytest.raises(IngestError) as exc:
            load_days(path)

        message = str(exc.value)
        assert "1 trading day" in message
        assert "2024-03-01" in message  # names the day it found
        assert "resamples whole days" in message  # says why one is not enough

    def test_single_trade(self, tmp_path):
        path = write_csv(tmp_path, "timestamp,pnl\n2024-03-01 09:31:00,120.5")

        with pytest.raises(IngestError, match="1 trading day"):
            load_days(path)

    def test_missing_file(self, tmp_path):
        with pytest.raises(IngestError, match="not found"):
            load_days(tmp_path / "nope.csv")

    def test_no_timestamp_column(self, tmp_path):
        path = write_csv(tmp_path, "symbol,pnl\nMGC,120\nMGC,-40")

        with pytest.raises(IngestError) as exc:
            load_days(path)

        assert "timestamp column" in str(exc.value)
        assert "symbol" in str(exc.value)  # lists what it did see

    def test_no_pnl_column(self, tmp_path):
        path = write_csv(tmp_path, "timestamp,symbol\n2024-03-01,MGC\n2024-03-04,MGC")

        with pytest.raises(IngestError) as exc:
            load_days(path)

        assert "P&L column" in str(exc.value)
        assert "--pnl-column" in str(exc.value)  # tells the user how to fix it

    def test_unparseable_pnl_names_the_row(self, tmp_path):
        path = write_csv(
            tmp_path, "timestamp,pnl\n2024-03-01,120\n2024-03-04,not-a-number"
        )

        with pytest.raises(IngestError, match="row 3"):
            load_days(path)

    def test_unparseable_timestamp_names_the_row(self, tmp_path):
        path = write_csv(tmp_path, "timestamp,pnl\n2024-03-01,120\nlast tuesday,45")

        with pytest.raises(IngestError, match="row 3"):
            load_days(path)

    def test_explicit_column_that_does_not_exist(self, tmp_path):
        path = write_csv(tmp_path, TWO_DAYS)

        with pytest.raises(IngestError, match="not in file"):
            load_days(path, pnl_column="net_profit")


class TestColumnInference:
    @pytest.mark.parametrize(
        "header",
        ["pnl", "PnL", "P&L", "profit", "Net", "net_pnl", "Net P/L", "realized",
         "Realized P&L", "profit_loss", "gain_loss", "Result", "NetProfit"],
    )
    def test_pnl_column_names(self, tmp_path, header):
        path = write_csv(
            tmp_path,
            f"timestamp,{header}\n2024-03-01 09:31:00,120\n2024-03-04 09:31:00,-45",
        )

        data = load_trade_data(path)

        assert data.pnl_column == header
        assert data.days[0] == pytest.approx([120])

    @pytest.mark.parametrize(
        "header",
        ["timestamp", "Timestamp", "datetime", "Date/Time", "date", "Trade Date",
         "Close Time", "closed_at", "Exit Time", "fill_time", "Execution Time"],
    )
    def test_timestamp_column_names(self, tmp_path, header):
        path = write_csv(
            tmp_path, f"{header},pnl\n2024-03-01 09:31:00,120\n2024-03-04 09:31:00,-45"
        )

        data = load_trade_data(path)

        assert data.timestamp_column == header
        assert len(data.days) == 2

    def test_net_is_preferred_over_gross(self, tmp_path):
        path = write_csv(
            tmp_path,
            """
            Close Time,Gross P/L,Commission,Net P/L
            2024-03-01 09:31:00,124.5,4.5,120.0
            2024-03-04 09:31:00,-40.5,4.5,-45.0
            """.replace("            ", ""),
        )

        data = load_trade_data(path)

        assert data.pnl_column == "Net P/L"
        assert data.days[0] == pytest.approx([120.0])

    def test_running_totals_are_not_mistaken_for_trade_pnl(self, tmp_path):
        path = write_csv(
            tmp_path,
            """
            timestamp,cumulative_pnl,account_balance,pnl
            2024-03-01 09:31:00,120,50120,120
            2024-03-04 09:31:00,75,50075,-45
            """.replace("            ", ""),
        )

        data = load_trade_data(path)

        assert data.pnl_column == "pnl"

    def test_explicit_columns_override_inference(self, tmp_path):
        path = write_csv(
            tmp_path,
            """
            Close Time,pnl,Gross P/L
            2024-03-01 09:31:00,120,124.5
            2024-03-04 09:31:00,-45,-40.5
            """.replace("            ", ""),
        )

        data = load_trade_data(path, pnl_column="Gross P/L")

        assert data.days[0] == pytest.approx([124.5])

    def test_bom_and_whitespace_in_headers(self, tmp_path):
        path = tmp_path / "bom.csv"
        path.write_text(
            "﻿ Timestamp , Net PnL \n2024-03-01 09:31:00,120\n2024-03-04 09:31:00,-45\n",
            encoding="utf-8",
        )

        data = load_trade_data(path)

        assert len(data.days) == 2


class TestDayGrouping:
    def test_trades_are_grouped_by_date(self, tmp_path):
        path = write_csv(tmp_path, TWO_DAYS)

        data = load_trade_data(path)

        assert len(data.days) == 2
        assert data.days[0] == pytest.approx([120.5, -45])
        assert data.days[1] == pytest.approx([310])
        assert [d.isoformat() for d in data.dates] == ["2024-03-01", "2024-03-04"]

    def test_intraday_order_is_preserved(self, tmp_path):
        path = write_csv(
            tmp_path,
            """
            timestamp,pnl
            2024-03-01 09:31:00,1
            2024-03-01 09:32:00,2
            2024-03-01 09:33:00,3
            2024-03-01 09:34:00,4
            2024-03-04 09:31:00,5
            """.replace("            ", ""),
        )

        days = load_days(path)

        assert days[0] == pytest.approx([1, 2, 3, 4])

    def test_out_of_order_rows_are_sorted_by_timestamp(self, tmp_path):
        path = write_csv(
            tmp_path,
            """
            timestamp,pnl
            2024-03-04 09:31:00,5
            2024-03-01 09:33:00,3
            2024-03-01 09:31:00,1
            2024-03-01 09:32:00,2
            """.replace("            ", ""),
        )

        days = load_days(path)

        assert days[0] == pytest.approx([1, 2, 3])
        assert days[1] == pytest.approx([5])

    def test_date_only_timestamps_keep_file_order_within_a_day(self, tmp_path):
        # Nothing else can order these, so the export's own order must survive.
        path = write_csv(
            tmp_path,
            """
            trade date,pnl
            2024-03-01,10
            2024-03-01,20
            2024-03-01,30
            2024-03-04,40
            """.replace("            ", ""),
        )

        days = load_days(path)

        assert days[0] == pytest.approx([10, 20, 30])

    def test_day_boundary_hour_groups_an_overnight_session(self, tmp_path):
        # With an 18:00 boundary, the evening trade belongs to the next
        # session, alongside the following morning's trades.
        path = write_csv(
            tmp_path,
            """
            timestamp,pnl
            2024-03-01 20:15:00,10
            2024-03-02 02:30:00,20
            2024-03-04 09:31:00,30
            """.replace("            ", ""),
        )

        default = load_days(path)
        overnight = load_days(path, day_boundary_hour=18)

        assert [list(d) for d in default] == [[10], [20], [30]]
        assert [list(d) for d in overnight] == [[10, 20], [30]]

    def test_days_are_float_arrays(self, tmp_path):
        days = load_days(write_csv(tmp_path, TWO_DAYS))

        assert all(isinstance(day, np.ndarray) for day in days)
        assert all(day.dtype == np.float64 for day in days)

    def test_metadata_reports_the_sample(self, tmp_path):
        data = load_trade_data(write_csv(tmp_path, TWO_DAYS))

        assert data.n_trades == 3
        assert data.timestamp_column == "timestamp"
        assert data.pnl_column == "pnl"


class TestValueParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("120.5", 120.5),
            ("-45", -45.0),
            ("+45", 45.0),
            ("$1,234.50", 1234.5),
            ("-$1,234.50", -1234.5),
            ("(500)", -500.0),
            ("($1,000.25)", -1000.25),
            ("1234.5 USD", 1234.5),
            ("0", 0.0),
        ],
    )
    def test_money_formats(self, tmp_path, raw, expected):
        path = write_csv(
            tmp_path, f'timestamp,pnl\n2024-03-01 09:31:00,"{raw}"\n2024-03-04 09:31:00,1'
        )

        days = load_days(path)

        assert days[0][0] == pytest.approx(expected)

    @pytest.mark.parametrize(
        "raw",
        [
            "2024-03-01T09:31:00", "2024-03-01 09:31:00", "2024-03-01",
            "2024-03-01T09:31:00Z", "03/01/2024 09:31:00", "03/01/2024",
            "03/01/24 09:31", "01-Mar-2024 09:31:00", "Mar 01, 2024 09:31:00",
            "20240301", "1709285460",
        ],
    )
    def test_timestamp_formats(self, tmp_path, raw):
        path = write_csv(tmp_path, f'timestamp,pnl\n"{raw}",120\n2024-06-01,45')

        data = load_trade_data(path)

        assert data.dates[0].year == 2024
        assert data.dates[0].month == 3


class TestDaysFromTrades:
    def test_groups_parsed_pairs(self):
        from datetime import datetime

        days = days_from_trades(
            [
                (datetime(2024, 3, 1, 9, 31), 10),
                (datetime(2024, 3, 4, 9, 31), 30),
                (datetime(2024, 3, 1, 9, 32), 20),
            ]
        )

        assert [list(d) for d in days] == [[10, 20], [30]]


class TestTimezoneHandling:
    """Offsets are dropped, not converted, so a day stays the day the export
    printed. Mixing offset-aware and naive rows must not blow up."""

    def test_offset_aware_and_naive_rows_mix(self, tmp_path):
        path = write_csv(
            tmp_path,
            """
            timestamp,pnl
            2024-03-01T09:31:00Z,10
            2024-03-01 09:32:00,20
            2024-03-04T09:31:00-05:00,30
            """.replace("            ", ""),
        )

        days = load_days(path)

        assert [list(d) for d in days] == [[10, 20], [30]]

    def test_evening_trade_keeps_its_local_date(self, tmp_path):
        # 20:15-05:00 is 01:15 UTC the next day; converting would move it.
        path = write_csv(
            tmp_path,
            """
            timestamp,pnl
            2024-03-01T20:15:00-05:00,10
            2024-03-04T09:31:00-05:00,30
            """.replace("            ", ""),
        )

        data = load_trade_data(path)

        assert [d.isoformat() for d in data.dates] == ["2024-03-01", "2024-03-04"]
