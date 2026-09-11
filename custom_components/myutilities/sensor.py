"""Sensor platform for MyUtilities (MyUsage prepaid)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import CURRENCY_USD, DOMAIN
from .coordinator import MyUtilitiesConfigEntry, MyUtilitiesCoordinator
from .parser import PrepaidSummary


def _midnight(day: date | None) -> datetime | None:
    """Local midnight at the start of a day, for last_reset."""
    if day is None:
        return None
    return datetime(
        day.year, day.month, day.day, tzinfo=dt_util.DEFAULT_TIME_ZONE
    )


def _latest(summary: PrepaidSummary) -> Any:
    """The most recent day in the thirty-day chart, if present."""
    return summary.daily_charges[-1] if summary.daily_charges else None


# SensorEntityDescription is a frozen, keyword-only dataclass in current Home
# Assistant. Subclassing with a plain @dataclass raises "cannot inherit
# non-frozen dataclass from a frozen one" at import, which takes the whole
# platform down with it.
@dataclass(frozen=True, kw_only=True)
class MyUtilitiesSensorEntityDescription(SensorEntityDescription):
    """Describes a MyUtilities sensor."""

    value_fn: Callable[[PrepaidSummary], Any]
    attributes_fn: Callable[[PrepaidSummary], dict[str, Any]] | None = None
    last_reset_fn: Callable[[PrepaidSummary], datetime | None] | None = None


SENSOR_DESCRIPTIONS: tuple[MyUtilitiesSensorEntityDescription, ...] = (
    MyUtilitiesSensorEntityDescription(
        key="account_balance",
        name="Account balance",
        native_unit_of_measurement=CURRENCY_USD,
        device_class=SensorDeviceClass.MONETARY,
        # No state class: a prepay balance moves both ways, and marking it
        # TOTAL_INCREASING would make every top-up look like consumption.
        suggested_display_precision=2,
        icon="mdi:cash",
        value_fn=lambda s: s.account_balance,
        attributes_fn=lambda s: {
            "balance_updated": s.balance_updated.isoformat()
            if s.balance_updated
            else None,
            "account_number": s.account_number,
        },
    ),
    MyUtilitiesSensorEntityDescription(
        key="unpaid_balance",
        name="Unpaid balance",
        native_unit_of_measurement=CURRENCY_USD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        icon="mdi:cash-remove",
        value_fn=lambda s: s.unpaid_balance,
    ),
    MyUtilitiesSensorEntityDescription(
        key="estimated_days_left",
        name="Estimated days left",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:calendar-clock",
        value_fn=lambda s: s.estimated_days_left,
    ),
    MyUtilitiesSensorEntityDescription(
        key="last_energy_usage",
        name="Last daily energy usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        # A daily figure polled once a day has to be TOTAL with an explicit
        # last_reset. TOTAL_INCREASING would read each daily drop as a meter
        # reset and inflate the statistics.
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        icon="mdi:lightning-bolt",
        value_fn=lambda s: s.last_energy_usage,
        last_reset_fn=lambda s: _midnight(s.last_reading_day),
    ),
    MyUtilitiesSensorEntityDescription(
        key="energy_rate",
        name="Energy rate",
        native_unit_of_measurement=f"¢/{UnitOfEnergy.KILO_WATT_HOUR}",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:cash-clock",
        value_fn=lambda s: s.energy_rate_cents,
    ),
    MyUtilitiesSensorEntityDescription(
        key="last_daily_charge",
        name="Last daily charge",
        native_unit_of_measurement=CURRENCY_USD,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:currency-usd",
        value_fn=lambda s: s.last_daily_utility_charge,
        last_reset_fn=lambda s: _midnight(s.last_reading_day),
    ),
    MyUtilitiesSensorEntityDescription(
        key="avg_daily_charge",
        name="Average daily charge",
        native_unit_of_measurement=CURRENCY_USD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        icon="mdi:chart-line",
        value_fn=lambda s: s.avg_daily_charge,
    ),
    MyUtilitiesSensorEntityDescription(
        key="avg_daily_utility_charge",
        name="Average daily utility charge",
        native_unit_of_measurement=CURRENCY_USD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        icon="mdi:chart-line",
        value_fn=lambda s: s.avg_daily_utility_charge,
    ),
    MyUtilitiesSensorEntityDescription(
        key="last_payment",
        name="Last payment",
        native_unit_of_measurement=CURRENCY_USD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        icon="mdi:credit-card-check",
        value_fn=lambda s: s.last_payment,
        attributes_fn=lambda s: {
            "posted_on": s.last_payment_date.isoformat()
            if s.last_payment_date
            else None,
        },
    ),
    MyUtilitiesSensorEntityDescription(
        key="meter_status",
        name="Meter status",
        icon="mdi:gauge",
        value_fn=lambda s: s.meter_status,
    ),
    MyUtilitiesSensorEntityDescription(
        key="last_reading_date",
        name="Last reading date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-check",
        value_fn=lambda s: s.last_reading_day,
    ),
    # Outdoor temperatures come free with the charge chart. Diagnostic
    # category so they don't clutter the main device page.
    MyUtilitiesSensorEntityDescription(
        key="reading_day_temp_high",
        name="Reading day high temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:thermometer-high",
        value_fn=lambda s: (_latest(s).temp_high if _latest(s) else None),
    ),
    MyUtilitiesSensorEntityDescription(
        key="reading_day_temp_low",
        name="Reading day low temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:thermometer-low",
        value_fn=lambda s: (_latest(s).temp_low if _latest(s) else None),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyUtilitiesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyUtilities sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    summary = coordinator.data

    # Only create entities for figures this utility actually publishes. A
    # postpay account has no prepay balance; a different tenant may omit
    # panels entirely. Creating them anyway would leave permanent "unknown"
    # entities that people then try to debug.
    entities = [
        MyUtilitiesSensor(coordinator, description, entry.entry_id)
        for description in SENSOR_DESCRIPTIONS
        if description.value_fn(summary) is not None
    ]

    async_add_entities(entities)


class MyUtilitiesSensor(CoordinatorEntity[MyUtilitiesCoordinator], SensorEntity):
    """A single MyUtilities sensor."""

    entity_description: MyUtilitiesSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyUtilitiesCoordinator,
        description: MyUtilitiesSensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="MyUtilities",
            manufacturer="Exceleron MyUsage",
            model="Prepaid account",
            configuration_url="https://www.myusage.com/",
        )

    @property
    def native_value(self) -> Any:
        """Return the current value, or None if the portal did not report it."""
        summary = self.coordinator.data
        if summary is None:
            return None
        return self.entity_description.value_fn(summary)

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of the period a daily total covers."""
        if self.entity_description.last_reset_fn is None:
            return None
        summary = self.coordinator.data
        if summary is None:
            return None
        return self.entity_description.last_reset_fn(summary)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attributes_fn is None:
            return None
        summary = self.coordinator.data
        if summary is None:
            return None
        return self.entity_description.attributes_fn(summary)
