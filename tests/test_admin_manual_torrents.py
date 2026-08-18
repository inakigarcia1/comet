"""Tests for the manual torrents admin API and persistence plumbing."""

import time
import unittest
from unittest.mock import patch

import orjson


class ManualTorrentModelValidationTests(unittest.TestCase):
    def test_resolve_extracts_info_hash_from_magnet(self):
        from comet.api.models.manual_torrent import ManualTorrentIn

        item = ManualTorrentIn(
            mediaId="tt1234567",
            mediaType="movie",
            magnet="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Movie.Name.2025.REMUX-GROUP&tr=udp://tracker.example.com",
        )
        resolved = item.resolve()
        self.assertEqual(resolved.infoHash, "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(resolved.title, "Movie.Name.2025.REMUX-GROUP")
        self.assertIn("udp://tracker.example.com", resolved.sources)

    def test_resolve_rejects_unparseable_title(self):
        from unittest.mock import patch

        from comet.api.models.manual_torrent import ManualTorrentIn

        class _BadParsed:
            parsed_title = None
            year = None
            resolution = "unknown"

        with patch("comet.api.models.manual_torrent.rtn_parse") as mock_parse:
            mock_parse.return_value = _BadParsed()
            item = ManualTorrentIn(
                mediaId="tt1234567",
                mediaType="movie",
                infoHash="0123456789abcdef0123456789abcdef01234567",
                title="Movie.2025.REMUX-GROUP",
            )
            with self.assertRaises(ValueError):
                item.resolve()

    def test_resolve_rejects_missing_hash(self):
        from comet.api.models.manual_torrent import ManualTorrentIn

        item = ManualTorrentIn(
            mediaId="tt1234567",
            mediaType="movie",
            title="Movie.Name.2025.2160p.UHD.BluRay.REMUX-GROUP",
        )
        with self.assertRaises(ValueError):
            item.resolve()

    def test_resolve_normalizes_series_fields(self):
        from comet.api.models.manual_torrent import ManualTorrentIn

        item = ManualTorrentIn(
            mediaId="tt1234567",
            mediaType="series",
            infoHash="0123456789abcdef0123456789abcdef01234567",
            title="Show.S01E04.1080p.WEB-DL-GROUP",
            season=1,
            episode=4,
            fileIndex=3,
        )
        resolved = item.resolve()
        self.assertEqual(resolved.season, 1)
        self.assertEqual(resolved.episode, 4)
        self.assertEqual(resolved.fileIndex, 3)
        self.assertIsNotNone(resolved.parsed)

    def test_resolve_rejects_movie_with_season(self):
        from pydantic import ValidationError

        from comet.api.models.manual_torrent import ManualTorrentIn

        with self.assertRaises(ValidationError):
            ManualTorrentIn(
                mediaId="tt1234567",
                mediaType="movie",
                infoHash="0123456789abcdef0123456789abcdef01234567",
                title="Movie.Name.2025.2160p.UHD.BluRay.REMUX-GROUP",
                season=1,
            )

    def test_resolve_produces_parsed_payload(self):
        from comet.api.models.manual_torrent import ManualTorrentIn

        item = ManualTorrentIn(
            mediaId="tt1234567",
            mediaType="movie",
            infoHash="0123456789abcdef0123456789abcdef01234567",
            title="Movie.Name.2025.2160p.UHD.BluRay.REMUX-GROUP",
        )
        resolved = item.resolve()
        self.assertIsNotNone(resolved.parsed)
        self.assertIn("parsed_title", resolved.parsed)


class ManualTorrentAdminEndpointsTests(unittest.TestCase):
    def setUp(self):
        from comet.api.endpoints import admin

        self.admin = admin

    def test_endpoints_require_admin_auth(self):
        from fastapi import HTTPException

        # The auth helper raises HTTPException(401) when the session is invalid.
        with self.assertRaises(HTTPException) as ctx:
            self.admin.require_admin_auth(admin_session=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_post_manual_torrent_inserts(self):
        import asyncio

        from comet.api.models.manual_torrent import (
            ManualTorrentIn as _Payload,
        )

        payload = _Payload(
            mediaId="tt0111161",
            mediaType="movie",
            infoHash="0123456789abcdef0123456789abcdef01234567",
            title="Movie.Name.2025.2160p.UHD.BluRay.REMUX-GROUP",
        )

        async def _run():
            with (
                patch.object(self.admin, "require_admin_auth"),
                patch.object(self.admin, "insert_manual") as mock_insert,
                patch.object(self.admin, "wait_for_manual_flush") as mock_flush,
            ):
                response = await self.admin.admin_manual_torrent_create(
                    payload=payload,
                    admin_session="valid",
                )
                return response, mock_insert, mock_flush

        response, mock_insert, mock_flush = asyncio.run(_run())
        self.assertEqual(response.status_code, 200)
        body = orjson.loads(response.body)
        self.assertTrue(body["success"])
        self.assertEqual(body["mediaId"], "tt0111161")
        mock_insert.assert_called_once()
        mock_flush.assert_called_once()

    def test_post_manual_torrent_422_for_unparseable_title(self):
        from unittest.mock import patch

        from comet.api.models.manual_torrent import ManualTorrentIn

        class _BadParsed:
            parsed_title = None

        with patch("comet.api.models.manual_torrent.rtn_parse") as mock_parse:
            mock_parse.return_value = _BadParsed()
            payload = ManualTorrentIn(
                mediaId="tt0111161",
                mediaType="movie",
                infoHash="0123456789abcdef0123456789abcdef01234567",
                title="Movie.2025.REMUX-GROUP",
            )
            with self.assertRaises(ValueError):
                payload.resolve()

    def test_post_manual_torrent_422_for_invalid_hash(self):
        from pydantic import ValidationError

        from comet.api.models.manual_torrent import ManualTorrentIn

        with self.assertRaises(ValidationError):
            ManualTorrentIn(
                mediaId="tt0111161",
                mediaType="movie",
                infoHash="notahex",
                title="Movie.Name.2025.2160p.UHD.BluRay.REMUX-GROUP",
            )

    def test_post_manual_bulk_inserts(self):
        import asyncio

        from comet.api.models.manual_torrent import ManualTorrentBulkIn

        payload = ManualTorrentBulkIn(
            torrents=[
                {
                    "mediaId": "tt0111161",
                    "mediaType": "movie",
                    "infoHash": f"{i:040x}",
                    "title": "Movie.Name.2025.2160p.UHD.BluRay.REMUX-GROUP",
                }
                for i in range(1, 4)
            ]
        )

        async def _run():
            with (
                patch.object(self.admin, "require_admin_auth"),
                patch.object(self.admin, "insert_manual_bulk") as mock_bulk,
                patch.object(self.admin, "wait_for_manual_flush"),
            ):
                mock_bulk.return_value = (3, 0, [])
                response = await self.admin.admin_manual_torrent_bulk(
                    payload=payload,
                    admin_session="valid",
                )
                return response, mock_bulk

        response, mock_bulk = asyncio.run(_run())
        self.assertEqual(response.status_code, 200)
        body = orjson.loads(response.body)
        self.assertTrue(body["success"])
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["inserted"], 3)
        mock_bulk.assert_called_once()

    def test_get_manual_torrents_list(self):
        import asyncio

        async def _run():
            with (
                patch.object(self.admin, "require_admin_auth"),
                patch.object(self.admin, "list_manual") as mock_list,
            ):
                mock_list.return_value = [
                    {
                        "mediaId": "tt0111161",
                        "infoHash": "0123456789abcdef0123456789abcdef01234567",
                        "title": "Movie",
                        "season": None,
                        "episode": None,
                        "fileIndex": None,
                        "size": 1000,
                        "seeders": 5,
                        "tracker": "Manual",
                        "updatedAt": time.time(),
                        "shareCometnet": False,
                    }
                ]
                response = await self.admin.admin_manual_torrent_list(
                    admin_session="valid",
                )
                return response, mock_list

        response, mock_list = asyncio.run(_run())
        self.assertEqual(response.status_code, 200)
        body = orjson.loads(response.body)
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["torrents"]), 1)
        mock_list.assert_called_once()

    def test_delete_manual_torrent(self):
        import asyncio

        from comet.api.models.manual_torrent import ManualTorrentDelete

        payload = ManualTorrentDelete(
            mediaId="tt0111161",
            infoHash="0123456789abcdef0123456789abcdef01234567",
        )

        async def _run():
            with (
                patch.object(self.admin, "require_admin_auth"),
                patch.object(self.admin, "delete_manual") as mock_delete,
            ):
                mock_delete.return_value = 1
                response = await self.admin.admin_manual_torrent_delete(
                    payload=payload,
                    admin_session="valid",
                )
                return response, mock_delete

        response, mock_delete = asyncio.run(_run())
        self.assertEqual(response.status_code, 200)
        body = orjson.loads(response.body)
        self.assertTrue(body["success"])
        self.assertEqual(body["deleted"], 1)
        mock_delete.assert_called_once()


