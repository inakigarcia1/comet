import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from databases import Database
from fastapi import HTTPException

from comet.api.models.stream_blacklist import StreamBlacklistAdd, StreamBlacklistRemove
from comet.core.database import NULL_SCOPE_SENTINEL
from comet.services import stream_blacklist as blacklist_service
from comet.services.orchestration import TorrentManager
from comet.services.torrent_manager import _construct_torrent_update, _execute_batched_upsert


class StreamBlacklistModelTests(unittest.TestCase):
    def test_series_requires_season_and_episode(self):
        with self.assertRaises(ValueError):
            StreamBlacklistAdd(
                mediaType="series",
                mediaId="tt1234567",
                kind="infohash",
                values=["0123456789abcdef0123456789abcdef01234567"],
            )

    def test_movie_rejects_season(self):
        with self.assertRaises(ValueError):
            StreamBlacklistAdd(
                mediaType="movie",
                mediaId="tt1234567",
                kind="infohash",
                values=["0123456789abcdef0123456789abcdef01234567"],
                season=1,
            )

    def test_magnet_resolves_to_infohash(self):
        payload = StreamBlacklistAdd(
            mediaType="movie",
            mediaId="tt1234567",
            kind="magnet",
            values=[
                "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=test"
            ],
        )
        self.assertEqual(
            payload.resolved_hashes(),
            ["0123456789abcdef0123456789abcdef01234567"],
        )

    def test_invalid_line_rejects_whole_batch(self):
        payload = StreamBlacklistAdd(
            mediaType="movie",
            mediaId="tt1234567",
            kind="infohash",
            values=[
                "0123456789abcdef0123456789abcdef01234567",
                "not-a-hash",
            ],
        )
        with self.assertRaises(ValueError):
            payload.resolved_hashes()


class StreamBlacklistPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "blacklist.db"
        self.database = Database(f"sqlite+aiosqlite:///{path}")
        await self.database.connect()
        await self.database.execute(
            """
            CREATE TABLE stream_blacklist (
                media_id TEXT NOT NULL,
                info_hash TEXT NOT NULL,
                season INTEGER,
                episode INTEGER,
                season_norm INTEGER NOT NULL DEFAULT -1,
                episode_norm INTEGER NOT NULL DEFAULT -1,
                created_at REAL NOT NULL,
                UNIQUE (media_id, info_hash, season_norm, episode_norm)
            )
            """
        )
        await self.database.execute(
            """
            CREATE TABLE torrents (
                media_id TEXT NOT NULL,
                info_hash TEXT NOT NULL,
                season INTEGER,
                episode INTEGER,
                season_norm INTEGER NOT NULL DEFAULT -1,
                episode_norm INTEGER NOT NULL DEFAULT -1,
                title TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL
            )
            """
        )
        await self.database.execute(
            """
            CREATE TABLE media_demand (
                media_id TEXT PRIMARY KEY,
                first_seen_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                last_scraped_at REAL
            )
            """
        )
        await self.database.execute(
            """
            CREATE TABLE media_metadata_cache (
                media_id TEXT PRIMARY KEY,
                title TEXT
            )
            """
        )
        self.patch_db = patch.object(blacklist_service, "database", self.database)
        self.patch_db.start()
        self.patch_tm = patch(
            "comet.services.torrent_manager.database", self.database
        )
        self.patch_tm.start()

    async def asyncTearDown(self):
        self.patch_tm.stop()
        self.patch_db.stop()
        await self.database.disconnect()
        self.tmp.cleanup()

    async def _insert_torrent(
        self,
        media_id: str,
        info_hash: str,
        season: int | None = None,
        episode: int | None = None,
    ):
        season_norm = NULL_SCOPE_SENTINEL if season is None else season
        episode_norm = NULL_SCOPE_SENTINEL if episode is None else episode
        await self.database.execute(
            """
            INSERT INTO torrents (
                media_id, info_hash, season, episode, season_norm, episode_norm,
                title, parsed_json, updated_at
            ) VALUES (
                :media_id, :info_hash, :season, :episode, :season_norm, :episode_norm,
                'title', '{}', :updated_at
            )
            """,
            {
                "media_id": media_id,
                "info_hash": info_hash,
                "season": season,
                "episode": episode,
                "season_norm": season_norm,
                "episode_norm": episode_norm,
                "updated_at": time.time(),
            },
        )

    async def test_ban_deletes_only_matching_scope(self):
        h1 = "a" * 40
        h2 = "b" * 40
        await self._insert_torrent("tt1111111", h1)
        await self._insert_torrent("tt2222222", h1)
        await self._insert_torrent("tt1111111", h2, season=1, episode=1)

        payload = StreamBlacklistAdd(
            mediaType="movie",
            mediaId="tt1111111",
            kind="infohash",
            values=[h1],
        )
        result = await blacklist_service.add_stream_blacklist(payload)
        self.assertEqual(result["torrentsDeleted"], 1)

        rows = await self.database.fetch_all("SELECT media_id, info_hash FROM torrents")
        remaining = {(r["media_id"], r["info_hash"]) for r in rows}
        self.assertEqual(remaining, {("tt2222222", h1), ("tt1111111", h2)})

    async def test_upsert_skips_blacklisted_row(self):
        info_hash = "c" * 40
        payload = StreamBlacklistAdd(
            mediaType="movie",
            mediaId="tt3333333",
            kind="infohash",
            values=[info_hash],
        )
        await blacklist_service.add_stream_blacklist(payload)

        row = _construct_torrent_update(
            media_id="tt3333333",
            info_hash=info_hash,
            season=None,
            episode=None,
            file_index=None,
            title="Banned.Title.2026",
            seeders=10,
            size=1000,
            tracker="test",
            sources=["test"],
            parsed={"parsed_title": "Banned"},
            from_cometnet=False,
        )
        await _execute_batched_upsert([row], updated_at=time.time())
        count = await self.database.fetch_val("SELECT COUNT(*) FROM torrents")
        self.assertEqual(count, 0)

    async def test_restore_clears_demand_for_scope_only(self):
        info_hash = "d" * 40
        now = time.time()
        await self.database.execute(
            """
            INSERT INTO media_demand (media_id, first_seen_at, last_seen_at, last_scraped_at)
            VALUES ('tt4444444', :t, :t, :t), ('tt5555555', :t, :t, :t)
            """,
            {"t": now},
        )
        await blacklist_service.add_stream_blacklist(
            StreamBlacklistAdd(
                mediaType="movie",
                mediaId="tt4444444",
                kind="infohash",
                values=[info_hash],
            )
        )
        await blacklist_service.remove_stream_blacklist(
            StreamBlacklistRemove(mediaId="tt4444444", entries=None)
        )
        scraped = await self.database.fetch_all(
            "SELECT media_id, last_scraped_at FROM media_demand ORDER BY media_id"
        )
        self.assertIsNone(scraped[0]["last_scraped_at"])
        self.assertIsNotNone(scraped[1]["last_scraped_at"])

    async def test_list_includes_title_when_cached(self):
        info_hash = "e" * 40
        await self.database.execute(
            "INSERT INTO media_metadata_cache (media_id, title) VALUES ('tt6666666', 'Animals')"
        )
        await blacklist_service.add_stream_blacklist(
            StreamBlacklistAdd(
                mediaType="movie",
                mediaId="tt6666666",
                kind="infohash",
                values=[info_hash],
            )
        )
        listed = await blacklist_service.list_stream_blacklist()
        self.assertEqual(listed["groups"][0]["title"], "Animals")

    async def test_fetch_blacklisted_hashes_follows_request_scope(self):
        movie_hash = "a" * 40
        episode_hash = "b" * 40
        await blacklist_service.add_stream_blacklist(
            StreamBlacklistAdd(
                mediaType="movie",
                mediaId="tt1111111",
                kind="infohash",
                values=[movie_hash],
            )
        )
        await blacklist_service.add_stream_blacklist(
            StreamBlacklistAdd(
                mediaType="series",
                mediaId="tt1111111",
                kind="infohash",
                season=1,
                episode=2,
                values=[episode_hash],
            )
        )

        movie_hashes = await blacklist_service.fetch_blacklisted_info_hashes(
            ["tt1111111"], None, None
        )
        episode_hashes = await blacklist_service.fetch_blacklisted_info_hashes(
            ["tt1111111"], 1, 2
        )
        self.assertEqual(movie_hashes, {movie_hash})
        self.assertEqual(episode_hashes, {episode_hash})


