"""Config flow for MyUtilities (Cleveland Utilities) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .api import MyUtilitiesApiClient, MyUtilitiesAuthError, MyUtilitiesApiError
from .const import CONF_ACCOUNT_NUMBER, CONF_PASSWORD, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_ACCOUNT_NUMBER): cv.string,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate user credentials against MyUtilities API."""
    client = MyUtilitiesApiClient(
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        account_number=data.get(CONF_ACCOUNT_NUMBER),
    )

    valid = await client.async_validate_credentials()
    if not valid:
        raise MyUtilitiesAuthError("Invalid username or password")

    return {"title": f"MyUtilities ({data[CONF_USERNAME]})"}


class MyUtilitiesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyUtilities."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Ensure unique entry based on username & optional account number
            unique_id = f"{user_input[CONF_USERNAME]}_{user_input.get(CONF_ACCOUNT_NUMBER, '')}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except MyUtilitiesAuthError:
                errors["base"] = "invalid_auth"
            except MyUtilitiesApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during MyUtilities setup")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
