# Changelog

All notable changes to the **MyUtilities Home Assistant integration**
(Exceleron MyUsage prepaid) are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); this
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-09-11

Rewritten against a captured browser session instead of guessed endpoints.
Entity ids and the set of sensors both change, hence the major bump.

### Fixed
- Sensor platform crashed on import. `SensorEntityDescription` has been a
  frozen, keyword-only dataclass since Home Assistant 2024.1, so subclassing
  it with a plain `@dataclass` raised `TypeError: cannot inherit non-frozen
  dataclass from a frozen one` and took the whole platform down. No entities
  were ever created on any HA from 2024.1 onward.
- `async_login()` returned `True` whenever the response lacked a
  `redirect_url`, so wrong passwords were accepted and the coordinator then
  served zeros indefinitely.
- `async_get_data()` caught bare `Exception` and returned all-zero defaults,
  so the coordinator always reported success and nothing ever surfaced in the
  log or the UI.
- Login posted a utility code as a third `uc` form field. The portal answers
  `{"error_str": "Invalid Session.", "result": "error"}` to that. The browser
  sends exactly two fields, `email` and `password`; `uc` belongs only to the
  follow-up step after a `multi_util` response.
- Session started from `myusagepayments.com/utility/<CODE>`, which is the
  payments site and 302s to the myusage.com root. The login session is now
  primed from `https://www.myusage.com/` directly.
- Monetary sensors used `"$"` as the unit. Home Assistant's monetary device
  class needs an ISO 4217 code, so no long-term statistics were recorded.
- Daily totals were marked `TOTAL_INCREASING`. Polled once a day, every
  daily reset read as a meter rollover and inflated the sums. They are now
  `TOTAL` with an explicit `last_reset`.
- Account balance was marked `TOTAL_INCREASING`, so each prepay top-up
  registered as consumption. It now carries no state class.
- The API client created its own `aiohttp.ClientSession` and never closed it,
  leaking a connector on every reload.
- `"requirements": ["aiohttp>=3.8.0"]` removed from the manifest; aiohttp
  ships with Home Assistant and pinning it invites resolution conflicts.

### Added
- Real parser for the Prepaid summary page, keyed off each panel's own label
  rather than positional regex, covering balance, estimated days left,
  average daily charge, average daily utility charge, last daily energy
  usage, energy rate, last daily charge, last payment, unpaid balance, meter
  status and meter reading date.
- Import of the thirty-day daily charge history embedded in the page's chart
  data, pushed to long-term statistics as `myutilities:daily_energy_charge`,
  so the Energy dashboard shows a month of cost history immediately.
- Outdoor high and low temperature for the reading day, which the portal
  supplies alongside the charge chart. Disabled by default.
- Diagnostics platform, so a user whose utility parses incorrectly can send a
  redacted report from the UI instead of running a script.
- Reauth flow: authentication failures raise `ConfigEntryAuthFailed` and
  prompt for a new password.
- Options flow for the polling interval.
- Test suite running against a captured page, so a portal redesign fails CI
  rather than silently blanking sensors.
- CI: hassfest, HACS validation, ruff and pytest, with a weekly schedule to
  catch Home Assistant's monthly releases.

### Changed
- Entities are only created for figures the account actually publishes, so a
  postpay or electric-only utility does not get permanently unknown sensors.
- Migrated from `hass.data[DOMAIN]` to `entry.runtime_data`.
- Utility code is now optional and used only for multi-utility logins. It is
  not an account number and not a tenant selector for myusage.com.
- Default polling interval is 6 hours, configurable from 1 to 24.

### Removed
- Water usage sensor. The Cleveland Utilities prepay portal publishes no
  water data; the page is electric only. If a tenant does expose water, it
  should be added from a captured page rather than guessed at.
