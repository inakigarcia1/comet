import asyncio
import unittest
from unittest.mock import patch

from comet.core.scrape import ScrapeContext
from comet.services.orchestration import TorrentManager, scraper_manager, settings


class TorrentOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_scrapers_receive_titles_selected_from_configured_languages(self):
        manager = TorrentManager(
            media_type="movie",
            media_full_id="tt123",
            media_only_id="tt123",
            title="The Life Ahead",
            year=2020,
            year_end=None,
            season=None,
            episode=None,
            aliases={
                "lang:it": ["La vita davanti a sé"],
                "lang:fr": ["La Vie devant soi"],
            },
            remove_adult_content=False,
        )
        captured = []

        async def capture_request(request):
            captured.append(request)
            if False:
                yield None

        with (
            patch.object(settings, "INDEXER_LANGUAGES", ["it"]),
            patch.object(settings, "INDEXER_INCLUDE_CANONICAL_TITLE", False),
            patch.object(settings, "INDEXER_INCLUDE_ORIGINAL_TITLE", True),
            patch.object(scraper_manager, "scrape_all", new=capture_request),
            patch.object(manager, "cache_torrents"),
            patch("comet.services.orchestration.logger.log") as log,
        ):
            await manager.scrape_torrents(ScrapeContext.LIVE)

        self.assertEqual(
            captured[0].query_titles,
            ("La vita davanti a se",),
        )
        self.assertIs(captured[0].context, ScrapeContext.LIVE)
        log.assert_any_call(
            "SCRAPER",
            "🔤 Indexer titles (1): “La vita davanti a se”",
        )

    async def test_filter_manager_logs_scraper_response_time(self):
        manager = TorrentManager(
            media_type="movie",
            media_full_id="tt123",
            media_only_id="tt123",
            title="Movie",
            year=2026,
            year_end=None,
            season=None,
            episode=None,
            aliases={},
            remove_adult_content=False,
        )

        with patch("comet.services.orchestration.logger.log") as log:
            await manager.filter_manager("Example", [], response_time=0.875)

        log.assert_called_once_with(
            "SCRAPER", "Scraper Example found 0 torrents. Took 0.88s."
        )

    async def test_filter_manager_isolates_invalid_scraper_results(self):
        manager = TorrentManager(
            media_type="movie",
            media_full_id="tt123",
            media_only_id="tt123",
            title="Movie",
            year=2026,
            year_end=None,
            season=None,
            episode=None,
            aliases={},
            remove_adult_content=False,
        )
        valid = {
            "title": "Movie.2026.1080p.WEB-DL",
            "infoHash": "a" * 40,
            "fileIndex": None,
            "seeders": 1,
            "size": 1000,
            "tracker": "Test",
            "sources": [],
        }

        def passthrough(torrents, *args):
            del args
            return torrents

        with (
            patch("comet.services.orchestration.get_executor", return_value=None),
            patch(
                "comet.services.orchestration.filter_worker",
                side_effect=passthrough,
            ),
        ):
            await manager.filter_manager(
                "ThirdParty",
                [
                    None,
                    {"title": "Broken"},
                    {
                        "title": "Missing.fields",
                        "infoHash": "b" * 40,
                        "tracker": "Test",
                        "sources": [],
                    },
                    valid,
                ],
            )
            await manager.filter_manager("ThirdParty", None)

        self.assertEqual(manager.ready_to_cache, [valid])

    async def test_scrape_waits_until_cache_updates_are_enqueued(self):
        manager = TorrentManager(
            media_type="movie",
            media_full_id="tt123",
            media_only_id="tt123",
            title="Title",
            year=2024,
            year_end=None,
            season=None,
            episode=None,
            aliases={},
            remove_adult_content=False,
        )
        cache_started = asyncio.Event()
        release_cache = asyncio.Event()

        async def no_scraper_results(request):
            del request
            if False:
                yield None

        async def cache_torrents():
            cache_started.set()
            await release_cache.wait()

        with (
            patch.object(scraper_manager, "scrape_all", new=no_scraper_results),
            patch.object(manager, "cache_torrents", new=cache_torrents),
        ):
            scrape = asyncio.create_task(manager.scrape_torrents(ScrapeContext.LIVE))
            await cache_started.wait()
            await asyncio.sleep(0)
            self.assertFalse(scrape.done())
            release_cache.set()
            await scrape

    async def test_cache_media_id_reads_start_concurrently(self):
        manager = TorrentManager(
            media_type="movie",
            media_full_id="tt123",
            media_only_id="tt123",
            title="Title",
            year=2024,
            year_end=None,
            season=None,
            episode=None,
            aliases={},
            remove_adult_content=False,
        )
        manager.cache_media_ids = ["tt123", "kitsu:456"]
        primary_started = asyncio.Event()
        alternate_started = asyncio.Event()

        async def fetch_rows(media_id):
            if media_id == "tt123":
                primary_started.set()
                await alternate_started.wait()
            else:
                alternate_started.set()
                await primary_started.wait()
            return []

        with patch.object(manager, "_fetch_cached_rows", new=fetch_rows):
            await asyncio.wait_for(manager.get_cached_torrents(), timeout=1)

        self.assertTrue(primary_started.is_set())
        self.assertTrue(alternate_started.is_set())

    async def test_corrupt_cached_parse_does_not_discard_valid_peer(self):
        manager = TorrentManager(
            media_type="movie",
            media_full_id="tt123",
            media_only_id="tt123",
            title="Title",
            year=2024,
            year_end=None,
            season=None,
            episode=None,
            aliases={},
            remove_adult_content=False,
        )
        base_row = {
            "file_index": 0,
            "seeders": 1,
            "size": 100,
            "tracker": "cache",
            "sources_json": '["tracker:first", null]',
            "episode": None,
            "updated_at": 1,
        }
        rows = [
            {
                **base_row,
                "info_hash": "a" * 40,
                "title": "Corrupt.mkv",
                "parsed_json": "not-json",
            },
            {
                **base_row,
                "info_hash": "b" * 40,
                "title": "Valid.mkv",
                "parsed_json": '{"raw_title":"Valid.mkv"}',
            },
        ]

        with patch.object(manager, "_fetch_cached_rows", return_value=rows):
            await manager.get_cached_torrents()

        self.assertNotIn("a" * 40, manager.torrents)
        self.assertEqual(manager.torrents["b" * 40]["sources"], ["tracker:first"])

    async def test_series_cache_projects_episode_children_without_losing_pack_title(
        self,
    ):
        manager = TorrentManager(
            media_type="series",
            media_full_id="tt123",
            media_only_id="tt123",
            title="Show",
            year=2024,
            year_end=None,
            season=None,
            episode=None,
            aliases={},
            remove_adult_content=False,
        )
        pack_hash = "a" * 40
        episode_hash = "b" * 40
        base_row = {
            "seeders": 1,
            "size": 100,
            "tracker": "cache",
            "sources_json": "[]",
            "updated_at": 1,
        }
        rows = [
            {
                **base_row,
                "info_hash": pack_hash,
                "file_index": None,
                "title": "Show.S01.COMPLETE.mkv",
                "episode": None,
                "parsed_json": (
                    '{"raw_title":"Show.S01.COMPLETE.mkv","seasons":[1],"episodes":[]}'
                ),
            },
            {
                **base_row,
                "info_hash": pack_hash,
                "file_index": 1,
                "title": "Show.S01E01.mkv",
                "episode": 1,
                "parsed_json": (
                    '{"raw_title":"Show.S01E01.mkv","seasons":[1],"episodes":[1]}'
                ),
            },
            {
                **base_row,
                "info_hash": episode_hash,
                "file_index": 0,
                "title": "Show.S02E03.mkv",
                "episode": 3,
                "parsed_json": (
                    '{"raw_title":"Show.S02E03.mkv","seasons":[2],"episodes":[3]}'
                ),
            },
        ]

        with patch.object(manager, "_fetch_cached_rows", return_value=rows):
            await manager.get_cached_torrents()

        self.assertEqual(set(manager.torrents), {pack_hash, episode_hash})
        self.assertEqual(
            manager.torrents[pack_hash]["title"],
            "Show.S01.COMPLETE.mkv",
        )
        self.assertEqual(
            manager.torrents[episode_hash]["title"],
            "Show.S02E03.mkv",
        )

    async def test_manual_cache_row_skips_parsed_scope_filters(self):
        manager = TorrentManager(
            media_type="series",
            media_full_id="tt0316613:1:1",
            media_only_id="tt0316613",
            title="Los Simuladores",
            year=2002,
            year_end=None,
            season=1,
            episode=1,
            aliases={},
            remove_adult_content=False,
            reject_unknown_episode_files=True,
        )
        manual_hash = "a" * 40
        scraper_hash = "b" * 40
        parsed_json = (
            '{"raw_title":"T1-01. Tarjeta de Navidad","parsed_title":'
            '"T1-01. Tarjeta de Navidad","resolution":"SD","seasons":[],'
            '"episodes":[],"languages":[],"dubbed":false,"date":null,'
            '"year":null,"complete":false}'
        )
        base_row = {
            "file_index": 4,
            "title": "T1-01. Tarjeta de Navidad",
            "seeders": 1,
            "size": 100,
            "tracker": "Manual",
            "sources_json": "[]",
            "episode": 1,
            "updated_at": 1,
            "parsed_json": parsed_json,
        }
        rows = [
            {**base_row, "info_hash": manual_hash, "is_manual": 1},
            {
                **base_row,
                "info_hash": scraper_hash,
                "tracker": "Scraper",
                "is_manual": 0,
            },
        ]

        with patch.object(manager, "_fetch_cached_rows", return_value=rows):
            await manager.get_cached_torrents()

        self.assertIn(manual_hash, manager.torrents)
        self.assertTrue(manager.torrents[manual_hash]["is_manual"])
        self.assertNotIn(scraper_hash, manager.torrents)

    async def test_manual_480p_survives_when_rank_worker_drops_all(self):
        from RTN import DefaultRanking, parse

        from comet.core.models import CometSettingsModel

        manager = TorrentManager(
            media_type="series",
            media_full_id="tt0316613:1:1",
            media_only_id="tt0316613",
            title="Los Simuladores",
            year=2002,
            year_end=None,
            season=1,
            episode=1,
            aliases={},
            remove_adult_content=False,
        )
        manual_hash = "a" * 40
        scraper_hash = "b" * 40
        manager.torrents = {
            scraper_hash: {
                "title": "Show.S01E01.1080p.WEB-DL",
                "parsed": parse("Show.S01E01.1080p.WEB-DL"),
                "size": 1_000_000,
                "is_manual": False,
            },
            manual_hash: {
                "title": "Show.S01E01.480p.WEB-DL",
                "parsed": parse("Show.S01E01.480p.WEB-DL"),
                "size": 1_000_000,
                "is_manual": True,
            },
        }
        captured = {}

        def fake_rank_worker(torrents, *args):
            captured["hashes"] = set(torrents)
            return {}

        with patch(
            "comet.services.orchestration.rank_worker",
            side_effect=fake_rank_worker,
        ):
            await manager.rank_torrents(
                CometSettingsModel(),
                DefaultRanking(),
                0,
                0,
                True,
            )

        self.assertEqual(captured["hashes"], {scraper_hash})
        self.assertEqual(list(manager.ranked_torrents), [manual_hash])
