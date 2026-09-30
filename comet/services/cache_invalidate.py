import re
from dataclasses import dataclass

_MEDIA_ID = re.compile(r"^(tt\d{5,10})(?::(\d{1,4}):(\d{1,4}))?$")
_IMDB_ID = re.compile(r"^tt\d{5,10}$")
_SCOPES = frozenset({"movie", "series", "season", "episode"})


@dataclass(frozen=True, slots=True)
class CacheTarget:
    media_id: str
    season: int | None = None
    episode: int | None = None


@dataclass(frozen=True, slots=True)
class InvalidateSpec:
    scope: str
    media_id: str
    season: int | None = None
    episode: int | None = None


def parse_cache_target(value: object) -> CacheTarget | None:
    """Accept `tt0111161` or `tt0111161:1:5`. Anything else is refused."""
    if not isinstance(value, str):
        return None
    match = _MEDIA_ID.fullmatch(value.strip())
    if match is None:
        return None
    season = int(match.group(2)) if match.group(2) else None
    episode = int(match.group(3)) if match.group(3) else None
    return CacheTarget(match.group(1), season, episode)


def parse_invalidate_body(body: object) -> InvalidateSpec | None:
    """`scope` is movie, series, season or episode.

    Without `scope`, the old payload still works: `tt0111161` wipes that id,
    `tt0111161:1:5` wipes that episode.
    """
    if not isinstance(body, dict):
        return None
    raw_scope = body.get("scope")
    if raw_scope is None:
        target = parse_cache_target(body.get("mediaId"))
        if target is None:
            return None
        if target.season is None:
            return InvalidateSpec("legacy", target.media_id)
        return InvalidateSpec("episode", target.media_id, target.season, target.episode)

    if not isinstance(raw_scope, str) or raw_scope not in _SCOPES:
        return None
    media_id = body.get("mediaId")
    if not isinstance(media_id, str) or _IMDB_ID.fullmatch(media_id.strip()) is None:
        return None
    media_id = media_id.strip()
    season = _optional_int(body.get("season"))
    episode = _optional_int(body.get("episode"))
    if raw_scope == "movie":
        return InvalidateSpec("movie", media_id)
    if raw_scope == "series":
        return InvalidateSpec("series", media_id)
    if season is None:
        return None
    if raw_scope == "season":
        return InvalidateSpec("season", media_id, season)
    if episode is None:
        return None
    return InvalidateSpec("episode", media_id, season, episode)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        return None
    if number < 0 or number > 9999:
        return None
    return number


async def invalidate_media_cache(target: CacheTarget) -> tuple[int, int]:
    spec = (
        InvalidateSpec("legacy", target.media_id)
        if target.season is None
        else InvalidateSpec("episode", target.media_id, target.season, target.episode)
    )
    deleted = await invalidate_for_scope(spec)
    return deleted["torrents"], deleted["demand"]


async def invalidate_for_scope(spec: InvalidateSpec) -> dict:
    """Drop stored torrents and scrape markers for one movie, series, season or episode.

    Series and season deletes use the rows already stored. They do not walk
    episode numbers, so a gap does not leave later chapters in cache.
    """
    from comet.core.database import database

    if spec.scope in ("legacy", "series"):
        torrent_rows = await database.fetch_all(
            """
            DELETE FROM torrents
            WHERE media_id = :media_id
            RETURNING season, episode
            """,
            {"media_id": spec.media_id},
        )
        demand_rows = await database.fetch_all(
            """
            DELETE FROM media_demand
            WHERE media_id = :media_id OR media_id LIKE :prefix
            RETURNING media_id
            """,
            {"media_id": spec.media_id, "prefix": f"{spec.media_id}:%"},
        )
    elif spec.scope == "movie":
        torrent_rows = await database.fetch_all(
            """
            DELETE FROM torrents
            WHERE media_id = :media_id
              AND season IS NULL
            RETURNING season, episode
            """,
            {"media_id": spec.media_id},
        )
        demand_rows = await database.fetch_all(
            """
            DELETE FROM media_demand
            WHERE media_id = :media_id
            RETURNING media_id
            """,
            {"media_id": spec.media_id},
        )
    elif spec.scope == "season":
        torrent_rows = await database.fetch_all(
            """
            DELETE FROM torrents
            WHERE media_id = :media_id
              AND season = :season
            RETURNING season, episode
            """,
            {"media_id": spec.media_id, "season": spec.season},
        )
        demand_rows = await database.fetch_all(
            """
            DELETE FROM media_demand
            WHERE media_id = :season_id
               OR media_id LIKE :episode_prefix
            RETURNING media_id
            """,
            {
                "season_id": f"{spec.media_id}:{spec.season}",
                "episode_prefix": f"{spec.media_id}:{spec.season}:%",
            },
        )
    else:
        torrent_rows = await database.fetch_all(
            """
            DELETE FROM torrents
            WHERE media_id = :media_id
              AND season = :season
              AND (episode = :episode OR episode IS NULL)
            RETURNING season, episode
            """,
            {
                "media_id": spec.media_id,
                "season": spec.season,
                "episode": spec.episode,
            },
        )
        demand_rows = await database.fetch_all(
            """
            DELETE FROM media_demand
            WHERE media_id = :demand_id
            RETURNING media_id
            """,
            {"demand_id": f"{spec.media_id}:{spec.season}:{spec.episode}"},
        )

    seasons = sorted({row["season"] for row in torrent_rows if row["season"] is not None})
    episodes = sorted(
        {
            row["episode"]
            for row in torrent_rows
            if row["episode"] is not None and (spec.season is None or row["season"] == spec.season)
        }
    )
    return {
        "scope": spec.scope,
        "mediaId": spec.media_id,
        "season": spec.season,
        "episode": spec.episode,
        "torrents": len(torrent_rows),
        "demand": len(demand_rows),
        "seasons": seasons,
        "episodes": episodes,
    }
