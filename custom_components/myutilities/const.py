"""Constants for the MyUtilities (MyUsage prepaid) integration."""

from __future__ import annotations

DOMAIN = "myutilities"

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
# Only needed for logins that cover more than one utility, where the portal
# answers the login with result="multi_util" and asks us to choose. A normal
# single-utility account should leave this blank.
CONF_UTILITY_CODE = "utility_code"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

# The portal recalculates once a day, in the morning. Polling more often than
# every few hours just adds load for no new data.
DEFAULT_SCAN_INTERVAL_HOURS = 6
MIN_SCAN_INTERVAL_HOURS = 1
MAX_SCAN_INTERVAL_HOURS = 24

# ISO 4217 code. Home Assistant's monetary device class needs a currency code
# here, not a "$" symbol, or no long-term statistics get recorded.
CURRENCY_USD = "USD"

# Portal endpoints, confirmed from a captured browser session.
#   GET  https://www.myusage.com/          -> sets session cookies
#   POST https://www.myusage.com/login     -> JSON with a one-time redirect_url
#   GET  <redirect_url>                    -> 302 chain ending at the data page
MYUSAGE_BASE_URL = "https://www.myusage.com"
MYUSAGE_ROOT_URL = f"{MYUSAGE_BASE_URL}/"
MYUSAGE_LOGIN_URL = f"{MYUSAGE_BASE_URL}/login"

# Statistic ids for the imported thirty-day history.
STAT_DAILY_CHARGE = f"{DOMAIN}:daily_energy_charge"
