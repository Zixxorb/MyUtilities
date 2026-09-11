# Capturing the portal traffic with DevTools

Use this if `probe_myusage.py` can't get in. It always works, because it
records what your real browser actually did — no guessing about endpoints,
field names, or JavaScript.

Takes about three minutes.

## Steps

1. Open a **new** browser tab and press `F12` (or Ctrl+Shift+I) to open
   DevTools. Click the **Network** tab.
2. Tick **Preserve log**. Without it, the log clears on every page navigation
   and you'll lose the login request — which is the one that matters most.
3. Leave the filter set to **All**, or click **Fetch/XHR** to cut the noise
   down to just the data calls.
4. Now paste `https://myusagepayments.com/utility/TNCLE` into the address bar
   and log in as normal.
5. Once you're looking at your usage page, click around: the balance, the
   usage chart, whatever shows daily figures. Every click that loads data
   adds a request to the log. Those are what we want.
6. Right-click anywhere in the request list → **Save all as HAR with content**.
   Save it as `myusage.har`.

## Before you send it

A HAR file is a complete recording. It contains your password in the login
request body and your session cookies. Do not skip this step — a 4 MB JSON
file is not something you can eyeball.

Run the scrubber:

```bash
python scrub_har.py myusage.har --also "Your Name"
```

It writes `myusage.scrubbed.har` alongside the original, leaves the original
untouched, and prints a tally of what it removed. It strips password and token
fields, Cookie and Authorization headers, emails, phone numbers,
card-shaped numbers, street addresses, and account numbers including
hyphenated ones like `012345-067890`.

Names cannot be detected by pattern, which is what `--also` is for. Pass it
once per literal you want gone.

Send the `.scrubbed.har`, and skim it first regardless. It is your account.

If you would rather not think about any of this: change your portal password,
capture, send, then change it back. The captured credentials are dead on
arrival.

## What I need from it

If the HAR feels like too much, just these four things get us most of the way:

1. The **request URL** of the POST that happens when you click Sign In
2. Its **form data** — the field names, not the values
3. Its **response** — is it JSON? what does the JSON look like?
4. The URLs of any **Fetch/XHR** requests that fire while the usage page or
   chart loads, plus one of their responses

You can read all of that off the Network tab by clicking a request and
looking at the Headers / Payload / Response panes. Screenshots are fine.

## Why this is the one that matters

If the usage figures come from a JSON endpoint, this capture will show it,
and the integration becomes a small clean API client instead of a regex
scraper. That's the difference between something that keeps working and
something you patch every time the portal gets restyled.
