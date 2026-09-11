"""Parsing for the MyUsage Prepaid account summary page.

Everything here is written against a real captured page rather than guessed.
The page is ColdFusion-generated and its structure is highly regular, which
lets us key off labels instead of counting numbers:

    <div class="box"><h3>Current Balance</h3><h2>$32.51</h2>
        <span>last updated on September 10</span></div>

So each figure is looked up by its own <h3> label. A utility that doesn't
offer a given box simply doesn't produce that key, which is what makes this
survive across the different tenants Exceleron hosts.

The page also embeds thirty days of daily charge history in a JavaScript
array for its chart:

    var chartData1 = [
        {"TempLow": 67, "TempHigh": 88,
         "GraphDayFormat": "08/12/2026", "ChargeTotal": 6.0000},
        ...
    ];

That's the most valuable thing on the page and is extracted separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import html as html_module
import json
import logging
import re
from typing import Any

_LOGGER = logging.getLogger(__name__)

# One "box" panel: label, value, and a small note underneath.
_BOX_RE = re.compile(
    r"<div\s+class=\"box\">\s*"
    r"<h3>(?P<label>.*?)</h3>\s*"
    r"<h2>(?P<value>.*?)</h2>\s*"
    r"(?:<span>(?P<note>.*?)</span>)?",
    re.IGNORECASE | re.DOTALL,
)

_ACCOUNT_RE = re.compile(
    r"<b>Account:</b>\s*([0-9-]+)", re.IGNORECASE
)
_METER_STATUS_RE = re.compile(
    r"<b>Meter Status:</b>\s*([A-Za-z ]+?)\s*<", re.IGNORECASE
)
_CHART_RE = re.compile(
    r"var\s+chartData1\s*=\s*(\[.*?\])\s*;", re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(raw: str | None) -> str:
    """Strip tags and entities from a fragment of markup."""
    if not raw:
        return ""
    cleaned = _TAG_RE.sub(" ", raw)
    cleaned = html_module.unescape(cleaned)
    # The page uses a bare &nbsp (no semicolon) as an empty placeholder.
    cleaned = cleaned.replace("&nbsp", " ").replace("\xa0", " ")
    return " ".join(cleaned.split())


def _money(raw: str) -> float | None:
    """Parse '$32.51' or '-$4.00' into a float."""
    match = re.search(r"(-?)\s*\$\s*(-?[0-9,]+(?:\.[0-9]+)?)", raw)
    if not match:
        return None
    try:
        value = float(match.group(2).replace(",", ""))
    except ValueError:
        return None
    return -value if match.group(1) == "-" and value > 0 else value


def _number(raw: str) -> float | None:
    """Parse the first bare number out of a string."""
    match = re.search(r"(-?[0-9,]+(?:\.[0-9]+)?)", raw)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _cents(raw: str) -> float | None:
    """Parse 'rated at 11.62¢ per kWh' into 11.62."""
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:¢|cent)", raw, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _partial_date(raw: str, today: date | None = None) -> date | None:
    """Parse 'last updated on September 10' - the year is not stated.

    The portal omits the year, so assume the most recent occurrence: if the
    parsed month/day is in the future relative to today, it belongs to last
    year. Without this, every January reading would jump forward a year.
    """
    match = re.search(r"([A-Z][a-z]+)\s+(\d{1,2})", raw)
    if not match:
        return None
    today = today or date.today()
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(
                f"{match.group(1)} {match.group(2)}", fmt
            ).date()
        except ValueError:
            continue
        candidate = parsed.replace(year=today.year)
        if candidate > today:
            candidate = candidate.replace(year=today.year - 1)
        return candidate
    return None


@dataclass
class DailyCharge:
    """One day from the thirty-day chart."""

    day: date
    charge: float
    temp_high: float | None = None
    temp_low: float | None = None


@dataclass
class PrepaidSummary:
    """Everything we can read off the Prepaid account summary page."""

    account_number: str | None = None
    meter_status: str | None = None

    account_balance: float | None = None
    balance_updated: date | None = None
    unpaid_balance: float | None = None

    estimated_days_left: float | None = None
    avg_daily_charge: float | None = None
    avg_daily_utility_charge: float | None = None

    last_energy_usage: float | None = None
    energy_rate_cents: float | None = None
    last_daily_utility_charge: float | None = None

    last_payment: float | None = None
    last_payment_date: date | None = None

    daily_charges: list[DailyCharge] = field(default_factory=list)
    # Labels we saw but had no mapping for. Surfaced in diagnostics so a
    # utility with extra boxes shows up as a feature request, not a mystery.
    unmapped_labels: list[str] = field(default_factory=list)

    @property
    def last_reading_day(self) -> date | None:
        """The day the latest figures describe."""
        if self.daily_charges:
            return self.daily_charges[-1].day
        return self.balance_updated


def parse_chart_data(page: str) -> list[DailyCharge]:
    """Extract the thirty-day daily charge series from the chart's JS array."""
    match = _CHART_RE.search(page)
    if not match:
        return []

    raw = match.group(1)
    # The generated array has trailing commas and whitespace that json
    # rejects, so tidy it rather than hand-rolling a parser.
    raw = re.sub(r",\s*(?=[}\]])", "", raw)
    raw = re.sub(r"\s+", " ", raw)

    try:
        rows = json.loads(raw)
    except ValueError as err:
        _LOGGER.debug("Could not decode chartData1: %s", err)
        return []

    charges: list[DailyCharge] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_day = row.get("GraphDayFormat")
        if not raw_day:
            continue
        try:
            day = datetime.strptime(str(raw_day), "%m/%d/%Y").date()
        except ValueError:
            continue
        total = row.get("ChargeTotal")
        if total is None:
            continue
        try:
            charge = float(total)
        except (TypeError, ValueError):
            continue

        def _opt(key: str) -> float | None:
            value = row.get(key)
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        charges.append(
            DailyCharge(
                day=day,
                charge=charge,
                temp_high=_opt("TempHigh"),
                temp_low=_opt("TempLow"),
            )
        )

    charges.sort(key=lambda item: item.day)
    return charges


def parse_prepaid_summary(page: str, today: date | None = None) -> PrepaidSummary:
    """Parse the Prepaid account summary page into a structured result."""
    summary = PrepaidSummary()

    if not page:
        return summary

    account = _ACCOUNT_RE.search(page)
    if account:
        summary.account_number = account.group(1)

    status = _METER_STATUS_RE.search(page)
    if status:
        summary.meter_status = status.group(1).strip()

    for box in _BOX_RE.finditer(page):
        label = _text(box.group("label"))
        value = _text(box.group("value"))
        note = _text(box.group("note"))

        if not label:
            continue

        key = label.lower()

        if key == "current balance":
            summary.account_balance = _money(value)
            summary.balance_updated = _partial_date(note, today)
        elif key == "unpaid balance":
            summary.unpaid_balance = _money(value)
        elif key == "estimated days left":
            summary.estimated_days_left = _number(value)
        elif key == "avg daily charge":
            summary.avg_daily_charge = _money(value)
            summary.avg_daily_utility_charge = _money(note)
        elif key == "last energy usage":
            summary.last_energy_usage = _number(value)
            summary.energy_rate_cents = _cents(note)
        elif key == "last daily utility charge":
            summary.last_daily_utility_charge = _money(value)
        elif key == "last payment":
            summary.last_payment = _money(value)
            summary.last_payment_date = _partial_date(note, today)
        else:
            summary.unmapped_labels.append(label)

    summary.daily_charges = parse_chart_data(page)
    return summary