class StreamBlacklistResponseTests(unittest.IsolatedAsyncioTestCase):
    def _manager(self) -> TorrentManager:
        return TorrentManager(
            media_type="movie",
            media_full_id="tt3333333",
            media_only_id="tt3333333",
            title="Title",
            year=2024,
            year_end=None,
            season=None,
            episode=None,
            aliases={},
            remove_adult_content=False,
        )

    def _torrent(self, info_hash: str) -> dict:
        return {
            "infoHash": info_hash,
            "fileIndex": 0,
            "title": "Title.2024.mkv",
            "seeders": 1,
            "size": 100,
            "tracker": "test",
            "sources": [],
            "parsed": object(),
        }

    async def test_live_scrape_skips_blacklisted_hash(self):
        banned = "a" * 40
        allowed = "b" * 40
        manager = self._manager()
        manager.blacklisted_hashes = {banned}
        with patch.object(manager, "_matches_requested_scope", return_value=True):
            manager._remember_live_torrent(self._torrent(banned))
            manager._remember_live_torrent(self._torrent(allowed))
        self.assertEqual(set(manager.torrents), {allowed})

    async def test_cached_rows_skip_blacklisted_hash(self):
        banned = "a" * 40
        allowed = "b" * 40
        manager = self._manager()
        base_row = {
            "file_index": 0,
            "seeders": 1,
            "size": 100,
            "tracker": "cache",
            "sources_json": "[]",
            "episode": None,
            "updated_at": 1,
            "title": "Title.2024.mkv",
            "parsed_json": '{"raw_title":"Title.2024.mkv"}',
        }
        rows = [
            {**base_row, "info_hash": banned, "is_manual": 1},
            {**base_row, "info_hash": allowed, "is_manual": 1},
        ]

        async def _banned_hashes(*_args, **_kwargs):
            return {banned}

        with (
            patch.object(
                blacklist_service,
                "fetch_blacklisted_info_hashes",
                _banned_hashes,
            ),
            patch.object(manager, "_fetch_cached_rows", return_value=rows),
        ):
            await manager.get_cached_torrents()

        self.assertEqual(set(manager.torrents), {allowed})
        self.assertTrue(manager.primary_cached)

    async def test_drop_removes_hash_added_after_the_read(self):
        banned = "c" * 40
        allowed = "d" * 40
        manager = self._manager()
        manager.blacklisted_hashes = {banned}
        manager.torrents = {banned: {"title": "banned"}, allowed: {"title": "ok"}}
        manager.ranked_torrents = [banned, allowed]
        manager.drop_blacklisted_torrents()
        ranked = [
            info_hash
            for info_hash in manager.ranked_torrents
            if info_hash in manager.torrents
        ]
        self.assertEqual(ranked, [allowed])


class StreamBlacklistAuthTests(unittest.TestCase):
    def test_bearer_password_accepted(self):
        from comet.api.endpoints import admin as admin_endpoints

        with patch.object(admin_endpoints.settings, "ADMIN_DASHBOARD_PASSWORD", "sekrit"):
            admin_endpoints.require_admin_auth(None, "Bearer sekrit")

    def test_wrong_bearer_rejected(self):
        from comet.api.endpoints import admin as admin_endpoints

        with patch.object(admin_endpoints.settings, "ADMIN_DASHBOARD_PASSWORD", "sekrit"):
            with self.assertRaises(HTTPException) as ctx:
                admin_endpoints.require_admin_auth(None, "Bearer wrong")
            self.assertEqual(ctx.exception.status_code, 401)

    def test_missing_auth_rejected(self):
        from comet.api.endpoints import admin as admin_endpoints

        with self.assertRaises(HTTPException):
            admin_endpoints.require_admin_auth(None, None)

    def test_invalid_body_is_400(self):
        from comet.api.endpoints.admin import parse_blacklist_body

        with self.assertRaises(HTTPException) as ctx:
            parse_blacklist_body(
                StreamBlacklistAdd,
                {
                    "mediaType": "series",
                    "mediaId": "tt1234567",
                    "kind": "infohash",
                    "values": ["0123456789abcdef0123456789abcdef01234567"],
                },
            )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
