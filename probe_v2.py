#!/usr/bin/env python3
"""
probe_myusage.py (v2) - discovery tool for the MyUsage / Exceleron portal.

Safe to double-click on Windows: it prompts for what it needs and holds the
window open at the end, even if it crashes. Everything is also written to
myusage_dump/transcript.txt so you never lose the output.

    pip install requests
    python probe_myusage.py

Starts from the per-utility entry point (e.g. myusagepayments.com/utility/TNCLE)
and follows wherever that redirects, rather than assuming myusage.com/login.
"""

from __future__ import annotations

import getpass
import os
import re
import sys
import traceback
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    print("Missing dependency. Run:  pip install requests")
    input("\nPress Enter to close...")
    raise SystemExit(1)

PAYMENTS_BASE = "https://myusagepayments.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

OUT = "myusage_dump"
_step = 0
_secrets: list[str] = []
_transcript: list[str] = []


def say(line: str = "") -> None:
    """Print and remember, so the transcript survives the window closing."""
    print(line)
    _transcript.append(line)


def redact(text: str) -> str:
    """Strip credentials and obvious personal details from dumped text."""
    for secret in _secrets:
        if secret and len(secret) > 2:
            text = text.replace(secret, "***REDACTED***")
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "***EMAIL***", text)
    text = re.sub(r"\b\d{7,}\b", "***DIGITS***", text)
    return text


def save(name: str, content: str, *, do_redact: bool = True) -> None:
    """Write a dump file, numbered in the order it was captured."""
    global _step
    _step += 1
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{_step:02d}_{name}")
    with open(path, "w", encoding="utf-8", errors="replace") as fh:
        fh.write(redact(content) if do_redact else content)
    say(f"  saved -> {path}  ({len(content)} bytes)")


def dump(name: str, resp, do_redact: bool = True) -> None:
    """Save a response with its status line and headers."""
    head = [
        f"# {resp.request.method} {resp.url}",
        f"# HTTP {resp.status_code}",
        "",
        *(f"{k}: {v}" for k, v in resp.headers.items()),
        "",
        "-" * 60,
        "",
    ]
    save(name, "\n".join(head) + resp.text, do_redact=do_redact)


def show_redirects(resp) -> None:
    """The redirect chain is the single most useful thing here."""
    if resp.history:
        say("  redirect chain:")
        for hop in resp.history:
            say(f"    {hop.status_code} {hop.url}")
            location = hop.headers.get("Location")
            if location:
                say(f"        -> Location: {location}")
    say(f"  final url: {resp.url}")


