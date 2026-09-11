# Shipping this on HACS

## Short answer

No. Nobody but you runs `probe_myusage.py`. It's a one-time authoring tool —
you use it to learn what the portal returns, you bake that knowledge into
`api.py`, and your users just enter their email and password. They never see
a script.

Think of it the way any reverse-engineered integration gets built: someone
watches the traffic once, writes the client, and ships it.

## The thing that actually complicates this

`myusage.com` is not Cleveland Utilities' website. It's Exceleron's MyUsage
platform, sold to a lot of small utilities as a white-label prepay portal —
which is why `/login` answers with `multi_util` when an account spans more
than one. Your login shows you *Cleveland Utilities' tenant*, with Cleveland
Utilities' enabled modules.

So a user in another town installs your integration and:

- they may have electric only, no water meter
- their utility may be postpay, so there's no prepay balance at all
- their tenant may have a different page layout or different modules enabled

An HTML-scraping parser tuned to one tenant's markup will not survive contact
with the others. Two consequences for the design:

**1. Prefer JSON endpoints over HTML.** `/login` already speaks JSON, so the
usage figures very likely come from an AJAX endpoint too. Field names in a
JSON API are far more stable across tenants than markup is — the tenants share
a backend even when they don't share a skin. `probe_myusage.py` step 5 and 6
hunt for exactly these. If one turns up, build on it and delete the regexes.

**2. Missing data must be normal, not an error.** This is why the patched
`api.py` returns `None` per field instead of `0.0`, and why it only raises
when *nothing at all* parsed. A water-less utility should get four working
sensors and one `unknown`, not a broken integration. Worth going further
later: skip creating an entity entirely when the portal never reports that
field.

## How your users report problems (not by scraping)

I added `diagnostics.py`. When someone's utility isn't parsed right, they go
to Settings → Devices & Services → MyUtilities → ⋮ → **Download diagnostics**
and attach the JSON to a GitHub issue. It contains which fields parsed, which
didn't, the login result shape, the data URL path, and the portal's markup
with emails, long digit strings, phone numbers and street addresses stripped.

That gives you what the probe script gives you, from a user who only had to
click a button. Mention it in your issue template.

## Packaging gaps in the current repo

| Item | Status |
|---|---|
| `custom_components/myutilities/` layout | already correct |
| `hacs.json` `filename` key | removed — that key is for plugins and templates, ignored for integrations |
| `hacs.json` `homeassistant` key | added, `2026.9.0`. Set this to the oldest version you actually test, since the frozen-dataclass requirement means this cannot run on pre-2024.1 anyway |
| `manifest.json` `codeowners: ["@user"]` | placeholder — HACS validation wants your real GitHub handle |
| `documentation` / `issue_tracker` → clevelandutilities.com | changed to your repo. `issue_tracker` pointing at the utility's contact page would send your bug reports to their front desk |
| `requirements: ["aiohttp>=3.8.0"]` | emptied — aiohttp ships with HA, and pinning it invites pip resolution conflicts |
| `loggers` key | added, so the log-level UI knows about you |
| Brand icon | needed. `brands/icon.png` for HACS; a separate PR to `home-assistant/brands` for the icon to appear inside HA |
| GitHub release | HACS uses your default branch without one. Tag and publish a real release, not just a tag |
| CI | added `.github/workflows/validate.yml` — hassfest, HACS action, ruff, plus a weekly cron so HA's monthly releases don't break you silently |
| Repo description + topics | GitHub repo needs both to pass HACS default-repo review |

`README.md` also links `CHANGELOG.md` as
`file:///C:/Users/adabbs/Documents/antigravity/calm-lovelace/CHANGELOG.md`.
Make that a relative `CHANGELOG.md` before anyone else reads it.

## Two things to be upfront about

**Credentials.** Users are handing your integration their utility account
password, stored in `.storage/core.config_entries` in plaintext. That's normal
for HA and unavoidable here, but say so in the README — people should know
before they type it.

**Terms of service.** Worth reading Exceleron's before publishing. Automated
access to a portal is a different proposition when it's you against your own
account versus a public integration pointing many users at their servers. A
polite once-a-day poll is about as defensible as this gets — resist the urge
to shorten the default interval for everyone.

## Order I'd do this in

1. Drop in the patched component, restart, read the error you now get.
2. Run the probe on your own account. Find out whether there's a JSON endpoint.
3. Send me the dumps; I'll write the real parser.
4. Then packaging: real codeowner, icon, CI green, first release.

Step 3 is the one that decides whether this is a clean API client or a
scraper you'll be repairing every few months.
