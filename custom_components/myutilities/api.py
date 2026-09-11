"""API client for the MyUsage prepaid portal.

The login sequence below mirrors a captured browser session exactly:

  1. GET  https://www.myusage.com/
         Establishes the session cookies (asid, sid, and ColdFusion's
         CFID/CFTOKEN once the .cfm side of the site is touched).

  2. POST https://www.myusage.com/login
         Body is exactly two fields: email and password. Nothing else.
         Headers include X-Requested-With: XMLHttpRequest, plus Origin and
         Referer pointing at the site root.

         Success looks like:
           {"data": {"login_redirect": 1, "show_redirect_animation": 1},
            "redirect_url": "https://www.myusage.com/default.cfm?
                             requestAction=Login&LoginEmail=WebSSOLogin&
                             LoginPassword=<32-digit one-time token>"}

         Bad credentials look like:
           {"error_str": "Invalid Email or Password", "result": "error"}

  3. GET  <redirect_url>, following redirects
         Hands the one-time token to the legacy ColdFusion app, which 302s
         via data.cfm?appPage=Account to the real summary page at
         data.cfm?appPage=Prepaid&...&appFlow=<per-session flow id>

The appFlow id is minted per login, so it can never be hardcoded. We let the
redirect chain carry us to it and remember where we landed.

Two mistakes worth not repeating, both confirmed from captures:
  - Sending a third form field (a utility code as "uc") on the initial login
    makes the portal answer "Invalid Session." The uc field belongs only to
    the follow-up step, after a result="multi_util" response.
  - The xsrf_token hidden input on the landing page belongs to the password
    reset and registration forms. The login POST does not carry it; session
    validation is done with cookies.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .const import MYUSAGE_BASE_URL, MYUSAGE_LOGIN_URL, MYUSAGE_ROOT_URL
from .parser import PrepaidSummary, parse_prepaid_summary

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) "
    "Gecko/20100101 Firefox/155.0"
)


class MyUtilitiesApiError(Exception):
    """General API or transport error."""


class MyUtilitiesAuthError(MyUtilitiesApiError):
    """The portal rejected our credentials."""


class MyUtilitiesParseError(MyUtilitiesApiError):
    """We reached the portal but could not understand the page."""


class MyUtilitiesApiClient:
    """Asynchronous client for the MyUsage prepaid portal."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        utility_code: str | None = None,
    ) -> None:
        """Initialize the client.

        The session belongs to Home Assistant (async_create_clientsession) so
        it is closed on unload, and carries its own cookie jar so the portal's
        session cookies are not mixed in with other integrations'.
        """
        self.username = username
        self.password = password
        self.utility_code = (utility_code or "").strip().upper() or None
        self._session = session

        self._logged_in = False
        self._data_url: str | None = None

        # Surfaced via the diagnostics platform.
        self.last_raw_page: str | None = None
        self.last_login_result: str | None = None
        self.last_login_keys: list[str] = []
        self.last_error: str | None = None

    @property
    def data_url(self) -> str | None:
        """The authenticated summary page we last landed on."""
        return self._data_url

    @staticmethod
    def _timeout(seconds: int) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=seconds)

    @property
    def _page_headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    @property
    def _ajax_headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": MYUSAGE_BASE_URL,
            "Referer": MYUSAGE_ROOT_URL,
        }

    async def async_login(self) -> None:
        """Authenticate. Raises on failure; never reports a false success."""
        try:
            await self._prime_session()

            # Exactly the two fields the browser sends. Adding more breaks it.
            payload = await self._post_login(
                {"email": self.username, "password": self.password}
            )

            if payload.get("result") == "error":
                message = (
                    payload.get("error_str")
                    or payload.get("error_msg")
                    or "credentials rejected"
                )
                raise MyUtilitiesAuthError(f"MyUsage login failed: {message}")

            if payload.get("result") == "multi_util":
                payload = await self._select_utility(payload)

            redirect = payload.get("redirect_url")
            if not redirect:
                raise MyUtilitiesAuthError(
                    "MyUsage login returned no redirect_url "
                    f"(result={payload.get('result')!r}, "
                    f"keys={sorted(payload)}). The login response shape has "
                    "probably changed."
                )

            await self._follow_sso_redirect(urljoin(MYUSAGE_BASE_URL, redirect))
            self._logged_in = True

        except MyUtilitiesApiError:
            raise
        except aiohttp.ClientError as err:
            raise MyUtilitiesApiError(f"Cannot reach MyUsage: {err}") from err
        except TimeoutError as err:
            raise MyUtilitiesApiError("Timed out talking to MyUsage") from err

    async def _prime_session(self) -> None:
        """Fetch the site root to pick up session cookies."""
        async with self._session.get(
            MYUSAGE_ROOT_URL,
            headers=self._page_headers,
            timeout=self._timeout(25),
            allow_redirects=True,
        ) as response:
            await response.read()
            _LOGGER.debug(
                "Root page HTTP %s, cookies now: %s",
                response.status,
                sorted({cookie.key for cookie in self._session.cookie_jar}),
            )

    async def _post_login(self, form: dict[str, str]) -> dict[str, Any]:
        """POST the login form and return the decoded JSON body."""
        async with self._session.post(
            MYUSAGE_LOGIN_URL,
            data=form,
            headers=self._ajax_headers,
            timeout=self._timeout(30),
            allow_redirects=False,
        ) as response:
            body = await response.text()

            if response.status in (401, 403):
                raise MyUtilitiesAuthError("MyUsage rejected the credentials")
            if response.status >= 400:
                raise MyUtilitiesApiError(
                    f"MyUsage login returned HTTP {response.status}"
                )

            try:
                decoded = await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError) as err:
                _LOGGER.debug("Non-JSON login body: %s", body[:400])
                raise MyUtilitiesApiError(
                    "MyUsage login did not return JSON"
                ) from err

            if not isinstance(decoded, dict):
                raise MyUtilitiesApiError(
                    f"Unexpected login payload: {type(decoded).__name__}"
                )

            self.last_login_result = str(decoded.get("result"))
            self.last_login_keys = sorted(decoded)
            _LOGGER.debug("Login payload keys: %s", self.last_login_keys)
            return decoded

    async def _select_utility(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Answer the portal's multi-utility picker.

        This is the only place the utility code is valid. It corresponds to
        the select_utility form on the landing page.
        """
        utilities = (payload.get("data") or {}).get("utilities") or []
        codes = [u.get("Code") for u in utilities]
        _LOGGER.debug("Portal offered utilities: %s", codes)

        code: Any = None
        if self.utility_code:
            for utility in utilities:
                if str(utility.get("Code")).upper() == self.utility_code:
                    code = utility.get("Code")
                    break
            if code is None:
                raise MyUtilitiesAuthError(
                    f"Utility code {self.utility_code} is not on this login. "
                    f"Available: {codes}"
                )
        elif len(utilities) == 1:
            code = utilities[0].get("Code")
        elif utilities:
            code = utilities[0].get("Code")
            _LOGGER.warning(
                "Login covers several utilities %s; defaulting to %s. Set the "
                "utility code during setup to choose a specific one.",
                codes,
                code,
            )

        if code is None:
            raise MyUtilitiesAuthError(
                "Portal asked us to choose a utility but listed none"
            )

        return await self._post_login({"uc": str(code)})

    async def _follow_sso_redirect(self, url: str) -> None:
        """Hand the one-time token to the ColdFusion app and note where we land.

        The 302 chain ends at the Prepaid summary page carrying this session's
        appFlow id, which is the URL we poll from then on.
        """
        async with self._session.get(
            url,
            headers=self._page_headers,
            timeout=self._timeout(30),
            allow_redirects=True,
        ) as response:
            body = await response.text()
            final = str(response.url)

            if response.status != 200:
                raise MyUtilitiesApiError(
                    f"SSO handoff returned HTTP {response.status}"
                )

            if "appFlow=" not in final and "data.cfm" not in final:
                raise MyUtilitiesAuthError(
                    f"SSO handoff did not reach the data app (landed on {final})"
                )

            self._data_url = final
            self.last_raw_page = body
            _LOGGER.debug("Authenticated. Summary page: %s", final)

    async def async_get_summary(self) -> PrepaidSummary:
        """Fetch and parse the prepaid account summary.

        Raises on failure rather than returning empty values, so Home
        Assistant can mark the entities unavailable and log the reason.
        """
        if not self._logged_in or not self._data_url:
            await self.async_login()

        page = await self._fetch_summary_page()
        self.last_raw_page = page

        summary = parse_prepaid_summary(page)

        if summary.account_balance is None and not summary.daily_charges:
            raise MyUtilitiesParseError(
                "Reached the summary page but found neither a balance nor any "
                "chart history. The page layout does not match the parser."
            )

        if summary.unmapped_labels:
            _LOGGER.debug(
                "Summary contained unrecognised panels: %s",
                summary.unmapped_labels,
            )

        return summary

    async def _fetch_summary_page(self) -> str:
        """GET the summary page, re-authenticating once if the session died."""
        for attempt in (1, 2):
            target = self._data_url
            if not target:
                await self.async_login()
                target = self._data_url
                if not target:
                    raise MyUtilitiesApiError("No summary URL after login")

            try:
                async with self._session.get(
                    target,
                    headers=self._page_headers,
                    timeout=self._timeout(30),
                    allow_redirects=True,
                ) as response:
                    body = await response.text()
                    status = response.status
            except aiohttp.ClientError as err:
                raise MyUtilitiesApiError(f"Network error: {err}") from err
            except TimeoutError as err:
                raise MyUtilitiesApiError("Timed out fetching summary") from err

            if status == 200 and not self._session_expired(body):
                return body

            if attempt == 1:
                # The appFlow id expires; a fresh login mints a new one.
                _LOGGER.debug("Session looks expired, re-authenticating")
                self._logged_in = False
                self._data_url = None
                continue

            if status != 200:
                raise MyUtilitiesApiError(
                    f"Summary page returned HTTP {status} after re-login"
                )
            raise MyUtilitiesAuthError(
                "Portal keeps bouncing us to the login page after a "
                "successful login response"
            )

        raise MyUtilitiesApiError("Could not fetch the summary page")

    @staticmethod
    def _session_expired(page: str) -> bool:
        """Detect being bounced back to the login screen."""
        if not page:
            return True
        lowered = page.lower()
        if 'type="password"' in lowered or "type='password'" in lowered:
            return True
        return "invalid session" in lowered
