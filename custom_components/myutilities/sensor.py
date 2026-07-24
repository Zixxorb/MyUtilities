"""Sensor platform for MyUtilities (Cleveland Utilities)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CURRENCY_DOLLAR,
    UnitOfEnergy,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    SENSOR_ACCOUNT_BALANCE,
    SENSOR_DAILY_COST,
    SENSOR_ELECTRIC_USAGE,
    SENSOR_LAST_METER_DATE,
    SENSOR_LAST_METER_READING,
    SENSOR_WATER_USAGE,
)


@dataclass
class MyUtilitiesSensorEntityDescription(SensorEntityDescription):
    """Class describing MyUtilities sensor entities."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[MyUtilitiesSensorEntityDescription, ...] = (
    MyUtilitiesSensorEntityDescription(
        key=SENSOR_ELECTRIC_USAGE,
        name="MyUtilities Daily Electric Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt",
        value_fn=lambda data: data.get("electric_usage"),
    ),
    MyUtilitiesSensorEntityDescription(
        key=SENSOR_WATER_USAGE,
        name="MyUtilities Daily Water Usage",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:water",
        value_fn=lambda data: data.get("water_usage"),
    ),
    MyUtilitiesSensorEntityDescription(
        key=SENSOR_DAILY_COST,
        name="MyUtilities Daily Usage Cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:currency-usd",
        value_fn=lambda data: data.get("daily_cost"),
    ),
    MyUtilitiesSensorEntityDescription(
        key=SENSOR_ACCOUNT_BALANCE,
        name="MyUtilities Account Balance",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        device_class=SensorDeviceClass.MONETARY,
        icon="mdi:account-cash",
        value_fn=lambda data: data.get("account_balance"),
    ),
    MyUtilitiesSensorEntityDescription(
        key=SENSOR_LAST_METER_READING,
        name="MyUtilities Last Meter Reading",
        icon="mdi:counter",
        value_fn=lambda data: data.get("last_meter_reading"),
        attributes_fn=lambda data: {
            "last_meter_read_date": data.get("last_meter_date"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyUtilities sensors based on config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DataUpdateCoordinator = entry_data["coordinator"]

    entities = [
        MyUtilitiesSensor(
            coordinator=coordinator,
            description=description,
            entry_id=entry.entry_id,
        )
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class MyUtilitiesSensor(CoordinatorEntity, SensorEntity):
    """Representation of a MyUtilities Sensor."""

    entity_description: MyUtilitiesSensorEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: MyUtilitiesSensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="MyUtilities (Cleveland Utilities)",
            manufacturer="Cleveland Utilities / MyUsage",
            model="Utility Data Collector",
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return device state attributes."""
        if self.coordinator.data and self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(self.coordinator.data)
        return None