def find_client_side_redirect(html: str) -> str | None:
    """The /utility/CODE page says 'Redirecting...' - find out where to."""
    patterns = (
        r"""<meta[^>]+http-equiv=["']refresh["'][^>]+content=["'][^"']*url=([^"']+)["']""",
        r"""window\.location(?:\.href|\.replace\()?\s*=?\s*['"]([^'"]+)['"]""",
        r"""location\.href\s*=\s*['"]([^'"]+)['"]""",
        r"""document\.location\s*=\s*['"]([^'"]+)['"]""",
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def find_forms(html: str) -> list[str]:
    """Return the raw form tags on a page."""
    return re.findall(r"<form\b[^>]*>", html, re.IGNORECASE)


def find_inputs(html: str) -> list[str]:
    """Return the raw input tags on a page."""
    return re.findall(r"<input\b[^>]*>", html, re.IGNORECASE)


def find_endpoints(html: str) -> list[str]:
    """Pull candidate AJAX and data endpoints out of markup and inline JS."""
    patterns = (
        r"""url\s*:\s*['"]([^'"]+)['"]""",
        r"""fetch\(\s*['"]([^'"]+)['"]""",
        r"""\.(?:get|post|ajax)\(\s*['"]([^'"]+)['"]""",
        r"""['"](/[^'"\s]*(?:usage|data|api|chart|json|graph|ajax|balance|meter|login|auth)[^'"\s]*)['"]""",
        r"""(?:action|href|src)\s*=\s*['"]([^'"]*(?:login|auth|data|usage|api)[^'"]*)['"]""",
    )
    found: list[str] = []
    for pattern in patterns:
        for hit in re.findall(pattern, html, re.IGNORECASE):
            candidate = hit.strip()
            if not candidate or candidate.startswith(
                ("#", "javascript:", "mailto:", "tel:", "data:")
            ):
                continue
            if candidate not in found:
                found.append(candidate)
    return found


def summarise_numbers(html: str) -> None:
    """Report what figures are actually present on the authenticated page."""
    say("\n[6] Numbers visible on the authenticated page")
    for label, pattern in (
        ("dollar amounts", r"\$\s*-?[0-9,]+\.[0-9]{2}"),
        ("kWh values", r"[0-9,]+\.?[0-9]*\s*kwh"),
        ("gallons/CCF", r"[0-9,]+\.?[0-9]*\s*(?:gal|gallons|ccf)"),
        ("dates", r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}"),
    ):
        hits = re.findall(pattern, html, re.IGNORECASE)
        say(f"  {label}: {len(hits)} -> {hits[:12]}")


def run() -> None:
    """Walk the portal and dump everything we learn."""
    say("MyUsage portal probe (v2)")
    say("=" * 60)

    code = (
        input("\nUtility code from your portal URL [TNCLE]: ").strip() or "TNCLE"
    ).upper()
    email = input("Portal email address: ").strip()
    password = getpass.getpass("Portal password (not echoed): ")
    account = input("Account number (optional, press Enter to skip): ").strip()

    if not email or not password:
        say("\nEmail and password are both required. Nothing to do.")
        return

    _secrets.extend([password, email, account])

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    entry = f"{PAYMENTS_BASE}/utility/{code}"
    say(f"\n[1] GET {entry}")
    landing = session.get(entry, timeout=25, allow_redirects=True)
    say(f"  HTTP {landing.status_code}, {len(landing.text)} bytes")
    show_redirects(landing)
    dump("utility_landing.html", landing)
    say(f"  cookies: {sorted(session.cookies.keys())}")

    app_origin = f"{urlparse(landing.url).scheme}://{urlparse(landing.url).netloc}"
    say(f"  app origin looks like: {app_origin}")

    # That page renders "Redirecting..." so the real destination may only
    # exist in a meta refresh or a line of JavaScript.
    hop = find_client_side_redirect(landing.text)
    current = landing
    if hop:
        target = urljoin(landing.url, hop)
        say(f"\n[1b] client-side redirect found -> {target}")
        current = session.get(target, timeout=25, allow_redirects=True)
        say(f"  HTTP {current.status_code}, {len(current.text)} bytes")
        show_redirects(current)
        dump("after_client_redirect.html", current)
        app_origin = f"{urlparse(current.url).scheme}://{urlparse(current.url).netloc}"
        say(f"  app origin now: {app_origin}")
    else:
        say("\n[1b] no meta-refresh or JS redirect found in the landing page")

    say("\n[2] Login form on the page we landed on")
    forms = find_forms(current.text)
    inputs = find_inputs(current.text)
    say(f"  {len(forms)} form tag(s), {len(inputs)} input tag(s)")
    for tag in forms[:6]:
        say(f"    {tag[:200]}")
    for tag in inputs[:25]:
        say(f"    {tag[:200]}")
    save("form_tags.txt", "\n".join(forms + inputs))

    names = re.findall(r"""name=["']([^"']+)["']""", "\n".join(inputs), re.IGNORECASE)
    say(f"  field names: {names}")
    if not names:
        say("  NOTE: no fields at all usually means the login UI is drawn by")
        say("        JavaScript. If so, the DevTools capture is the reliable")
        say("        route, not this script. See PACKAGING.md.")

    say("\n[3] Candidate endpoints referenced by the page")
    endpoints = find_endpoints(current.text)
    save("candidate_endpoints.txt", "\n".join(endpoints), do_redact=False)
    for endpoint in endpoints[:40]:
        say(f"    {endpoint}")

    form_action = None
    if forms:
        action = re.search(r"""action=["']([^"']*)["']""", forms[0], re.IGNORECASE)
        if action and action.group(1).strip():
            form_action = urljoin(current.url, action.group(1).strip())

    attempts: list[str] = []
    for candidate in (
        form_action,
        f"{app_origin}/login",
        "https://www.myusage.com/login",
    ):
        if candidate and candidate not in attempts:
            attempts.append(candidate)

    payload = {"email": email, "password": password, "uc": code}
    if account:
        payload["accountNumber"] = account

    say("\n[4] Attempting login")
    for index, url in enumerate(attempts, start=1):
        say(f"  [4.{index}] POST {url}")
        try:
            resp = session.post(
                url,
                data=payload,
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": current.url,
                    "Origin": app_origin,
                },
                timeout=30,
                allow_redirects=False,
            )
        except requests.RequestException as err:
            say(f"    FAILED: {err}")
            continue

        say(
            f"    HTTP {resp.status_code}, "
            f"content-type {resp.headers.get('content-type')}"
        )
        parsed = urlparse(url)
        safe = re.sub(r"[^A-Za-z0-9]", "_", parsed.netloc + parsed.path)[-50:]
        dump(f"login_{safe}.txt", resp)

        try:
            decoded = resp.json()
        except ValueError:
            snippet = redact(resp.text[:300]).replace("\n", " ")
            say(f"    not JSON. First 300 chars: {snippet}")
        else:
            say(f"    JSON keys: {sorted(decoded)}")
            say(f"    result: {decoded.get('result')!r}")
            if decoded.get("redirect_url"):
                say(f"    redirect_url: {decoded['redirect_url']}")
                follow = urljoin(url, decoded["redirect_url"])
                say(f"\n[5] GET authenticated page {follow}")
                page = session.get(follow, timeout=30)
                say(f"  HTTP {page.status_code}, {len(page.text)} bytes")
                dump("data_page.html", page)
                summarise_numbers(page.text)
                return

        if resp.status_code in (301, 302, 303, 307, 308):
            say(f"    Location: {resp.headers.get('Location')}")

    say("\n  None of the login attempts produced a usable session.")
    say("  Check the dumped login_*.txt files, then fall back to the DevTools")
    say("  capture - that always works, because it records a real browser.")


def main() -> int:
    """Run the probe, and keep the console open whatever happens."""
    exit_code = 0
    try:
        run()
    except KeyboardInterrupt:
        say("\nCancelled.")
        exit_code = 1
    except Exception:  # noqa: BLE001 - the whole point is to show the error
        say("\n" + "!" * 60)
        say("The probe crashed. Full traceback:")
        say(traceback.format_exc())
        exit_code = 1
    finally:
        try:
            os.makedirs(OUT, exist_ok=True)
            with open(
                os.path.join(OUT, "transcript.txt"), "w", encoding="utf-8"
            ) as fh:
                fh.write(redact("\n".join(_transcript)))
            print(f"\nTranscript written to {OUT}/transcript.txt")
        except OSError as err:
            print(f"Could not write transcript: {err}")

        # Keeps the console open when the script is double-clicked.
        if sys.stdin is not None and sys.stdin.isatty():
            input("\nPress Enter to close...")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
