"""Config flow for the MyUtilities (Cleveland Utilities) integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv

from .api import MyUtilitiesApiClient, MyUtilitiesApiError, MyUtilitiesAuthError
from .const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_USERNAME,
    CONF_UTILITY_CODE,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        # Required, and the reason this works for utilities other than
        # Cleveland: it is the tenant selector, read off the portal URL.
        # Optional, and only used when one login covers several utilities
        # and the portal answers with result="multi_util". A normal account
        # never needs it.
        vol.Optional(CONF_UTILITY_CODE): vol.All(
            cv.string, vol.Length(min=2, max=20), vol.Upper
        ),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): cv.string})


class MyUtilitiesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the MyUtilities config flow."""

    VERSION = 1

    async def _async_try_login(self, data: dict[str, Any]) -> dict[str, str]:
        """Attempt a login. Returns a dict of form errors (empty if it worked)."""
        client = MyUtilitiesApiClient(
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            utility_code=data.get(CONF_UTILITY_CODE),
            session=async_create_clientsession(
                self.hass, cookie_jar=aiohttp.CookieJar(unsafe=True)
            ),
        )

        try:
            await client.async_validate_credentials()
        except MyUtilitiesAuthError as err:
            _LOGGER.debug("Auth rejected: %s", err)
            return {"base": "invalid_auth"}
        except MyUtilitiesApiError as err:
            _LOGGER.debug("Connection problem: %s", err)
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - config flows must not raise
            _LOGGER.exception("Unexpected error validating MyUtilities credentials")
            return {"base": "unknown"}

        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = user_input[CONF_USERNAME].strip().lower()
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            errors = await self._async_try_login(user_input)
            if not errors:
                return self.async_create_entry(
                    title=f"MyUtilities ({user_input[CONF_USERNAME]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication when the stored password stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh password."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            candidate = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            errors = await self._async_try_login(candidate)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=candidate)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return MyUtilitiesOptionsFlow()


class MyUtilitiesOptionsFlow(OptionsFlow):
    """Let the user change how often we poll."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_HOURS, default=current
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_SCAN_INTERVAL_HOURS, max=MAX_SCAN_INTERVAL_HOURS
                        ),
                    )
                }
            ),
        )
