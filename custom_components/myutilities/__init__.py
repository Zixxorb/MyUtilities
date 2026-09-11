"""Home Assistant custom component for MyUtilities (Cleveland Utilities)."""

from __future__ import annotations

from datetime import timedelta

import aiohttp

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import MyUtilitiesApiClient
from .const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_USERNAME,
    CONF_UTILITY_CODE,
    DEFAULT_SCAN_INTERVAL_HOURS,
)
from .coordinator import (
    MyUtilitiesConfigEntry,
    MyUtilitiesCoordinator,
    MyUtilitiesRuntimeData,
)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: MyUtilitiesConfigEntry
) -> bool:
    """Set up MyUtilities from a config entry."""
    # A private cookie jar: the portal's session cookie must not be mixed
    # into the session shared by every other integration. auto_cleanup means
    # Home Assistant closes this for us on unload.
    session = async_create_clientsession(
        hass,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )

    client = MyUtilitiesApiClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
        utility_code=entry.data.get(CONF_UTILITY_CODE),
    )

    hours = entry.options.get(
        CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
    )

    coordinator = MyUtilitiesCoordinator(
        hass, entry, client, timedelta(hours=hours)
    )

    # Raises ConfigEntryNotReady on failure, so a broken setup is visible on
    # the integrations page instead of producing entities full of zeros.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = MyUtilitiesRuntimeData(
        client=client, coordinator=coordinator
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(
    hass: HomeAssistant, entry: MyUtilitiesConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: MyUtilitiesConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
