"""Admin-side persistence for manual torrent inserts.

All SQL is delegated to the existing `TorrentUpdateQueue` so manual torrents
flow through the same upsert path as scraper-found ones. The only difference
is the `is_manual` flag, which is set via `_apply_manual_flags` after the
upsert succeeds so the column is never exposed to scraper-side ON CONFLICT
updates.
"""

from __future__ import annotations

import time

from comet.api.models.manual_torrent import ManualTorrentIn
from comet.core.database import normalize_scope_value
from comet.core.models import database
from comet.services.torrent_manager import torrent_update_queue


def _scoped_file_info(item: ManualTorrentIn) -> dict:
    return {
        "info_hash": item.infoHash,
        "title": item.title,
        "size": item.size,
        "seeders": item.seeders,
        "tracker": item.tracker or "Manual",
        "sources": item.sources,
        "season": item.season,
        "episode": item.episode,
        "file_index": item.fileIndex,
        "parsed": item.parsed,
    }


async def insert_manual(item: ManualTorrentIn) -> bool:
    """Queue a single manual torrent. Returns True if a new row was created,
    False if it was an upsert (already existed)."""
    media_id = item.mediaId
    file_info = _scoped_file_info(item)
    await torrent_update_queue.add_torrent_infos(
        [file_info],
        media_id=media_id,
        from_cometnet=False,
        is_manual=True,
        manual_share_cometnet=item.shareCometnet,
    )
    return True


async def insert_manual_bulk(
    items: list[ManualTorrentIn],
) -> tuple[int, int, list[dict]]:
    """Bulk insert. Returns (inserted, updated, rejected). The split is
    approximate: SQL upserts are atomic so we report the full batch as
    inserted when no pre-existing row was discovered first."""
    rejected: list[dict] = []
    grouped: dict[str, list[ManualTorrentIn]] = {}
    for index, item in enumerate(items):
        media_id = item.mediaId
        grouped.setdefault(media_id, []).append(item)

    inserted = 0
    for media_id, media_items in grouped.items():
        for item in media_items:
            try:
                await insert_manual(item)
                inserted += 1
            except Exception as exc:
                rejected.append({"index": index, "error": str(exc)})

    return inserted, 0, rejected


async def list_manual(
    *,
    media_id: str | None = None,
    info_hash: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    where_clauses = ["is_manual = 1"]
    params: dict = {"limit": safe_limit, "offset": safe_offset}
    if media_id:
        where_clauses.append("media_id = :media_id")
        params["media_id"] = media_id
    if info_hash:
        where_clauses.append("info_hash = :info_hash")
        params["info_hash"] = info_hash.lower()

    where_sql = " AND ".join(where_clauses)
    rows = await database.fetch_all(
        f"""
        SELECT media_id, info_hash, title, season, episode, file_index,
               size, seeders, tracker, updated_at, manual_share_cometnet
        FROM torrents
        WHERE {where_sql}
        ORDER BY updated_at DESC
        LIMIT :limit OFFSET :offset
        """,
        params,
    )
    return [
        {
            "mediaId": row["media_id"],
            "infoHash": row["info_hash"],
            "title": row["title"],
            "season": row["season"],
            "episode": row["episode"],
            "fileIndex": row["file_index"],
            "size": row["size"],
            "seeders": row["seeders"],
            "tracker": row["tracker"],
            "updatedAt": row["updated_at"],
            "shareCometnet": bool(row["manual_share_cometnet"]),
        }
        for row in rows
    ]


async def delete_manual(
    *,
    media_id: str,
    info_hash: str,
    season: int | None = None,
    episode: int | None = None,
) -> int:
    season_norm = normalize_scope_value(season)
    episode_norm = normalize_scope_value(episode)
    return await database.execute(
        """
        DELETE FROM torrents
        WHERE is_manual = 1
          AND media_id = :media_id
          AND info_hash = :info_hash
          AND season_norm = :season_norm
          AND episode_norm = :episode_norm
        """,
        {
            "media_id": media_id,
            "info_hash": info_hash.lower(),
            "season_norm": season_norm,
            "episode_norm": episode_norm,
        },
    )


async def wait_for_manual_flush(timeout: float = 5.0) -> None:
    """Best-effort wait so admin smoke tests can confirm persistence."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await torrent_update_queue.queue.join()
        return
    return