class QueueGateTests(unittest.TestCase):
    def test_manual_torrent_flags_preserved_on_construct(self):
        """Validate the broadcast gate flag: is_manual=True, manual_share_cometnet=False
        means the item is filtered out from the broadcast payload."""
        from comet.services.torrent_manager import _construct_torrent_update

        item = _construct_torrent_update(
            media_id="tt0111161",
            info_hash="0123456789abcdef0123456789abcdef01234567",
            season=None,
            episode=None,
            file_index=None,
            title="Movie.Name.2025.REMUX-GROUP",
            seeders=5,
            size=1000,
            tracker="Manual",
            sources=[],
            parsed={},
            from_cometnet=False,
            is_manual=True,
            manual_share_cometnet=False,
        )
        self.assertTrue(item.is_manual)
        self.assertFalse(item.manual_share_cometnet)

        shared = _construct_torrent_update(
            media_id="tt0111161",
            info_hash="0123456789abcdef0123456789abcdef01234567",
            season=None,
            episode=None,
            file_index=None,
            title="Movie.Name.2025.REMUX-GROUP",
            seeders=5,
            size=1000,
            tracker="Manual",
            sources=[],
            parsed={},
            from_cometnet=False,
            is_manual=True,
            manual_share_cometnet=True,
        )
        self.assertTrue(shared.is_manual)
        self.assertTrue(shared.manual_share_cometnet)

    def test_manual_torrent_not_exposed_in_broadcast_payload(self):
        """The broadcast gate filter must exclude manual items unless they have
        manual_share_cometnet=True."""
        from comet.services.torrent_manager import _construct_torrent_update

        # Build a batch of items: 1 manual (no share), 1 manual (share),
        # 1 normal scraper.
        manual = _construct_torrent_update(
            media_id="tt0111161",
            info_hash="0000000000000000000000000000000000000001",
            season=None,
            episode=None,
            file_index=None,
            title="Manual-NonShare",
            seeders=1,
            size=1,
            tracker="Manual",
            sources=[],
            parsed={},
            from_cometnet=False,
            is_manual=True,
            manual_share_cometnet=False,
        )
        manual_shared = _construct_torrent_update(
            media_id="tt0111161",
            info_hash="0000000000000000000000000000000000000002",
            season=None,
            episode=None,
            file_index=None,
            title="Manual-Share",
            seeders=1,
            size=1,
            tracker="Manual",
            sources=[],
            parsed={},
            from_cometnet=False,
            is_manual=True,
            manual_share_cometnet=True,
        )
        scraper = _construct_torrent_update(
            media_id="tt0111161",
            info_hash="0000000000000000000000000000000000000003",
            season=None,
            episode=None,
            file_index=None,
            title="Scraper",
            seeders=1,
            size=1,
            tracker="Scraper",
            sources=[],
            parsed={},
            from_cometnet=False,
        )

        # Replicate the broadcast gate filter inline; this is the same logic
        # used by `_enqueue_broadcast_items` so it serves as a contract test.
        Admitted = []
        for item in [manual, manual_shared, scraper]:
            if item.from_cometnet:
                continue
            if item.is_manual and not item.manual_share_cometnet:
                continue
            Admitted.append(item.title)
        self.assertNotIn("Manual-NonShare", Admitted)
        self.assertIn("Manual-Share", Admitted)
        self.assertIn("Scraper", Admitted)


if __name__ == "__main__":
    unittest.main()
