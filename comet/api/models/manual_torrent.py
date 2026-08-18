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
_MAGNET_HASH_PATTERN = re.compile(r"btih:([0-9a-fA-F]{40}|[a-zA-Z0-9]{32})", re.IGNORECASE)
_MAGNET_DN_PATTERN = re.compile(r"dn=([^&]+)")
_MAGNET_TR_PATTERN = re.compile(r"tr=([^&]+)")
_VALID_SOURCES = re.compile(r"^[a-zA-Z0-9_\-\.:&/?=]+$")


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
    def _validate(self) -> "ManualTorrentIn":
        if self.mediaType == "series":
            if self.season is not None and self.season < 0:
                raise ValueError("season must be >= 0")
            if self.episode is not None and self.episode < 0:
                raise ValueError("episode must be >= 0")
        elif self.mediaType == "movie":
            if self.season is not None or self.episode is not None:
                raise ValueError("season/episode must be null for movie")
        return self

    def resolve(self) -> "ManualTorrentIn":
        """Apply magnet extraction and RTN parsing. Returns a new instance with
        normalized hashes/title/sources. Raises ValueError on invalid RTN."""
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
            raise ValueError(
                "infoHash is required and must be a 40-char hex string"
            )
        info_hash = normalize_info_hash(info_hash)
        if not title:
            raise ValueError("title is required (or magnet must include dn=)")
        if not isinstance(title, str):
            raise ValueError("title must be a string")

        try:
            parsed = rtn_parse(title)
        except Exception as exc:
            raise ValueError(f"RTN failed to parse title: {exc}") from exc
        if not parsed.parsed_title:
            raise ValueError(
                "RTN could not extract a parsed title; provide a fuller filename"
            )

        parsed_payload = parsed.model_dump() if hasattr(parsed, "model_dump") else {}

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
