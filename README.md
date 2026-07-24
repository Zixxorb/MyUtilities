# MyUtilities (Cleveland Utilities) Home Assistant Integration

Custom Home Assistant component that fetches daily utility usage data (electric, water, cost, account balance, and last meter reading) from Cleveland Utilities / MyUsage every 24 hours.

## Features

- **24-Hour Polling Cycle**: Configured using Home Assistant's `DataUpdateCoordinator` to update once every 24 hours (`86400` seconds).
- **Home Assistant Energy Dashboard Ready**: Includes `device_class` and `state_class` metadata compatible with Home Assistant's built-in Energy Dashboard.
- **Sensors Created**:
  - `sensor.myutilities_daily_electric_usage` (kWh)
  - `sensor.myutilities_daily_water_usage` (Gallons)
  - `sensor.myutilities_daily_usage_cost` ($)
  - `sensor.myutilities_account_balance` ($)
  - `sensor.myutilities_last_meter_reading` (Meter reading value with `last_meter_read_date` attribute)
- **UI Configuration Flow**: Setup via standard Home Assistant UI (`Settings` -> `Devices & Services`).

---

## Installation

### Manual Installation
1. Copy the `custom_components/myutilities` folder into your Home Assistant `/config/custom_components/` directory:
   ```text
   config/
   └── custom_components/
       └── myutilities/
           ├── __init__.py
           ├── api.py
           ├── config_flow.py
           ├── const.py
           ├── manifest.json
           └── sensor.py
   ```
2. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** -> **Devices & Services**.
2. Click **Add Integration** in the bottom right.
3. Search for **MyUtilities (Cleveland Utilities)**.
4. Enter your login credentials and optional account number.
5. Click **Submit**.

---

## Change Log

All modifications and updates to this integration are recorded in [CHANGELOG.md](file:///C:/Users/adabbs/Documents/antigravity/calm-lovelace/CHANGELOG.md).
