import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from comet.metadata.episode_index import (
    EpisodeIndexService,
    absolute_index_from_rows,
    database,
)


class EpisodeIndexRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_air_date_requires_valid_current_date(self):
        service = EpisodeIndexService(session=None)
        with patch.object(database, "fetch_one", return_value={"air_date": "invalid"}):
            self.assertIsNone(await service._get_cached_air_date("tt123", 1, 2, None))

        with patch.object(
            database,
            "fetch_one",
            return_value={"air_date": "2026-07-22T12:00:00Z"},
        ):
            self.assertEqual(
                await service._get_cached_air_date("tt123", 1, 2, None),
                "2026-07-22",
            )

    async def test_invalid_refresh_timestamp_is_stale(self):
        service = EpisodeIndexService(session=None)
        for value in (None, True, "invalid", float("inf")):
            with (
                self.subTest(value=value),
                patch.object(database, "fetch_val", return_value=value),
            ):
                self.assertFalse(await service._is_series_index_fresh("tt123", 1.0))

    async def test_air_date_reverse_lookup_refreshes_the_existing_index_once(self):
        service = EpisodeIndexService(session=None)
        with (
            patch.object(
                service,
                "_get_cached_episode",
                new=AsyncMock(side_effect=[None, (3, 9)]),
            ) as cached_lookup,
            patch.object(
                service,
                "_is_series_index_fresh",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                service,
                "_refresh_from_cinemeta",
                new=AsyncMock(),
            ) as refresh,
        ):
            episode = await service.get_episode_by_air_date("tt1234567", "2026-07-25")

        self.assertEqual(episode, (3, 9))
        self.assertEqual(cached_lookup.await_count, 2)
        refresh.assert_awaited_once_with("tt1234567")

    async def test_rows_and_refresh_marker_share_one_transaction(self):
        service = EpisodeIndexService(session=None)
        events = []

        @asynccontextmanager
        async def transaction():
            events.append("begin")
            try:
                yield
            except Exception:
                events.append("rollback")
                raise

        async def upsert_rows(rows):
            events.append(("rows", rows))

        async def delete_rows(series_id):
            events.append(("delete", series_id))

        async def fail_marker(series_id, refreshed_at):
            events.append(("marker", series_id, refreshed_at))
            raise RuntimeError("marker failed")

        rows = [{"season": 1, "episode": 1}]
        with (
            patch.object(database, "transaction", new=transaction),
            patch.object(service, "_delete_series_air_dates", new=delete_rows),
            patch.object(service, "_upsert_series_air_dates", new=upsert_rows),
            patch.object(service, "_upsert_series_refresh", new=fail_marker),
        ):
            with self.assertRaisesRegex(RuntimeError, "marker failed"):
                await service._replace_series_index("tt123", 42.0, rows)

        self.assertEqual(
            events,
            [
                "begin",
                ("delete", "tt123"),
                ("rows", rows),
                ("marker", "tt123", 42.0),
                "rollback",
            ],
        )


class AbsoluteEpisodeIndexTests(unittest.TestCase):
    def test_counts_broadcast_order_and_skips_specials(self):
        rows = [{"season": 0, "episode": 1}]
        rows += [{"season": 1, "episode": episode} for episode in range(1, 33)]
        rows += [{"season": 2, "episode": episode} for episode in range(1, 22)]

        absolute, mapping = absolute_index_from_rows(rows, 2, 1)

        self.assertEqual(absolute, 33)
        self.assertEqual(mapping[33], (2, 1))
        self.assertEqual(mapping[1], (1, 1))
        self.assertNotIn(0, {season for season, _episode in mapping.values()})

    def test_requires_the_requested_row_and_season_one(self):
        rows = [{"season": 2, "episode": 1}]
        self.assertEqual(absolute_index_from_rows(rows, 2, 1), (None, {}))
        self.assertEqual(
            absolute_index_from_rows([{"season": 1, "episode": 1}], 1, 2),
            (None, {}),
        )
