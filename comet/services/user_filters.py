"""User-controlled filters applied before RTN ranking.

These run after `filter_worker` (title/year/adult) and before `rank_worker`
(max-size and RTN rank). The per-type max size replaces the legacy global
`maxSize` for the relevant media type.

All filters are constructed once per request and reused per torrent; no
per-torrent regex compilation, no DB queries.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from RTN import ParsedData

_MAX_BYTES = 0
_GB = 1024**3


def compute_effective_max_size(config: Mapping[str, Any], media_type: str) -> int:
    """Resolve the per-type max size override, falling back to the legacy
    global `maxSize`. 0 means no cap (the ranking worker treats 0 as
    disabled)."""
    key = "maxSizeMovie" if media_type == "movie" else "maxSizeSeries"
    override = config.get(key) or 0
    if override:
        try:
            return int(override)
        except (TypeError, ValueError):
            pass
    legacy = config.get("maxSize") or 0
    try:
        return int(legacy)
    except (TypeError, ValueError):
        return _MAX_BYTES


def _normalize_substrings(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if normalized:
            out.append(normalized)
    return out


class FilenameFilter:
    """Substring filename/release filter, case-insensitive. Exclude wins over
    include. Empty include = accept any filename. Empty exclude = no rejects
    from this filter."""

    __slots__ = ("exclude", "include")

    def __init__(self, include: Iterable[str] | None, exclude: Iterable[str] | None):
        self.include = _normalize_substrings(include)
        self.exclude = _normalize_substrings(exclude)

    @property
    def is_active(self) -> bool:
        return bool(self.include or self.exclude)

    def matches(self, torrent_title: str) -> bool:
        if not self.is_active:
            return True
        if not isinstance(torrent_title, str) or not torrent_title:
            return True
        title_lower = torrent_title.lower()
        for needle in self.exclude:
            if needle in title_lower:
                return False
        if self.include:
            return any(needle in title_lower for needle in self.include)
        return True


class ReleaseTypeFilter:
    """Allow/block based on the central release-type taxonomy."""

    __slots__ = ("_matches", "allow", "block")

    def __init__(self, allow: Iterable[str] | None, block: Iterable[str] | None):
        # Lazy import to keep the dependency local.
        from comet.utils.release_types import matches_release_filters

        self.allow = [
            entry.lower() for entry in (allow or []) if isinstance(entry, str)
        ]
        self.block = [
            entry.lower() for entry in (block or []) if isinstance(entry, str)
        ]
        self._matches = matches_release_filters

    @property
    def is_active(self) -> bool:
        return bool(self.allow or self.block)

    def matches(self, parsed: ParsedData | None) -> bool:
        return self._matches(parsed, self.allow, self.block)


class BitrateFilter:
    """Bitrate filter driven by request-supplied duration. 0 disables either
    bound. Missing/zero/negative duration or missing size transparently
    disables the filter for that candidate — the spec says we cannot
    confidently compute bitrate for season packs."""

    __slots__ = ("duration_minutes", "max_mbps", "min_mbps")

    def __init__(
        self,
        min_mbps: float | None,
        max_mbps: float | None,
        duration_minutes: float | None,
    ):
        try:
            self.min_mbps = float(min_mbps) if min_mbps else 0.0
        except (TypeError, ValueError):
            self.min_mbps = 0.0
        try:
            self.max_mbps = float(max_mbps) if max_mbps else 0.0
        except (TypeError, ValueError):
            self.max_mbps = 0.0
        try:
            self.duration_minutes = float(duration_minutes) if duration_minutes else 0.0
        except (TypeError, ValueError):
            self.duration_minutes = 0.0

    @property
    def is_active(self) -> bool:
        return (self.min_mbps > 0 or self.max_mbps > 0) and self.duration_minutes > 0

    def matches(
        self,
        size_bytes: int | None,
        *,
        scope_matches: bool,
    ) -> bool:
        """Return True if the candidate passes the bitrate gate.

        `scope_matches` should be False when the torrent does not represent
        the actual file matching the requested season/episode (e.g. a full
        season pack when the user asked for a single episode). In that case
        the bitrate filter is skipped for the candidate.
        """
        if not self.is_active or not scope_matches:
            return True
        if not isinstance(size_bytes, (int, float)) or size_bytes <= 0:
            return True
        # bitrate_mbps = (size_bytes * 8) / (duration_minutes * 60 * 1_000_000)
        duration_seconds = self.duration_minutes * 60.0
        bitrate = (float(size_bytes) * 8.0) / (duration_seconds * 1_000_000.0)
        return not (
            (self.min_mbps > 0 and bitrate < self.min_mbps)
            or (self.max_mbps > 0 and bitrate > self.max_mbps)
        )


class UserFilters:
    """Aggregate container. Each filter is independently optional."""

    def __init__(
        self,
        *,
        filename: FilenameFilter,
        release_type: ReleaseTypeFilter,
        bitrate: BitrateFilter,
    ):
        self.filename = filename
        self.release_type = release_type
        self.bitrate = bitrate

    def any_active(self) -> bool:
        return (
            self.filename.is_active
            or self.release_type.is_active
            or self.bitrate.is_active
        )

    def filter_torrent(
        self,
        torrent: dict,
        *,
        scope_matches: bool,
    ) -> bool:
        if not self.any_active():
            return True
        return (
            self.filename.matches(torrent.get("title", ""))
            and self.release_type.matches(torrent.get("parsed"))
            and self.bitrate.matches(
                torrent.get("size"),
                scope_matches=scope_matches,
            )
        )


def build_user_filters(
    config: Mapping[str, Any],
    *,
    duration_minutes: float | None = None,
) -> UserFilters:
    return UserFilters(
        filename=FilenameFilter(
            config.get("filenameInclude"),
            config.get("filenameExclude"),
        ),
        release_type=ReleaseTypeFilter(
            config.get("releaseTypesAllowlist"),
            config.get("releaseTypesBlocklist"),
        ),
        bitrate=BitrateFilter(
            config.get("minBitrateMbps"),
            config.get("maxBitrateMbps"),
            duration_minutes,
        ),
    )


def has_include_but_no_match(
    torrents: Iterable[dict], filename: FilenameFilter
) -> bool:
    """Return True when `filenameInclude` is set and no cached torrent matches
    it. Used to trigger a bounded live refresh."""
    if not filename.include:
        return False
    for torrent in torrents:
        title = torrent.get("title")
        if isinstance(title, str) and filename.matches(title):
            return False
    return True
