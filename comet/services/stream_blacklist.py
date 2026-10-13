"""Per-title stream blacklist: block infohashes from cache for one movie or episode."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from comet.api.models.stream_blacklist import StreamBlacklistAdd, StreamBlacklistRemove
from comet.core.database import (
    build_scope_lookup_params,
    build_scope_params,
    normalize_scope_value,
)
from comet.core.models import database

RowKey = tuple[str, str, int, int]


@dataclass(frozen=True, slots=True)
class BlacklistScope:
    media_id: str
    season: int | None
    episode: int | None
    season_norm: int
    episode_norm: int


def scope_from_add(payload: StreamBlacklistAdd) -> BlacklistScope:
    if payload.mediaType == "movie":
        return BlacklistScope(
            media_id=payload.mediaId,
            season=None,
            episode=None,
            season_norm=normalize_scope_value(None),
            episode_norm=normalize_scope_value(None),
        )
    return BlacklistScope(
        media_id=payload.mediaId,
        season=payload.season,
        episode=payload.episode,
        season_norm=normalize_scope_value(payload.season),
        episode_norm=normalize_scope_value(payload.episode),
    )


def _row_key(
    media_id: str, info_hash: str, season_norm: int, episode_norm: int
) -> RowKey:
    return (media_id, info_hash.lower(), season_norm, episode_norm)


def _demand_id_for_scope(scope: BlacklistScope) -> str:
    if scope.season is None:
        return scope.media_id
    return f"{scope.media_id}:{scope.season}:{scope.episode}"


async def _delete_torrent_rows_for_keys(keys: list[RowKey]) -> int:
    if not keys:
        return 0
    deleted = 0
    for media_id, info_hash, season_norm, episode_norm in keys:
        rows = await database.fetch_all(
            """
            DELETE FROM torrents
            WHERE media_id = :media_id
              AND info_hash = :info_hash
              AND season_norm = :season_norm
              AND episode_norm = :episode_norm
            RETURNING info_hash
            """,
            {
                "media_id": media_id,
                "info_hash": info_hash,
                "season_norm": season_norm,
                "episode_norm": episode_norm,
            },
        )
        deleted += len(rows)
    return deleted


async def _clear_demand_scraped_at(demand_ids: set[str]) -> int:
    if not demand_ids:
        return 0
    cleared = 0
    for demand_id in demand_ids:
        result = await database.execute(
            """
            UPDATE media_demand
            SET last_scraped_at = NULL
            WHERE media_id = :media_id AND last_scraped_at IS NOT NULL
            """,
            {"media_id": demand_id},
        )
        if result:
            cleared += int(result)
    return cleared


async def add_stream_blacklist(payload: StreamBlacklistAdd) -> dict[str, Any]:
    scope = scope_from_add(payload)
    hashes = payload.resolved_hashes()
    now = time.time()
    added: list[str] = []
    already: list[str] = []

    async with database.transaction():
        for info_hash in hashes:
            inserted = await database.fetch_one(
                """
                INSERT INTO stream_blacklist (
                    media_id, info_hash, season, episode,
                    season_norm, episode_norm, created_at
                ) VALUES (
                    :media_id, :info_hash, :season, :episode,
                    :season_norm, :episode_norm, :created_at
                )
                ON CONFLICT (media_id, info_hash, season_norm, episode_norm)
                DO NOTHING
                RETURNING info_hash
                """,
                {
                    "media_id": scope.media_id,
                    "info_hash": info_hash,
                    "season": scope.season,
                    "episode": scope.episode,
                    "season_norm": scope.season_norm,
                    "episode_norm": scope.episode_norm,
                    "created_at": now,
                },
            )
            if inserted:
                added.append(info_hash)
            else:
                already.append(info_hash)

        purge_keys = [
            _row_key(scope.media_id, h, scope.season_norm, scope.episode_norm)
            for h in set(hashes)
        ]
        torrents_deleted = await _delete_torrent_rows_for_keys(purge_keys)

    return {
        "mediaId": scope.media_id,
        "season": scope.season,
        "episode": scope.episode,
        "added": added,
        "alreadyBlacklisted": already,
        "torrentsDeleted": torrents_deleted,
    }


async def list_stream_blacklist() -> dict[str, Any]:
    rows = await database.fetch_all(
        """
        SELECT
            b.media_id,
            b.info_hash,
            b.season,
            b.episode,
            b.created_at,
            m.title
        FROM stream_blacklist b
        LEFT JOIN media_metadata_cache m ON m.media_id = b.media_id
        ORDER BY b.media_id, b.season_norm, b.episode_norm, b.created_at DESC
        """
    )
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        media_id = row["media_id"]
        group = groups.get(media_id)
        if group is None:
            group = {
                "mediaId": media_id,
                "title": row["title"],
                "entries": [],
            }
            groups[media_id] = group
        group["entries"].append(
            {
                "infoHash": row["info_hash"],
                "season": row["season"],
                "episode": row["episode"],
                "createdAt": row["created_at"],
            }
        )
    return {"groups": list(groups.values())}


def _scope_from_entry(media_id: str, season: int | None, episode: int | None) -> BlacklistScope:
    return BlacklistScope(
        media_id=media_id,
        season=season,
        episode=episode,
        season_norm=normalize_scope_value(season),
        episode_norm=normalize_scope_value(episode),
    )


async def remove_stream_blacklist(payload: StreamBlacklistRemove) -> dict[str, Any]:
    media_id = payload.mediaId
    demand_ids: set[str] = set()
    removed = 0

    async with database.transaction():
        if not payload.entries:
            rows = await database.fetch_all(
                """
                DELETE FROM stream_blacklist
                WHERE media_id = :media_id
                RETURNING season, episode
                """,
                {"media_id": media_id},
            )
            removed = len(rows)
            for row in rows:
                scope = _scope_from_entry(media_id, row["season"], row["episode"])
                demand_ids.add(_demand_id_for_scope(scope))
        else:
            for entry in payload.entries:
                scope_params = build_scope_params(entry.season, entry.episode)
                result = await database.fetch_all(
                    """
                    DELETE FROM stream_blacklist
                    WHERE media_id = :media_id
                      AND info_hash = :info_hash
                      AND season_norm = :season_norm
                      AND episode_norm = :episode_norm
                    RETURNING season, episode
                    """,
                    {
                        "media_id": media_id,
                        "info_hash": entry.infoHash,
                        **scope_params,
                    },
                )
                if result:
                    removed += len(result)
                    for row in result:
                        scope = _scope_from_entry(
                            media_id, row["season"], row["episode"]
                        )
                        demand_ids.add(_demand_id_for_scope(scope))

        demand_cleared = await _clear_demand_scraped_at(demand_ids)

    return {
        "mediaId": media_id,
        "removed": removed,
        "demandScopesCleared": sorted(demand_ids),
        "demandRowsUpdated": demand_cleared,
    }


async def fetch_blacklisted_info_hashes(
    media_ids: list[str],
    season: int | None,
    episode: int | None,
) -> set[str]:
    """Infohashes banned for this request scope across the given media ids."""
    ids = list(dict.fromkeys(media_id for media_id in media_ids if media_id))
    if not ids:
        return set()

    params: dict[str, object] = dict(build_scope_lookup_params(season, episode))
    placeholders = []
    for index, media_id in enumerate(ids):
        key = f"media_id_{index}"
        placeholders.append(f":{key}")
        params[key] = media_id

    rows = await database.fetch_all(
        f"""
        SELECT info_hash
        FROM stream_blacklist
        WHERE media_id IN ({", ".join(placeholders)})
          AND season_norm = :season_norm
          AND episode_norm = :episode_norm
        """,
        params,
    )
    return {row["info_hash"].lower() for row in rows}


async def fetch_blacklisted_row_keys(
    row_keys: list[RowKey],
) -> set[RowKey]:
    """Return subset of row_keys that exist in stream_blacklist."""
    if not row_keys:
        return set()
    by_media: dict[str, list[RowKey]] = {}
    for key in row_keys:
        by_media.setdefault(key[0], []).append(key)

    blacklisted: set[RowKey] = set()
    for media_id, keys in by_media.items():
        rows = await database.fetch_all(
            """
            SELECT info_hash, season_norm, episode_norm
            FROM stream_blacklist
            WHERE media_id = :media_id
            """,
            {"media_id": media_id},
        )
        banned_set = {
            (media_id, r["info_hash"].lower(), r["season_norm"], r["episode_norm"])
            for r in rows
        }
        for key in keys:
            if key in banned_set:
                blacklisted.add(key)
    return blacklisted


def parse_infohash_from_kind(kind: str, value: str) -> str | None:
    """Helper for tests: resolve one line."""
    from comet.api.models.stream_blacklist import _parse_infohash_line

    try:
        return _parse_infohash_line(kind, value)
    except ValueError:
        return None
