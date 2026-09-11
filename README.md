# MyUtilities — Home Assistant integration for MyUsage prepaid

[![hacs][hacs-badge]][hacs-url]
[![Validate][validate-badge]][validate-url]

Brings your Exceleron **MyUsage** prepaid utility account into Home Assistant:
current balance, estimated days of service left, daily energy usage and
charge, and a month of daily cost history in the Energy dashboard.

Developed against Cleveland Utilities (utility code `TNCLE`). MyUsage is a
white-label platform used by a lot of small US utilities and co-ops, so it
should work for other MyUsage prepaid accounts — see
[Other utilities](#other-utilities) if yours reports something different.

---

## Sensors

| Entity | Unit | Notes |
|---|---|---|
| Account balance | USD | Your prepay balance. Attributes: date last updated, account number |
| Unpaid balance | USD | Only created if your account has one |
| Estimated days left | days | The portal's own estimate at current usage |
| Last daily energy usage | kWh | Most recent completed day |
| Energy rate | ¢/kWh | The rate your usage is billed at |
| Last daily charge | USD | Most recent completed day |
| Average daily charge | USD | Portal's rolling average |
| Average daily utility charge | USD | Excludes fees |
| Last payment | USD | Attribute: date posted |
| Meter status | — | e.g. `Active` |
| Last reading date | date | The day the figures above describe |
| Reading day high / low temperature | °F | Supplied with the charge chart. Disabled by default |

Entities are only created for figures your account actually publishes, so you
won't get a row of permanently unknown sensors for features your utility
doesn't offer.

### Energy dashboard

The summary page embeds the last thirty days of daily charge, which this
integration imports into long-term statistics as
`myutilities:daily_energy_charge`. So the Energy dashboard shows a month of
daily cost bars as soon as you finish setup, rather than starting from empty.

To use it: **Settings → Dashboards → Energy → Add consumption**, and pick the
MyUtilities daily energy charge statistic as a cost.

---

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/Zixxorb/MyUtilities`, category
   **Integration**
3. Search for **MyUtilities**, download, restart Home Assistant

### Manual

Copy `custom_components/myutilities/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

**Settings → Devices & Services → Add Integration → MyUtilities**

- **Email address** and **password** — the same ones you use at
  [myusage.com](https://www.myusage.com/)
- **Utility code** — leave blank. Only needed if one login covers several
  utilities, in which case the portal asks you to choose and this setting
  picks for you

Polling interval is configurable afterwards under **Configure** (1–24 hours).
The portal recalculates once a day in the morning, so the 6-hour default is
already more often than the data changes.

---

## Requirements

- Home Assistant 2026.9 or newer
- A MyUsage **prepaid** account with online access

---

## Before you install: your password

There is no API here. The integration signs in to the portal the same way a
browser does, which means Home Assistant stores your utility account password
in `.storage/core.config_entries` in plain text. That is how all
username/password integrations work, but it's worth knowing before you type it
in, particularly since this account can take payments.

If that bothers you, don't install this.

The integration also reads your account terms differently from a person
clicking around: it polls on a schedule. Exceleron's terms of service are
worth a look before you rely on it. The default interval is deliberately
gentle; please don't shorten it for a shared release.

---

## Other utilities

If the integration installs but some sensors don't appear, your utility's
portal probably lays out or labels those panels differently. You don't need to
capture anything by hand:

1. **Settings → Devices & Services → MyUtilities → ⋮ → Download diagnostics**
2. Open a [new issue][issues-url] and attach the JSON

The diagnostics report says which figures parsed, which didn't, and includes
the portal markup with emails, account numbers, phone numbers and street
addresses stripped. That's enough to add support for your utility. Skim it
before attaching, as always.

Known: the Cleveland Utilities portal publishes **no water data** — the
prepaid page is electric only — so there is no water sensor. If your utility
does expose water, a diagnostics report is all it takes to add it.

---

## Troubleshooting

Turn on debug logging first:

```yaml
logger:
  default: warning
  logs:
    custom_components.myutilities: debug
```

| Symptom | Likely cause |
|---|---|
| `Config entry not ready` | The log line beneath it says why. Usually a portal outage or a network problem |
| Re-authentication prompt | Password changed, or the portal invalidated the session. Enter the current password |
| `login failed: Invalid Email or Password` | Credentials are wrong. Confirm them by signing in at myusage.com |
| `returned no redirect_url` | The portal's login response changed shape. Please open an issue |
| `found neither a balance nor any chart history` | Login worked but the page layout doesn't match. Send diagnostics |

This integration has no control over the portal. If MyUsage is down or
redesigned, sensors go unavailable and the log says so — by design, rather
than reporting stale or zero values.

---

## Development

```bash
python -m pytest tests/ -v
```

The test suite runs the parser against a captured summary page with personal
details replaced. A portal redesign fails CI instead of quietly blanking
everyone's sensors. If you're adding support for another utility, add a
fixture from your own diagnostics report alongside it.

`scrub_har.py` strips credentials, cookies and personal data out of a HAR
capture, if you need to share raw traffic rather than a diagnostics report.

Changes are recorded in [CHANGELOG.md](CHANGELOG.md).

---

## Credits

Version 1.x was written with AI assistance from Gemini against guessed
endpoints and never worked. Version 2.0 was rewritten with Claude against a
captured browser session; the login flow and page structure documented in
`api.py` and `parser.py` came from real traffic.

Not affiliated with, endorsed by, or supported by Exceleron Software or
Cleveland Utilities.

## License

MIT — see [LICENSE](LICENSE).

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[validate-badge]: https://github.com/Zixxorb/MyUtilities/actions/workflows/validate.yml/badge.svg
[validate-url]: https://github.com/Zixxorb/MyUtilities/actions/workflows/validate.yml
[issues-url]: https://github.com/Zixxorb/MyUtilities/issues
