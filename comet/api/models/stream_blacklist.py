"""Pydantic models for admin stream blacklist API."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from comet.utils.formatting import normalize_info_hash

_IMDB_ID = re.compile(r"^tt\d{5,10}$")
_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_MAGNET_HASH_PATTERN = re.compile(
    r"btih:([0-9a-fA-F]{40}|[a-zA-Z0-9]{32})", re.IGNORECASE
)
_MEDIA_TYPES = ("movie", "series")
_KINDS = ("infohash", "magnet")
_MAX_VALUES = 500


def _parse_infohash_line(kind: str, line: str) -> str:
    stripped = line.strip()
    if not stripped:
        raise ValueError("empty line")
    if kind == "magnet":
        match = _MAGNET_HASH_PATTERN.search(stripped)
        if match is None:
            raise ValueError(f"no infohash in magnet: {stripped[:80]!r}")
        raw = match.group(1)
    else:
        raw = stripped
    normalized = normalize_info_hash(raw)
    if not _HASH_PATTERN.match(normalized):
        raise ValueError(f"invalid infohash: {stripped[:80]!r}")
    return normalized.lower()


class StreamBlacklistAdd(BaseModel):
    mediaType: Literal["movie", "series"]
    mediaId: str = Field(..., min_length=1)
    kind: Literal["infohash", "magnet"]
    values: Annotated[list[str], Field(min_length=1, max_length=_MAX_VALUES)]
    season: int | None = Field(default=None, ge=0)
    episode: int | None = Field(default=None, ge=0)

    @field_validator("mediaId")
    @classmethod
    def _strip_media_id(cls, value: str) -> str:
        cleaned = value.strip()
        if _IMDB_ID.fullmatch(cleaned) is None:
            raise ValueError("mediaId must be a valid IMDB id (tt…)")
        return cleaned

    @model_validator(mode="after")
    def _validate_scope(self) -> StreamBlacklistAdd:
        if self.mediaType == "movie":
            if self.season is not None or self.episode is not None:
                raise ValueError("season/episode must be omitted for movie")
        else:
            if self.season is None or self.episode is None:
                raise ValueError("season and episode are required for series")
        return self

    def resolved_hashes(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for line in self.values:
            if not line.strip():
                continue
            digest = _parse_infohash_line(self.kind, line)
            if digest not in seen:
                seen.add(digest)
                ordered.append(digest)
        if not ordered:
            raise ValueError("values must contain at least one non-empty entry")
        if len(ordered) > _MAX_VALUES:
            raise ValueError(f"at most {_MAX_VALUES} unique hashes per request")
        return ordered


class StreamBlacklistEntryRef(BaseModel):
    infoHash: str = Field(..., min_length=40, max_length=64)
    season: int | None = Field(default=None, ge=0)
    episode: int | None = Field(default=None, ge=0)

    @field_validator("infoHash")
    @classmethod
    def _normalize_hash(cls, value: str) -> str:
        normalized = normalize_info_hash(value.strip())
        if not _HASH_PATTERN.match(normalized):
            raise ValueError("infoHash must be a 40-char hex string")
        return normalized.lower()


class StreamBlacklistRemove(BaseModel):
    mediaId: str = Field(..., min_length=1)
    entries: list[StreamBlacklistEntryRef] | None = None

    @field_validator("mediaId")
    @classmethod
    def _strip_media_id(cls, value: str) -> str:
        cleaned = value.strip()
        if _IMDB_ID.fullmatch(cleaned) is None:
            raise ValueError("mediaId must be a valid IMDB id (tt…)")
        return cleaned
