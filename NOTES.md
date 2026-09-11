# MyUtilities — what's broken and what I changed

## The two problems

**1. The sensor platform crashes on import, so you get zero entities.**

`sensor.py` subclasses `SensorEntityDescription` with a bare `@dataclass`.
Since Home Assistant 2024.1, `EntityDescription` is declared
`@dataclass(frozen=True, kw_only=True)`, and Python refuses to inherit a
non-frozen dataclass from a frozen one:

```
TypeError: cannot inherit non-frozen dataclass from a frozen one
```

That fires at import time, so the whole sensor platform fails to set up. The
config entry appears in Settings → Devices & Services with no entities under
it. If that matches what you see, this is your immediate cause.

**2. Even once it loads, the scraper was written without ever seeing the site.**

The changelog history tells the story: `/index.cfm` → 404 → switch to
`/login` → broaden the regexes. Each round was a guess. The current patterns
are so loose they'd match almost anything:

```python
re.search(r"\$\s*(-?[0-9,]+\.[0-9]{2})", html)          # first dollar figure anywhere
re.search(r"(?:meter|reading)[^\d]*([0-9,]+\.?[0-9]*)", html)   # any number after "meter"
```

And three things conspired to hide the failure:

- `async_login()` returned `True` when the response had no `redirect_url`,
  so a wrong password was accepted and the config flow never showed
  "invalid auth".
- `async_get_data()` wrapped everything in `except Exception` and returned
  `_get_default_metrics()` — all `0.0`. So the coordinator always succeeded.
- The sensors defaulted to `0.0` rather than `None`, so entities looked
  populated. Those zeros also get written into long-term statistics, which
  is a pain to clean up.

Net effect: something that looks like it's working but reports zeros forever.
I could not find any prior art for the MyUsage/Exceleron portal — no public
library, no existing HA integration, just a 2021 feature request. So the
endpoints have to be discovered.

## Also fixed

| Issue | Fix |
|---|---|
| `MONETARY` device class with `"$"` as the unit | ISO 4217 `"USD"` — HA won't record statistics for `$` |
| Daily-resetting totals marked `TOTAL_INCREASING` | `TOTAL` + `last_reset`; with one poll per day, `TOTAL_INCREASING` reads each daily drop as a meter reset and inflates the sums |
| Account balance marked `TOTAL_INCREASING` | no state class — a balance moves both ways, and top-ups would register as consumption |
| `aiohttp.ClientSession` created by the client, never closed | `async_create_clientsession(hass, cookie_jar=...)`, so HA closes it on unload; private cookie jar so the portal session isn't mixed into HA's shared one |
| `timeout=15` as a bare int | `aiohttp.ClientTimeout(total=15)` (bare numbers are deprecated) |
| `"requirements": ["aiohttp>=3.8.0"]` | removed — aiohttp ships with HA, and pinning it invites pip conflicts |
| `DataUpdateCoordinator` without `config_entry` | passed explicitly (required in recent HA) |
| `from homeassistant.helpers.entity import DeviceInfo` | `homeassistant.helpers.device_registry` (the old path is deprecated) |
| No `strings.json` | added, so `invalid_auth` / `cannot_connect` render as real text |
| No reauth flow | `async_step_reauth`; auth errors now raise `ConfigEntryAuthFailed` |
| Fixed 24h interval | options flow, 1–24 hours — you don't want to wait a day per test |
| `last_meter_reading` given no device class | left that way deliberately, until we know what the number is |

`README.md` also links `CHANGELOG.md` as
`file:///C:/Users/adabbs/Documents/...`, which only works on your machine.
Should be a relative `CHANGELOG.md`.

## What to do next

### 1. Drop in the patched component

Copy `custom_components/myutilities/` over your existing folder and restart.
Then add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.myutilities: debug
```

It will now fail *loudly*. Expect one of:

- `Config entry not ready` with a real reason — good, that's the truth
- `MyUsage login failed: <portal's own message>` — credentials or field names
- `MyUsage login returned no redirect_url` — the login shape changed
- `Reached the portal but extracted no values at all` — auth works, parsing doesn't

### 2. Capture what the portal actually returns

`probe_myusage.py` runs on your PC, not in HA — much faster to iterate than
edit-restart-wait.

```bash
pip install requests
python probe_myusage.py --email you@example.com --password 'yourpass'
```

It writes numbered dumps to `./myusage_dump/`: the landing page, any hidden
CSRF tokens (the integration currently sends none, a common silent-failure
cause), the raw `/login` reply, the authenticated page, every number visible
on it, and any AJAX endpoints the page references — it fetches the promising
ones too. Since `/login` already speaks JSON, there's a good chance the usage
figures come from a JSON endpoint as well, which would let us delete the
regex parser entirely.

Secrets, emails and long digit runs are scrubbed by default. Skim the files
before sharing anyway.

### 3. Send me the dumps

With `02_login_response.txt` and `03_data_page.html` I can write a parser that
targets real elements instead of guessing, and tell you whether there's a
clean JSON endpoint to use instead.

## One caveat on the data itself

Polling once a day gives one data point per day, so the Energy Dashboard will
only ever show daily bars. If the portal exposes hourly or 15-minute interval
data — prepay portals usually do, to draw their charts — the better design is
to import that history via `async_add_external_statistics` rather than expose
a live sensor. Worth checking for in the probe output before we settle the
sensor design.
