"""Pydantic models for the admin manual-torrent API.

Validation is the only behaviour here. The actual persistence is delegated to
`comet.services.admin_manual_torrents` which routes through the existing
`TorrentUpdateQueue`.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator
from RTN import parse as rtn_parse

from comet.utils.formatting import normalize_info_hash

_MEDIA_TYPES = ("movie", "series")
_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_MAGNET_HASH_PATTERN = re.compile(
    r"btih:([0-9a-fA-F]{40}|[a-zA-Z0-9]{32})", re.IGNORECASE
)
_MAGNET_DN_PATTERN = re.compile(r"dn=([^&]+)")
_MAGNET_TR_PATTERN = re.compile(r"tr=([^&]+)")
_VALID_SOURCES = re.compile(r"^[a-zA-Z0-9_\-\.:&/?=]+$")
_KNOWN_RESOLUTIONS = frozenset(
    {
        "2160p",
        "1440p",
        "1080p",
        "720p",
        "576p",
        "480p",
        "360p",
        "240p",
        "SD",
    }
)


def _synthetic_parsed_payload(
    title: str, season: int | None, episode: int | None
) -> dict:
    """Minimal ParsedData dump when RTN cannot extract a title or resolution."""
    return {
        "raw_title": title,
        "parsed_title": title,
        "year": None,
        "resolution": "SD",
        "quality": None,
        "rip": "UNKNOWN",
        "codec": None,
        "audio": None,
        "channels": None,
        "hdr": None,
        "languages": [],
        "extras": [],
        "adult": False,
        "trash": False,
        "seasons": [season] if season is not None else [],
        "episodes": [episode] if episode is not None else [],
        "dubbed": False,
        "edition": None,
        "network": None,
        "group": None,
        "container": None,
        "bitrate": None,
        "site": None,
        "proper": False,
        "repack": False,
        "upscaled": False,
        "remux": False,
        "documentary": False,
        "three_d": False,
        "converted": False,
        "raw": None,
        "title": title,
        "complete": False,
    }


def _dump_parsed(parsed) -> dict:
    if hasattr(parsed, "model_dump"):
        payload = parsed.model_dump()
        return payload if isinstance(payload, dict) else {}
    data = getattr(parsed, "__dict__", None)
    return dict(data) if isinstance(data, dict) else {}


def _parsed_has_known_resolution(payload: dict) -> bool:
    resolution = payload.get("resolution")
    if not isinstance(resolution, str) or not resolution.strip():
        return False
    return resolution.strip() in _KNOWN_RESOLUTIONS


def _overlay_explicit_scope(
    payload: dict, season: int | None, episode: int | None
) -> dict:
    if season is not None:
        payload["seasons"] = [season]
    if episode is not None:
        payload["episodes"] = [episode]
    return payload


class ManualTorrentIn(BaseModel):
    """Schema for a single manual torrent entry."""

    mediaId: str = Field(..., min_length=1, max_length=128)
    mediaType: str = Field(..., min_length=1)
    infoHash: str | None = Field(default=None, min_length=40, max_length=64)
    title: str | None = Field(default=None, max_length=512)
    size: int = Field(default=0, ge=0)
    seeders: int = Field(default=0, ge=0)
    tracker: str | None = Field(default="Manual", max_length=64)
    sources: list[str] = Field(default_factory=list)
    season: int | None = Field(default=None, ge=0)
    episode: int | None = Field(default=None, ge=0)
    fileIndex: int | None = Field(default=None, ge=0)
    magnet: str | None = Field(default=None, max_length=2048)
    parsed: dict | None = Field(default=None)
    shareCometnet: bool = False

    @field_validator("mediaType")
    @classmethod
    def _validate_media_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _MEDIA_TYPES:
            raise ValueError("mediaType must be 'movie' or 'series'")
        return normalized

    @field_validator("mediaId")
    @classmethod
    def _validate_media_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("mediaId is required")
        return stripped

    @field_validator("sources")
    @classmethod
    def _validate_sources(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for source in value:
            if not isinstance(source, str):
                continue
            candidate = source.strip()
            if not candidate:
                continue
            if not _VALID_SOURCES.match(candidate):
                raise ValueError(f"Invalid source: {candidate!r}")
            cleaned.append(candidate)
        return cleaned

    @model_validator(mode="after")
    def _validate(self) -> ManualTorrentIn:
        if self.mediaType == "series":
            if self.season is not None and self.season < 0:
                raise ValueError("season must be >= 0")
            if self.episode is not None and self.episode < 0:
                raise ValueError("episode must be >= 0")
        elif self.mediaType == "movie":
            if self.season is not None or self.episode is not None:
                raise ValueError("season/episode must be null for movie")
        return self

    def resolve(self) -> ManualTorrentIn:
        """Apply magnet extraction and optional RTN parsing.

        Hash and title are still required. RTN is best-effort: if it cannot
        extract a parsed title and a known resolution, a synthetic payload
        with resolution ``SD`` is used instead of raising.
        """
        magnet = self.magnet
        info_hash = self.infoHash
        title = self.title
        sources = list(self.sources)
        tracker = self.tracker or "Manual"

        if magnet:
            hash_match = _MAGNET_HASH_PATTERN.search(magnet)
            if hash_match:
                info_hash = hash_match.group(1).lower()
            if not title:
                dn_match = _MAGNET_DN_PATTERN.search(magnet)
                if dn_match:
                    from urllib.parse import unquote

                    title = unquote(dn_match.group(1)).strip() or None
            if not sources:
                for tr_match in _MAGNET_TR_PATTERN.finditer(magnet):
                    from urllib.parse import unquote

                    tr = unquote(tr_match.group(1)).strip()
                    if tr:
                        sources.append(tr)

        if not info_hash or not _HASH_PATTERN.match(info_hash):
            raise ValueError("infoHash is required and must be a 40-char hex string")
        info_hash = normalize_info_hash(info_hash)
        if not title:
            raise ValueError("title is required (or magnet must include dn=)")
        if not isinstance(title, str):
            raise ValueError("title must be a string")

        parsed_payload: dict | None = None
        try:
            parsed = rtn_parse(title)
        except Exception:
            parsed = None
        if parsed is not None:
            dumped = _dump_parsed(parsed)
            if dumped.get("parsed_title") and _parsed_has_known_resolution(dumped):
                parsed_payload = dumped
        if parsed_payload is None:
            parsed_payload = _synthetic_parsed_payload(title, self.season, self.episode)
        else:
            parsed_payload = _overlay_explicit_scope(
                parsed_payload, self.season, self.episode
            )

        if not sources:
            sources = ["manual"]

        return self.model_copy(
            update={
                "infoHash": info_hash,
                "title": title,
                "sources": sources,
                "tracker": tracker,
                "parsed": parsed_payload,
            }
        )


class ManualTorrentBulkIn(BaseModel):
    torrents: Annotated[list[ManualTorrentIn], Field(min_length=1, max_length=500)]


class ManualTorrentDelete(BaseModel):
    mediaId: str = Field(..., min_length=1)
    infoHash: str = Field(..., min_length=40, max_length=64)
    season: int | None = Field(default=None, ge=0)
    episode: int | None = Field(default=None, ge=0)


class ManualTorrentOut(BaseModel):
    mediaId: str
    infoHash: str
    title: str
    season: int | None
    episode: int | None
    fileIndex: int | None
    size: int
    seeders: int
    tracker: str | None
    updatedAt: float
    shareCometnet: bool
