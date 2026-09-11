"""Tests for the MyUsage prepaid summary parser.

Run with:  python -m pytest tests/ -v

The fixture is a real captured page with personal details replaced. Keeping
it in the repo means a portal redesign shows up as a failing test rather than
as sensors quietly going unknown.
"""

from __future__ import annotations

from datetime import date
import importlib.util
import pathlib
import sys

# Load parser.py directly rather than importing the package: the package
# __init__ pulls in homeassistant and aiohttp, while the parser itself is
# pure stdlib and should stay testable without a Home Assistant install.
_PARSER_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "myutilities"
    / "parser.py"
)
_spec = importlib.util.spec_from_file_location("mu_parser", _PARSER_PATH)
_parser = importlib.util.module_from_spec(_spec)
# @dataclass resolves annotations via sys.modules, so register before exec.
sys.modules[_spec.name] = _parser
_spec.loader.exec_module(_parser)
parse_prepaid_summary = _parser.parse_prepaid_summary

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "prepaid_summary.html"
CAPTURED_ON = date(2026, 9, 11)


def _summary():
    return parse_prepaid_summary(
        FIXTURE.read_text(encoding="utf-8"), today=CAPTURED_ON
    )


def test_account_details():
    summary = _summary()
    assert summary.account_number == "999999-000000"
    assert summary.meter_status == "Active"


def test_balance_panel():
    summary = _summary()
    assert summary.account_balance == 32.51
    assert summary.balance_updated == date(2026, 9, 10)
    # The page renders an empty unpaid-balance box; that must read as absent,
    # not as zero, or a fake 0.00 lands in long-term statistics.
    assert summary.unpaid_balance is None


def test_usage_panels():
    summary = _summary()
    assert summary.estimated_days_left == 3
    assert summary.avg_daily_charge == 9.04
    assert summary.avg_daily_utility_charge == 5.20
    assert summary.last_energy_usage == 42
    assert summary.energy_rate_cents == 11.62
    assert summary.last_daily_utility_charge == 5.63


def test_payment_panel():
    summary = _summary()
    assert summary.last_payment == 100.00
    assert summary.last_payment_date == date(2026, 8, 28)


def test_every_panel_is_recognised():
    assert _summary().unmapped_labels == []


def test_chart_history():
    summary = _summary()
    charges = summary.daily_charges
    assert len(charges) == 29
    assert charges[0].day == date(2026, 8, 12)
    assert charges[0].charge == 6.00
    assert charges[0].temp_high == 88
    assert charges[0].temp_low == 67
    assert charges[-1].day == date(2026, 9, 9)
    assert charges[-1].charge == 5.63
    # Days must come out in order, since the statistics import walks them
    # sequentially to build a running sum.
    assert charges == sorted(charges, key=lambda c: c.day)


def test_last_daily_charge_matches_chart():
    # Cross-check: the "Last Daily Utility Charge" panel should agree with
    # the final bar on the chart. If these ever diverge, one of the two is
    # being read wrong.
    summary = _summary()
    assert summary.last_daily_utility_charge == summary.daily_charges[-1].charge


def test_year_inference_for_partial_dates():
    # The portal writes "posted on August 28" with no year. Read in January,
    # that must resolve to the previous year, not eleven months ahead.
    page = FIXTURE.read_text(encoding="utf-8")
    summary = parse_prepaid_summary(page, today=date(2027, 1, 5))
    assert summary.last_payment_date == date(2026, 8, 28)


def test_empty_page_yields_nothing():
    summary = parse_prepaid_summary("")
    assert summary.account_balance is None
    assert summary.daily_charges == []
