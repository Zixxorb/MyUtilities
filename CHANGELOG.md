# Changelog

All notable changes to the **MyUtilities Home Assistant Integration** (Cleveland Utilities / MyUsage) will be documented in this file.

## [1.0.0] - 2026-07-24

### Added
- Created initial directory structure for Home Assistant custom component `custom_components/myutilities`.
- Added `manifest.json` defining domain, integration name, version, and dependencies.
- Added `const.py` with configuration constants, scan interval (24 hours / 86400 seconds), and sensor entity definitions.
- Added `api.py` with `MyUtilitiesApiClient` supporting asynchronous authentication and retrieval of:
  - Daily Electric Usage (kWh)
  - Daily Water Usage (Gallons / CCF)
  - Daily Usage Cost ($)
  - Current Account Balance ($)
  - Last Meter Reading timestamp and values
- Added `config_flow.py` for Home Assistant UI configuration flow with credential validation.
- Added `__init__.py` implementing `DataUpdateCoordinator` set to a 24-hour update interval (`update_interval=timedelta(hours=24)`).
## [1.0.1] - 2026-07-24

### Changed
- Updated `api.py` to support `myusage.com` ColdFusion (`.cfm`) session login flow via `index.cfm`.
- Added cookie session persistence (`aiohttp.CookieJar`) to maintain authenticated portal access across 24-hour update cycles.
- Added HTML text parser for `data.cfm?appPage=Prepaid` to extract account balance ($), daily electric usage (kWh), daily water usage (gal/CCF), daily usage cost ($), and last meter reading details.
- Added `hacs.json` for HACS (Home Assistant Community Store) custom repository support.
- Added AI development disclaimer to `README.md` acknowledging code development with Gemini.



