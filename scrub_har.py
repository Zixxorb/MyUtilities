#!/usr/bin/env python3
"""
scrub_har.py - strip secrets and personal data out of a HAR capture.

Browsers export HAR files with everything in them: passwords in POST bodies,
session cookies, auth headers, your name and address in response HTML. Doing
that by hand in a multi-megabyte file is how a password ends up in a chat log.

    python scrub_har.py myusage.har

Writes myusage.scrubbed.har next to the original and prints what it found.
The original is never modified.

Optional:
    --also "Jane Smith" --also "123 Main St"     # extra literals to remove
    --keep-cookie-names                          # keep names, drop values

Removes by default:
  - values of any POST field named like a credential (password, passwd, pin,
    token, secret, otp, ssn, card, cvv, account)
  - Cookie / Set-Cookie / Authorization / X-Auth-* header values
  - email addresses, digit runs of 7+, US phone numbers, card-shaped numbers
  - queryString and URL values for credential-ish parameter names
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_FIELD = re.compile(
    r"pass|pwd|pin\b|token|secret|otp|auth|session|sid\b|ssn"
    r"|card|cvv|cvc|account|routing",
    re.IGNORECASE,
)
SECRET_HEADER = re.compile(
    r"^(cookie|set-cookie|authorization|proxy-authorization"
    r"|x-auth.*|x-api-key|x-csrf.*|x-xsrf.*)$",
    re.IGNORECASE,
)

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"), "<email>"),
    (
        "card number",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        "<card>",
    ),
    (
        "phone",
        re.compile(r"\b(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"),
        "<phone>",
    ),
    (
        "hyphenated account no.",
        # Utility account numbers are often grouped, e.g. 012598-076202,
        # which a plain "7+ digits" rule misses because each half is shorter.
        re.compile(r"\b\d{4,}[- ]\d{4,}(?:[- ]\d{3,})?\b"),
        "<account>",
    ),
    ("long digits", re.compile(r"\b\d{7,}\b"), "<digits>"),
    (
        "street address",
        re.compile(
            r"\b\d{1,6}\s+[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)?\s+"
            r"(?:St|Street|Rd|Road|Ave|Avenue|Dr|Drive|Ln|Lane|Ct|Court"
            r"|Blvd|Boulevard|Way|Pl|Place|Ter|Terrace|Cir|Circle)\b\.?",
            re.IGNORECASE,
        ),
        "<address>",
    ),
]

counts: dict[str, int] = {}


def bump(label: str, n: int = 1) -> None:
    if n:
        counts[label] = counts.get(label, 0) + n


def scrub_text(text: str, literals: list[str]) -> str:
    """Apply literal removals then pattern removals to a string."""
    if not isinstance(text, str) or not text:
        return text

    for literal in literals:
        if literal and literal in text:
            bump(f"literal {literal[:12]!r}", text.count(literal))
            text = text.replace(literal, "<redacted>")

    for label, pattern, replacement in PATTERNS:
        text, n = pattern.subn(replacement, text)
        bump(label, n)

    return text


def scrub_url(url: str, literals: list[str]) -> str:
    """Blank credential-ish query parameters, then scrub what's left."""
    parts = urlsplit(url)
    if parts.query:
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        cleaned = []
        for key, value in pairs:
            if SECRET_FIELD.search(key):
                bump(f"query param {key}")
                cleaned.append((key, "<redacted>"))
            else:
                cleaned.append((key, value))
        parts = parts._replace(query=urlencode(cleaned))
    return scrub_text(urlunsplit(parts), literals)


def scrub_headers(headers: list[dict], keep_names: bool) -> list[dict]:
    out = []
    for header in headers:
        name = header.get("name", "")
        if SECRET_HEADER.match(name):
            bump(f"header {name}")
            if keep_names and name.lower() in ("cookie", "set-cookie"):
                names = [
                    piece.split("=")[0].strip()
                    for piece in header.get("value", "").split(";")
                ]
                header = {**header, "value": f"<names: {', '.join(names)}>"}
            else:
                header = {**header, "value": "<redacted>"}
        out.append(header)
    return out


def scrub_entry(entry: dict, literals: list[str], keep_names: bool) -> None:
    req = entry.get("request") or {}
    res = entry.get("response") or {}

    if req.get("url"):
        req["url"] = scrub_url(req["url"], literals)
    if res.get("redirectURL"):
        res["redirectURL"] = scrub_url(res["redirectURL"], literals)

    req["headers"] = scrub_headers(req.get("headers") or [], keep_names)
    res["headers"] = scrub_headers(res.get("headers") or [], keep_names)

    # Cookie arrays: keep names so the flow stays readable, drop values.
    for holder in (req, res):
        for cookie in holder.get("cookies") or []:
            if "value" in cookie:
                bump("cookie value")
                cookie["value"] = "<redacted>"

    for holder in (req, res):
        for param in holder.get("queryString") or []:
            if SECRET_FIELD.search(param.get("name", "")):
                bump(f"query param {param['name']}")
                param["value"] = "<redacted>"

    post = req.get("postData") or {}
    for param in post.get("params") or []:
        name = param.get("name", "")
        if SECRET_FIELD.search(name):
            bump(f"post field {name}")
            param["value"] = "<redacted>"
        elif "value" in param:
            param["value"] = scrub_text(param["value"], literals)

    if post.get("text"):
        text = post["text"]
        # Blank credential fields inside a raw urlencoded body too.
        def _blank(match: re.Match[str]) -> str:
            bump(f"post field {match.group(1)}")
            return f"{match.group(1)}=<redacted>"

        text = re.sub(r"([^=&]*(?:pass|token|pwd|otp|secret)[^=&]*)=[^&]*",
                      _blank, text, flags=re.IGNORECASE)
        post["text"] = scrub_text(text, literals)

    content = res.get("content") or {}
    if content.get("text"):
        content["text"] = scrub_text(content["text"], literals)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("har", help="path to the .har file")
    parser.add_argument(
        "--also",
        action="append",
        default=[],
        help="extra literal string to remove (repeatable)",
    )
    parser.add_argument(
        "--keep-cookie-names",
        action="store_true",
        help="keep cookie names in headers, drop only the values",
    )
    args = parser.parse_args()

    source = pathlib.Path(args.har)
    if not source.exists():
        print(f"No such file: {source}")
        return 1

    raw = source.read_text(encoding="utf-8", errors="replace")
    try:
        # strict=False tolerates the raw control characters browsers emit.
        data = json.loads(raw, strict=False)
    except ValueError as err:
        print(f"Could not parse {source} as JSON: {err}")
        return 1

    entries = (data.get("log") or {}).get("entries") or []
    print(f"{source.name}: {len(entries)} entries")

    for entry in entries:
        scrub_entry(entry, args.also, args.keep_cookie_names)

    target = source.with_suffix(".scrubbed.har")
    target.write_text(json.dumps(data, indent=1), encoding="utf-8")

    print("\nRemoved:")
    for label in sorted(counts):
        print(f"  {counts[label]:>6}  {label}")
    if not counts:
        print("  nothing matched - check the file is the one you meant")

    print(f"\nWrote {target}")
    print(
        "\nNote: personal NAMES cannot be detected by pattern. If the capture\n"
        "contains yours, rerun with e.g.  --also \"Jane Smith\"\n"
    )
    print("This is a best-effort scrub. Skim the output before sharing it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
