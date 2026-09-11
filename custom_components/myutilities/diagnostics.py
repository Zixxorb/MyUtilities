"""Diagnostics for MyUtilities.

This is the piece that makes the integration supportable without asking
anyone to run a script. When a user's utility is not parsed correctly, they
hit Settings -> Devices & Services -> MyUtilities -> "Download diagnostics"
and send you the JSON. It contains the portal's own markup with credentials
and personal details stripped out.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from dataclasses import asdict, is_dataclass

from .const import CONF_PASSWORD, CONF_USERNAME
from .coordinator import MyUtilitiesConfigEntry

# The utility code is deliberately NOT redacted: it identifies which portal
# tenant the report came from, which is the first thing you need to know, and
# it is not personal information.
TO_REDACT = {CONF_USERNAME, CONF_PASSWORD}

# How much of the page to include. Enough to see the structure, small enough
# to paste into a GitHub issue.
MAX_PAGE_CHARS = 60_000


def _summary_dict(summary) -> dict[str, Any] | None:
    """Render the parsed summary, minus the account number."""
    if summary is None or not is_dataclass(summary):
        return None
    data = asdict(summary)
    data.pop("account_number", None)
    # Just the shape of the history, not a month of the user's usage.
    charges = data.pop("daily_charges", []) or []
    data["daily_charge_days"] = len(charges)
    data["daily_charge_first"] = str(charges[0]["day"]) if charges else None
    data["daily_charge_last"] = str(charges[-1]["day"]) if charges else None
    return {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in data.items()}


def _scrub(text: str) -> str:
    """Strip anything that identifies the account holder."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", text)
    text = re.sub(r"\b\d{7,}\b", "<digits>", text)
    text = re.sub(
        r"\b\d{3}[.\-\s]\d{3}[.\-\s]\d{4}\b", "<phone>", text
    )
    # Common street-address shapes
    text = re.sub(
        r"\b\d{1,6}\s+[A-Z][a-z]+\s+"
        r"(?:St|Street|Rd|Road|Ave|Avenue|Dr|Drive|Ln|Lane|Ct|Court|Blvd|Way|Pl|Place)\b\.?",
        "<address>",
        text,
    )
    return text


def _trim_markup(html: str) -> str:
    """Drop the noise that makes a page dump unreadable."""
    html = re.sub(
        r"<(script|style|svg)\b[^>]*>.*?</\1>", r"<\1 removed/>", html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"\n\s*\n+", "\n", html)
    return html


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MyUtilitiesConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    client = runtime.client
    coordinator = runtime.coordinator

    page = client.last_raw_page or ""
    if page:
        page = _scrub(_trim_markup(page))

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "version": entry.version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_hours": (
                coordinator.update_interval.total_seconds() / 3600
                if coordinator.update_interval
                else None
            ),
            "parsed_summary": _summary_dict(coordinator.data),
            "last_exception": str(coordinator.last_exception)
            if coordinator.last_exception
            else None,
        },
        "login": {
            "result": client.last_login_result,
            "payload_keys": client.last_login_keys,
            # The path tells us which portal variant this utility uses,
            # without leaking the session token in the query string.
            "data_url_path": (
                client.data_url.split("?")[0] if client.data_url else None
            ),
            "data_url_params": (
                sorted(
                    p.split("=")[0]
                    for p in client.data_url.split("?", 1)[1].split("&")
                )
                if client.data_url and "?" in client.data_url
                else []
            ),
        },
        "page": {
            "length": len(client.last_raw_page or ""),
            "truncated": len(page) > MAX_PAGE_CHARS,
            "markup": page[:MAX_PAGE_CHARS],
        },
    }
