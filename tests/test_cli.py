"""Tests for `python -m propsim`: output contents and failure exit codes."""

import subprocess
import sys
from pathlib import Path

import pytest

from propsim.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]

GOOD_CSV = """
Close Time,Symbol,Gross P/L,Net P/L
2024-03-01 09:31:00,MGC,124.5,120.0
2024-03-01 10:02:00,MGC,-40.5,-45.0
2024-03-04 09:45:00,MGC,314.5,310.0
2024-03-05 09:45:00,MGC,-95.5,-100.0
2024-03-06 11:05:00,MGC,204.5,200.0
2024-03-07 09:15:00,MGC,84.5,80.0
"""


@pytest.fixture
def trades_csv(tmp_path):
    path = tmp_path / "trades.csv"
    path.write_text(GOOD_CSV.strip() + "\n", encoding="utf-8")
    return path


class TestReportContents:
    def test_reports_every_requested_section(self, trades_csv, capsys):
        code = main([str(trades_csv), "-n", "200", "--sweep-runs", "100", "--seed", "1"])
        out = capsys.readouterr().out

        assert code == 0
        assert "PASS RATE" in out
        assert "outcomes:" in out            # failure-mode breakdown
        assert "trailing_drawdown" in out or "timeout" in out
        assert "median days to pass:" in out
        assert "position-size sweep" in out
        for multiplier in ("1", "2", "3", "4"):
            assert f"  {multiplier:<8s}" in out

    def test_reports_the_columns_it_inferred(self, trades_csv, capsys):
        main([str(trades_csv), "-n", "50", "--no-sweep"])
        out = capsys.readouterr().out

        assert "'Close Time'" in out
        assert "'Net P/L'" in out  # not the gross column

    def test_warns_that_the_ruleset_is_unverified(self, trades_csv, capsys):
        main([str(trades_csv), "-n", "50", "--no-sweep"])
        err = capsys.readouterr().err

        assert "UNVERIFIED" in err
        assert "multi-day losing streaks are not reproduced" in err

    def test_warns_when_the_sample_is_thin(self, trades_csv, capsys):
        main([str(trades_csv), "-n", "50", "--no-sweep"])
        err = capsys.readouterr().err

        assert "only 5 trading days" in err

    def test_no_sweep_flag(self, trades_csv, capsys):
        main([str(trades_csv), "-n", "50", "--no-sweep"])
        out = capsys.readouterr().out

        assert "position-size sweep" not in out

    def test_seed_makes_the_report_reproducible(self, trades_csv, capsys):
        main([str(trades_csv), "-n", "200", "--seed", "42", "--no-sweep"])
        first = capsys.readouterr().out
        main([str(trades_csv), "-n", "200", "--seed", "42", "--no-sweep"])
        second = capsys.readouterr().out

        assert first == second

    def test_ruleset_overrides_are_reported_and_applied(self, trades_csv, capsys):
        main([str(trades_csv), "-n", "50", "--no-sweep", "--start", "150000",
              "--target", "9000", "--trail", "5000"])
        out = capsys.readouterr().out

        assert "start 150,000" in out
        assert "target +9,000" in out
        assert "trail 5,000" in out


class TestFailureExits:
    """A bad input must exit non-zero with a message, never print a number."""

    def test_single_day_csv_exits_with_an_error(self, tmp_path, capsys):
        path = tmp_path / "one_day.csv"
        path.write_text(
            "timestamp,pnl\n2024-03-01 09:31:00,120\n2024-03-01 10:02:00,-45\n",
            encoding="utf-8",
        )

        code = main([str(path)])
        captured = capsys.readouterr()

        assert code == 2
        assert "1 trading day" in captured.err
        assert "PASS RATE" not in captured.out
        assert captured.out == ""

    def test_empty_csv_exits_with_an_error(self, tmp_path, capsys):
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")

        code = main([str(path)])
        captured = capsys.readouterr()

        assert code == 2
        assert "no header row" in captured.err
        assert captured.out == ""

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        code = main([str(tmp_path / "nope.csv")])

        assert code == 2
        assert "not found" in capsys.readouterr().err

    def test_impossible_ruleset_exits_with_an_error(self, trades_csv, capsys):
        code = main([str(trades_csv), "--trail", "0"])

        assert code == 2
        assert "invalid ruleset" in capsys.readouterr().err


class TestModuleEntryPoint:
    def test_python_dash_m_propsim_runs(self, trades_csv):
        proc = subprocess.run(
            [sys.executable, "-m", "propsim", str(trades_csv), "-n", "100",
             "--sweep-runs", "50"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )

        assert proc.returncode == 0, proc.stderr
        assert "PASS RATE" in proc.stdout

    def test_exit_code_propagates_to_the_shell(self, tmp_path):
        path = tmp_path / "one_day.csv"
        path.write_text("timestamp,pnl\n2024-03-01 09:31:00,120\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "-m", "propsim", str(path)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )

        assert proc.returncode == 2
        assert "1 trading day" in proc.stderr
