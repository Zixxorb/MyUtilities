"""Coordinator and runtime types for MyUtilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MyUtilitiesApiClient, MyUtilitiesApiError, MyUtilitiesAuthError
from .parser import PrepaidSummary
from .statistics import async_import_daily_charges

_LOGGER = logging.getLogger(__name__)


class MyUtilitiesCoordinator(DataUpdateCoordinator[PrepaidSummary]):
    """Polls the MyUsage portal and hands the result to the sensors."""

    config_entry: MyUtilitiesConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MyUtilitiesConfigEntry,
        client: MyUtilitiesApiClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="myutilities",
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> PrepaidSummary:
        """Fetch the latest summary from the portal."""
        try:
            summary = await self.client.async_get_summary()
        except MyUtilitiesAuthError as err:
            self.client.last_error = str(err)
            # Prompts the user to re-enter their password, rather than failing
            # quietly until they notice months later.
            raise ConfigEntryAuthFailed(str(err)) from err
        except MyUtilitiesApiError as err:
            self.client.last_error = str(err)
            raise UpdateFailed(str(err)) from err

        self.client.last_error = None

        # Backfilling the thirty-day history is a bonus, not the point of the
        # update. If the recorder rejects it, the sensors should still work.
        if summary.daily_charges:
            try:
                await async_import_daily_charges(
                    self.hass, self.config_entry, summary.daily_charges
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not import daily charge statistics: %s", err
                )

        return summary


@dataclass
class MyUtilitiesRuntimeData:
    """Objects kept alive for the lifetime of a config entry."""

    client: MyUtilitiesApiClient
    coordinator: MyUtilitiesCoordinator


type MyUtilitiesConfigEntry = ConfigEntry[MyUtilitiesRuntimeData]
