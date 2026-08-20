"""API Client for MyUtilities (Cleveland Utilities / MyUsage)."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin
import aiohttp

_LOGGER = logging.getLogger(__name__)

MYUSAGE_BASE_URL = "https://www.myusage.com"
MYUSAGE_LOGIN_URL = f"{MYUSAGE_BASE_URL}/login"
MYUSAGE_ROOT_URL = f"{MYUSAGE_BASE_URL}/"


class MyUtilitiesApiError(Exception):
    """Exception raised for general MyUtilities API errors."""


class MyUtilitiesAuthError(MyUtilitiesApiError):
    """Exception raised for authentication errors."""


class MyUtilitiesApiClient:
    """Asynchronous client for Cleveland Utilities / MyUsage service."""

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
        self._data_url: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession with cookie storage."""
        if self._session is None or self._session.closed:
            cookie_jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(cookie_jar=cookie_jar)
        return self._session

    async def async_login(self) -> bool:
        """Authenticate with the MyUsage portal via /login endpoint."""
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
            # 1. Fetch root page to initialize session and CSRF/session cookies
            async with session.get(MYUSAGE_ROOT_URL, headers=headers, timeout=15) as root_resp:
                _LOGGER.debug("Loaded MyUsage home page, status: %s", root_resp.status)

            # 2. Submit credentials to /login via XMLHttpRequest
            login_headers = {
                "User-Agent": headers["User-Agent"],
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": MYUSAGE_ROOT_URL,
                "Origin": MYUSAGE_BASE_URL,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }

            form_data = {
                "email": self.username,
                "password": self.password,
            }

            if self.account_number:
                form_data["uc"] = self.account_number

            _LOGGER.debug("Submitting login request to %s for user %s", MYUSAGE_LOGIN_URL, self.username)

            async with session.post(
                MYUSAGE_LOGIN_URL, data=form_data, headers=login_headers, timeout=20
            ) as response:
                _LOGGER.debug("Login HTTP response status: %s", response.status)

                if response.status == 200:
                    try:
                        res_json = await response.json(content_type=None)
                        _LOGGER.debug("Login JSON response: %s", res_json)
                    except Exception:
                        res_text = await response.text()
                        _LOGGER.warning("Non-JSON response from /login: %s", res_text[:200])
                        res_json = {}

                    result = res_json.get("result")

                    if result == "error":
                        error_msg = res_json.get("error_str") or res_json.get("error_msg") or "Invalid credentials"
                        _LOGGER.error("MyUsage authentication error: %s", error_msg)
                        raise MyUtilitiesAuthError(f"MyUsage login failed: {error_msg}")

                    if result == "multi_util":
                        _LOGGER.info("Multiple utilities found for account; selecting utility...")
                        utils = res_json.get("data", {}).get("utilities", [])
                        selected_code = None
                        if self.account_number:
                            for u in utils:
                                if str(u.get("Code")) == str(self.account_number):
                                    selected_code = u.get("Code")
                                    break
                        if not selected_code and utils:
                            selected_code = utils[0].get("Code")

                        if selected_code:
                            async with session.post(
                                MYUSAGE_LOGIN_URL,
                                data={"uc": selected_code},
                                headers=login_headers,
                                timeout=20,
                            ) as util_resp:
                                util_json = await util_resp.json(content_type=None)
                                if util_json.get("redirect_url"):
                                    self._data_url = urljoin(MYUSAGE_BASE_URL, util_json["redirect_url"])
                                    self._logged_in = True
                                    _LOGGER.info("Authenticated multi-utility session; data URL: %s", self._data_url)
                                    return True

                    redirect_url = res_json.get("redirect_url")
                    if redirect_url:
                        self._data_url = urljoin(MYUSAGE_BASE_URL, redirect_url)
                        self._logged_in = True
                        _LOGGER.info("Successfully authenticated with MyUsage. Target data URL: %s", self._data_url)
                        return True
                    else:
                        # Fallback data URL if redirect_url not returned in JSON
                        self._data_url = f"{MYUSAGE_BASE_URL}/data.cfm?appPage=Prepaid"
                        self._logged_in = True
                        _LOGGER.info("Authenticated without explicit redirect_url. Using default: %s", self._data_url)
                        return True

                elif response.status in (401, 403):
                    raise MyUtilitiesAuthError("Invalid username or password for MyUsage")
                else:
                    raise MyUtilitiesApiError(f"Unexpected HTTP {response.status} from MyUsage login")

        except MyUtilitiesAuthError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error connecting to MyUsage portal: %s", err)
            raise MyUtilitiesApiError(f"Cannot connect to MyUsage portal: {err}") from err

    async def async_validate_credentials(self) -> bool:
        """Validate credentials during Home Assistant config flow."""
        return await self.async_login()

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch latest utility usage and account data every 24 hours."""
        if not self._logged_in or not self._data_url:
            await self.async_login()

        session = await self._get_session()
        target_url = self._data_url or f"{MYUSAGE_BASE_URL}/data.cfm?appPage=Prepaid"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": MYUSAGE_ROOT_URL,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            _LOGGER.debug("Fetching utility data from: %s", target_url)
            async with session.get(target_url, headers=headers, timeout=25) as response:
                _LOGGER.debug("Data page response status: %s", response.status)

                if response.status == 200:
                    html_content = await response.text()
                    parsed_data = self._parse_myusage_html(html_content)
                    _LOGGER.info("Parsed MyUsage utility metrics: %s", parsed_data)
                    return parsed_data

                elif response.status in (401, 403):
                    _LOGGER.warning("Session expired, re-authenticating with MyUsage...")
                    self._logged_in = False
                    await self.async_login()
                    # Retry with newly established session
                    async with session.get(self._data_url or target_url, headers=headers, timeout=25) as retry_resp:
                        if retry_resp.status == 200:
                            retry_html = await retry_resp.text()
                            return self._parse_myusage_html(retry_html)

        except Exception as err:
            _LOGGER.error("Error fetching MyUsage utility data: %s", err)

        return self._get_default_metrics()

    def _parse_myusage_html(self, html: str) -> dict[str, Any]:
        """Extract usage, cost, balance, and meter values from portal HTML."""
        data = self._get_default_metrics()

        if not html:
            _LOGGER.warning("Received empty HTML content from MyUsage portal")
            return data

        _LOGGER.debug("MyUsage HTML snippet: %s", html[:400])

        # 1. Parse Account Balance ($)
        balance_match = (
            re.search(r"(?:balance|prepay|account balance)[^\$\d\-]*\$?\s*(-?[0-9,]+\.[0-9]{2})", html, re.IGNORECASE)
            or re.search(r"\$\s*(-?[0-9,]+\.[0-9]{2})", html)
        )
        if balance_match:
            try:
                data["account_balance"] = float(balance_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # 2. Parse Electric Usage (kWh)
        electric_match = (
            re.search(r"([0-9,]+\.?[0-9]*)\s*kwh", html, re.IGNORECASE)
            or re.search(r"electric[^\d]*([0-9,]+\.?[0-9]*)", html, re.IGNORECASE)
        )
        if electric_match:
            try:
                data["electric_usage"] = float(electric_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # 3. Parse Water Usage (Gallons / CCF)
        water_match = (
            re.search(r"([0-9,]+\.?[0-9]*)\s*(?:gal|gallons|ccf)", html, re.IGNORECASE)
            or re.search(r"water[^\d]*([0-9,]+\.?[0-9]*)", html, re.IGNORECASE)
        )
        if water_match:
            try:
                data["water_usage"] = float(water_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # 4. Parse Daily Cost ($)
        cost_match = re.search(r"(?:daily cost|today'?s? cost|cost|charge)[^\$\d]*\$?\s*([0-9,]+\.[0-9]{2})", html, re.IGNORECASE)
        if cost_match:
            try:
                data["daily_cost"] = float(cost_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # 5. Parse Last Meter Reading & Date
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
        """Return default metrics dictionary ensuring all keys exist."""
        return {
            "electric_usage": 0.0,
            "water_usage": 0.0,
            "daily_cost": 0.0,
            "account_balance": 0.0,
            "last_meter_reading": 0.0,
            "last_meter_date": "N/A",
        }



