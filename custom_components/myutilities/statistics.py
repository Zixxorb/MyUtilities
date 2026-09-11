"""Long-term statistics import for the thirty-day charge history.

The summary page embeds the last thirty days of daily energy charge in the
chart's data array. A live sensor can only ever report today's number, so the
history is pushed into the recorder as external statistics instead. That
gives the Energy dashboard real daily cost bars going back a month, including
for the period before the integration was installed.

External statistics are keyed "myutilities:daily_energy_charge" and carry a
running sum, because that is what the recorder needs to compute deltas.
"""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.components.recorder.util import get_instance
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from .const import CURRENCY_USD, DOMAIN, STAT_DAILY_CHARGE
from .parser import DailyCharge

_LOGGER = logging.getLogger(__name__)


def _midnight_utc(day) -> datetime:
    """Local midnight of a day, as an aware datetime.

    Statistics starts must be timezone aware and aligned to the hour; local
    midnight satisfies both and keeps the daily buckets lined up with how the
    utility itself bills.
    """
    return datetime(
        day.year, day.month, day.day, tzinfo=dt_util.DEFAULT_TIME_ZONE
    )


async def async_import_daily_charges(
    hass: HomeAssistant,
    entry: ConfigEntry,
    charges: list[DailyCharge],
) -> None:
    """Push the daily charge history into long-term statistics."""
    if not charges:
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="MyUtilities daily energy charge",
        source=DOMAIN,
        statistic_id=STAT_DAILY_CHARGE,
        unit_of_measurement=CURRENCY_USD,
    )

    # Continue the existing sum rather than restarting it, or every restart
    # would look like a reset and the dashboard totals would be wrong.
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        STAT_DAILY_CHARGE,
        True,
        {"sum"},
    )

    running_sum = 0.0
    cutoff: datetime | None = None
    if last and STAT_DAILY_CHARGE in last and last[STAT_DAILY_CHARGE]:
        previous = last[STAT_DAILY_CHARGE][0]
        running_sum = float(previous.get("sum") or 0.0)
        start = previous.get("start")
        if start is not None:
            cutoff = dt_util.utc_from_timestamp(start)

    rows: list[StatisticData] = []
    for charge in charges:
        start = _midnight_utc(charge.day)
        # Skip days already recorded, so repeated polls don't double count.
        if cutoff is not None and start <= cutoff:
            continue
        running_sum += charge.charge
        rows.append(
            StatisticData(start=start, state=charge.charge, sum=running_sum)
        )

    if not rows:
        return

    _LOGGER.debug(
        "Importing %d day(s) of charge statistics, through %s",
        len(rows),
        rows[-1]["start"].date(),
    )
    async_add_external_statistics(hass, metadata, rows)
