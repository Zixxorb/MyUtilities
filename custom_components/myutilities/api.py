"""API Client for MyUtilities (Cleveland Utilities / MyUsage)."""

from __future__ import annotations

import logging
import re
from typing import Any
import aiohttp

_LOGGER = logging.getLogger(__name__)

MYUSAGE_BASE_URL = "https://www.myusage.com"
MYUSAGE_LOGIN_URL = f"{MYUSAGE_BASE_URL}/index.cfm"
MYUSAGE_DATA_URL = f"{MYUSAGE_BASE_URL}/data.cfm"


class MyUtilitiesApiError(Exception):
    """Exception raised for general MyUtilities API errors."""


class MyUtilitiesAuthError(MyUtilitiesApiError):
    """Exception raised for authentication errors."""


class MyUtilitiesApiClient:
    """Asynchronous client for Cleveland Utilities / MyUsage ColdFusion service."""

    def __init__(
        self,
        username: str,
        password: str,
        account_number: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the client."""
        self.username = username
        self.password = password
        self.account_number = account_number
        self._session = session
        self._logged_in = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession with cookie storage."""
        if self._session is None or self._session.closed:
            cookie_jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(cookie_jar=cookie_jar)
        return self._session

    async def async_login(self) -> bool:
        """Authenticate with the MyUsage portal (index.cfm -> data.cfm session)."""
        session = await self._get_session()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded",
        }

        form_data = {
            "username": self.username,
            "password": self.password,
            "accountNumber": self.account_number or "",
            "btnSubmit": "Login",
        }

        try:
            async with session.post(
                MYUSAGE_LOGIN_URL, data=form_data, headers=headers, timeout=15
            ) as response:
                html_text = await response.text()
                if response.status in (401, 403) or "Invalid Login" in html_text or "incorrect password" in html_text.lower():
                    raise MyUtilitiesAuthError("Invalid username or password for MyUsage")

                self._logged_in = True
                _LOGGER.info("Successfully authenticated with MyUsage session")
                return True
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error connecting to MyUsage: %s", err)
            raise MyUtilitiesApiError(f"Cannot connect to MyUsage portal: {err}") from err

    async def async_validate_credentials(self) -> bool:
        """Validate credentials during Home Assistant config flow."""
        return await self.async_login()

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch latest utility usage and account data from data.cfm every 24 hours."""
        if not self._logged_in:
            await self.async_login()

        session = await self._get_session()
        params = {"appPage": "Prepaid"}

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        try:
            async with session.get(
                MYUSAGE_DATA_URL, params=params, headers=headers, timeout=20
            ) as response:
                if response.status == 200:
                    html_content = await response.text()
                    parsed_data = self._parse_myusage_html(html_content)
                    if parsed_data:
                        return parsed_data
        except Exception as err:
            _LOGGER.warning("Error fetching MyUsage data.cfm: %s. Using default structure.", err)

        return await self.async_fetch_fallback_metrics()

    def _parse_myusage_html(self, html: str) -> dict[str, Any]:
        """Extract usage and balance numbers from data.cfm HTML content."""
        data = {}

        # Parse Account Balance ($)
        balance_match = re.search(r"balance[^\$\d]*\$?\s*([0-9]+\.[0-9]{2})", html, re.IGNORECASE)
        if balance_match:
            data["account_balance"] = float(balance_match.group(1))

        # Parse Electric Usage (kWh)
        electric_match = re.search(r"([0-9]+\.?[0-9]*)\s*kWh", html, re.IGNORECASE)
        if electric_match:
            data["electric_usage"] = float(electric_match.group(1))

        # Parse Water Usage (Gallons / CCF)
        water_match = re.search(r"([0-9]+\.?[0-9]*)\s*(Gal|Gallons|CCF)", html, re.IGNORECASE)
        if water_match:
            data["water_usage"] = float(water_match.group(1))

        # Parse Daily Cost ($)
        cost_match = re.search(r"cost[^\$\d]*\$?\s*([0-9]+\.[0-9]{2})", html, re.IGNORECASE)
        if cost_match:
            data["daily_cost"] = float(cost_match.group(1))

        # Parse Last Meter Reading & Date
        meter_match = re.search(r"meter\s*reading[^\d]*([0-9]+\.?[0-9]*)", html, re.IGNORECASE)
        if meter_match:
            data["last_meter_reading"] = float(meter_match.group(1))

        date_match = re.search(r"([0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", html)
        if date_match:
            data["last_meter_date"] = date_match.group(1)

        return data

    async def async_fetch_fallback_metrics(self) -> dict[str, Any]:
        """Fallback values if session parsing encounters empty page data."""
        return {
            "electric_usage": 0.0,
            "water_usage": 0.0,
            "daily_cost": 0.0,
            "account_balance": 0.0,
            "last_meter_reading": 0.0,
            "last_meter_date": "",
        }

