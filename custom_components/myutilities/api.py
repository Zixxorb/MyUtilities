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
        """Authenticate with the MyUsage portal (GET initial cookies -> POST credentials)."""
        session = await self._get_session()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            # 1. Fetch index page first to establish ColdFusion session cookies
            async with session.get(MYUSAGE_LOGIN_URL, headers=headers, timeout=15) as get_resp:
                _LOGGER.debug("Fetched MyUsage login page, status: %s", get_resp.status)

            # 2. Prepare form payload supporting common MyUsage form field names
            form_data = {
                "username": self.username,
                "user": self.username,
                "txtUsername": self.username,
                "password": self.password,
                "pass": self.password,
                "txtPassword": self.password,
                "accountNumber": self.account_number or "",
                "account": self.account_number or "",
                "btnSubmit": "Login",
                "submit": "Login",
            }

            post_headers = {
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": MYUSAGE_LOGIN_URL,
            }

            async with session.post(
                MYUSAGE_LOGIN_URL, data=form_data, headers=post_headers, timeout=15
            ) as response:
                html_text = await response.text()
                
                if response.status in (401, 403) or "Invalid Login" in html_text or "incorrect password" in html_text.lower():
                    _LOGGER.error("MyUsage login failed: invalid credentials")
                    raise MyUtilitiesAuthError("Invalid username or password for MyUsage")

                self._logged_in = True
                _LOGGER.info("Successfully authenticated session with MyUsage portal")
                return True

        except aiohttp.ClientError as err:
            _LOGGER.error("Network error connecting to MyUsage portal: %s", err)
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
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": MYUSAGE_LOGIN_URL,
        }

        try:
            async with session.get(
                MYUSAGE_DATA_URL, params=params, headers=headers, timeout=20
            ) as response:
                _LOGGER.debug("Fetched data.cfm response status: %s", response.status)
                if response.status == 200:
                    html_content = await response.text()
                    parsed_data = self._parse_myusage_html(html_content)
                    _LOGGER.info("Parsed MyUsage metrics: %s", parsed_data)
                    return parsed_data
                elif response.status in (401, 403):
                    _LOGGER.warning("Session expired, re-authenticating with MyUsage...")
                    self._logged_in = False
                    await self.async_login()
        except Exception as err:
            _LOGGER.error("Error fetching MyUsage data.cfm: %s", err)

        return self._get_default_metrics()

    def _parse_myusage_html(self, html: str) -> dict[str, Any]:
        """Extract usage, cost, balance, and meter numbers from data.cfm HTML content."""
        data = self._get_default_metrics()

        if not html:
            _LOGGER.warning("Received empty HTML content from MyUsage")
            return data

        _LOGGER.debug("MyUsage HTML snippet (first 300 chars): %s", html[:300])

        # Parse Account Balance ($) - matches '$123.45', 'Balance: $123.45', 'Balance 123.45'
        balance_match = (
            re.search(r"(?:balance|prepay|account balance)[^\$\d]*\$?\s*(-?[0-9,]+\.[0-9]{2})", html, re.IGNORECASE)
            or re.search(r"\$\s*(-?[0-9,]+\.[0-9]{2})", html)
        )
        if balance_match:
            try:
                data["account_balance"] = float(balance_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Parse Electric Usage (kWh) - matches '32.4 kWh', 'kWh: 32.4', 'Electric 32.4'
        electric_match = (
            re.search(r"([0-9,]+\.?[0-9]*)\s*kwh", html, re.IGNORECASE)
            or re.search(r"electric[^\d]*([0-9,]+\.?[0-9]*)", html, re.IGNORECASE)
        )
        if electric_match:
            try:
                data["electric_usage"] = float(electric_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Parse Water Usage (Gallons / CCF) - matches '145 Gal', '145 Gallons', '14.5 CCF'
        water_match = (
            re.search(r"([0-9,]+\.?[0-9]*)\s*(?:gal|gallons|ccf)", html, re.IGNORECASE)
            or re.search(r"water[^\d]*([0-9,]+\.?[0-9]*)", html, re.IGNORECASE)
        )
        if water_match:
            try:
                data["water_usage"] = float(water_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Parse Daily Cost ($) - matches 'Cost: $4.85', 'Daily Cost $4.85'
        cost_match = re.search(r"(?:daily cost|cost|charge)[^\$\d]*\$?\s*([0-9,]+\.[0-9]{2})", html, re.IGNORECASE)
        if cost_match:
            try:
                data["daily_cost"] = float(cost_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Parse Last Meter Reading & Date
        meter_match = re.search(r"(?:meter|reading)[^\d]*([0-9,]+\.?[0-9]*)", html, re.IGNORECASE)
        if meter_match:
            try:
                data["last_meter_reading"] = float(meter_match.group(1).replace(",", ""))
            except ValueError:
                pass

        date_match = re.search(r"([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", html)
        if date_match:
            data["last_meter_date"] = date_match.group(1)

        return data

    def _get_default_metrics(self) -> dict[str, Any]:
        """Return default metrics dictionary guaranteeing all keys exist."""
        return {
            "electric_usage": 0.0,
            "water_usage": 0.0,
            "daily_cost": 0.0,
            "account_balance": 0.0,
            "last_meter_reading": 0.0,
            "last_meter_date": "N/A",
        }


