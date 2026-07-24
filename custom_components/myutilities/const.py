"""Constants for the MyUtilities (Cleveland Utilities) integration."""

DOMAIN = "myutilities"

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ACCOUNT_NUMBER = "account_number"

# Default configuration settings
DEFAULT_SCAN_INTERVAL = 86400  # 24 hours in seconds

# Sensor keys
SENSOR_ELECTRIC_USAGE = "electric_usage"
SENSOR_WATER_USAGE = "water_usage"
SENSOR_DAILY_COST = "daily_cost"
SENSOR_ACCOUNT_BALANCE = "account_balance"
SENSOR_LAST_METER_READING = "last_meter_reading"
SENSOR_LAST_METER_DATE = "last_meter_date"

# API Base URL
BASE_URL = "https://www.clevelandutilities.com/myusage-app"
API_ENDPOINT = "https://myusage.clevelandutilities.com/api"
