"""Centralized release-type taxonomy shared by web UI, filters and admin UI.

A single source of truth for the categories exposed in `web_config.releaseTypes`
and consumed by `services.user_filters.ReleaseTypeFilter`. Classification comes
from RTN's parsed payload (`parsed.rip`); only the `"unknown"` bucket is added
for releases RTN cannot attribute.
"""

from __future__ import annotations

from collections.abc import Iterable

from RTN import ParsedData

RELEASE_TYPE_KEYS: tuple[str, ...] = (
    "remux",
    "bluray",
    "web",
    "webdl",
    "webmux",
    "hdtv",
    "dvd",
    "bdrip",
    "brrip",
    "dvdrip",
    "hdrip",
    "webrip",
    "webdlrip",
    "tvrip",
    "cam",
    "screener",
    "telecine",
    "telesync",
    "unknown",
)


RELEASE_TYPE_LABELS: dict[str, str] = {
    "remux": "REMUX",
    "bluray": "BluRay",
    "web": "WEB",
    "webdl": "WEB-DL",
    "webmux": "WEBMux",
    "hdtv": "HDTV",
    "dvd": "DVD",
    "bdrip": "BDRip",
    "brrip": "BRRip",
    "dvdrip": "DVDRip",
    "hdrip": "HDRip",
    "webrip": "WEBRip",
    "webdlrip": "WEB-DL Rip",
    "tvrip": "TVRip",
    "cam": "CAM",
    "screener": "Screener",
    "telecine": "Telecine",
    "telesync": "Telesync",
    "unknown": "Unknown",
}


_RIP_TO_TYPE: dict[str, str] = {
    "REMUX": "remux",
    "BLURAY": "bluray",
    "BLU-RAY": "bluray",
    "WEB": "web",
    "WEBDL": "webdl",
    "WEB-DL": "webdl",
    "WEBMUX": "webmux",
    "WEB-MUX": "webmux",
    "HDTV": "hdtv",
    "DVD": "dvd",
    "BDRIP": "bdrip",
    "BRRIP": "brrip",
    "DVDRIP": "dvdrip",
    "HDRIP": "hdrip",
    "WEBRIP": "webrip",
    "WEB-DLRIP": "webdlrip",
    "WEBDLRIP": "webdlrip",
    "TVRIP": "tvrip",
    "CAM": "cam",
    "SCREENER": "screener",
    "TELECINE": "telecine",
    "TELESYNC": "telesync",
}


def classify_release(parsed: ParsedData | None) -> str:
    """Return the release-type key for a parsed RTN payload, or `unknown`."""
    if parsed is None:
        return "unknown"
    rip = getattr(parsed, "rip", None)
    if isinstance(rip, str) and rip:
        key = _RIP_TO_TYPE.get(rip.strip().upper())
        if key:
            return key
    return "unknown"


def matches_release_filters(
    parsed: ParsedData | None,
    allow: Iterable[str] | None,
    block: Iterable[str] | None,
) -> bool:
    """Apply allow/block predicate with block winning over allow."""
    release_type = classify_release(parsed)
    block_set = {entry.lower() for entry in (block or []) if isinstance(entry, str)}
    if release_type in block_set:
        return False
    allow_values = [entry for entry in (allow or []) if isinstance(entry, str)]
    if not allow_values:
        return True
    allow_set = {entry.lower() for entry in allow_values}
    return release_type in allow_set


def release_type_choices() -> list[dict[str, str]]:
    """UI-ready list of available release types for the configure page."""
    return [
        {"key": key, "label": RELEASE_TYPE_LABELS[key]} for key in RELEASE_TYPE_KEYS
    ]
