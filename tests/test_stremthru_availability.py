import unittest
from unittest.mock import AsyncMock, patch

from comet.debrid.exceptions import DebridAuthError, DebridLinkGenerationError
from comet.debrid.stremthru import (
    StremThru,
    _pick_file_by_trusted_index,
    _prepare_cached_torrents,
    _season_episode_from_filename,
)


class _ResponseContext:
    def __init__(self, payload=None, *, status=200, error=None, text="raw"):
        self.payload = payload
        self.status = status
        self.error = error
        self.raw_text = text
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.exited = True

    async def json(self, **kwargs):
        del kwargs
        if self.error is not None:
            raise self.error
        return self.payload

    async def text(self):
        return self.raw_text


class _Session:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        del args, kwargs
        return self.response

    def post(self, *args, **kwargs):
        del args, kwargs
        return self.response


class StremThruAvailabilityTests(unittest.TestCase):
    def test_malformed_torrents_and_files_are_isolated_once(self):
        responses = [
            None,
            {"data": {"items": "invalid"}},
            {
                "data": {
                    "items": [
                        {"status": "cached", "files": []},
                        {
                            "status": "cached",
                            "hash": "a" * 40,
                            "files": [
                                None,
                                {"name": "Sample.mkv", "index": 0, "size": 10},
                                {
                                    "name": "folder/First.S01E01.mkv",
                                    "index": 1,
                                    "size": 20,
                                },
                                {"name": 42},
                                {"name": "Second.S01E02.MP4", "index": 2, "size": 30},
                            ],
                        },
                        {"status": "downloading", "hash": "b" * 40, "files": []},
                    ]
                }
            },
        ]

        torrents, filenames = _prepare_cached_torrents(
            responses,
            is_offcloud=False,
        )

        self.assertEqual(filenames, ["First.S01E01.mkv", "Second.S01E02.MP4"])
        self.assertEqual([torrent["info_hash"] for torrent in torrents], ["a" * 40])
        self.assertEqual(
            [filename for _, filename in torrents[0]["files"]],
            filenames,
        )


class StremThruResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_json_response_closes_after_complete_payload_read(self):
        response = _ResponseContext({"data": {"value": "complete"}})
        client = StremThru(_Session(response), None, None, "realdebrid:token", "")

        payload = await client._post_store_json("/endpoint", {}, "read store")

        self.assertEqual(payload, {"data": {"value": "complete"}})
        self.assertTrue(response.exited)

    async def test_premium_response_closes_on_auth_error(self):
        response = _ResponseContext({"error": "invalid"})
        client = StremThru(_Session(response), None, None, "realdebrid:token", "")

        with self.assertRaises(DebridAuthError):
            await client.check_premium()

        self.assertTrue(response.exited)

    async def test_instant_response_closes_on_json_error(self):
        response = _ResponseContext(error=ValueError("invalid JSON"))
        client = StremThru(_Session(response), None, None, "realdebrid:token", "")

        self.assertIsNone(await client.get_instant(["a" * 40]))
        self.assertTrue(response.exited)

    async def test_magnet_list_response_closes_on_invalid_payload(self):
        response = _ResponseContext({"data": None})
        client = StremThru(_Session(response), None, None, "realdebrid:token", "")

        self.assertEqual(await client.list_magnets(), (None, 0))
        self.assertTrue(response.exited)

    async def test_unexpected_link_error_is_typed_and_visible(self):
        client = StremThru(None, None, None, "realdebrid:token", "")
        with (
            patch.object(
                client,
                "_post_store_json",
                new=AsyncMock(side_effect=RuntimeError("transport failed")),
            ),
            self.assertRaises(DebridLinkGenerationError) as raised,
        ):
            await client.generate_download_link(
                "a" * 40,
                "0",
                "Movie.mkv",
                "Movie",
                None,
                None,
            )

        self.assertEqual(raised.exception.payload["error_type"], "RuntimeError")
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)


class StremThruTrustedFileIndexTests(unittest.IsolatedAsyncioTestCase):
    _HASH = "db544aade436fc7a2d0ce82b3920166ea2cff6b5"
    _FILES = [
        {
            "name": "T1-01. Tarjeta de Navidad [480p].mp4",
            "index": 4,
            "size": 100,
            "link": "https://store.example/file4",
        },
        {
            "name": "T1-02. El Gran Bonete [480p].mp4",
            "index": 6,
            "size": 100,
            "link": "https://store.example/file6",
        },
    ]

    def _client(self):
        return StremThru(None, "tt0316613:1:1", "tt0316613", "torbox:token", "")

    def _magnet_then_link(self, files=None):
        files = self._FILES if files is None else files
        calls = []

        async def _post(endpoint, payload, action):
            calls.append((endpoint, payload, action))
            if endpoint.startswith("/magnets"):
                return {"data": {"status": "cached", "files": files}}
            if endpoint.startswith("/link/generate"):
                return {"data": {"link": "https://cdn.example/play"}}
            raise AssertionError(endpoint)

        return _post, calls

    async def test_trust_file_index_picks_unparseable_name(self):
        client = self._client()
        post, calls = self._magnet_then_link()
        with patch.object(client, "_post_store_json", side_effect=post):
            url = await client.generate_download_link(
                self._HASH,
                "4",
                "T1-01. Tarjeta de Navidad [480p].mp4",
                "Los Simuladores",
                1,
                1,
                trust_file_index=True,
            )

        self.assertEqual(url, "https://cdn.example/play")
        self.assertEqual(calls[1][1], {"link": "https://store.example/file4"})

    async def test_without_trust_file_index_rejects_unparseable_episode_name(self):
        client = self._client()
        post, _calls = self._magnet_then_link()
        with (
            patch.object(client, "_post_store_json", side_effect=post),
            patch.object(
                client,
                "_episode_request_context",
                new=AsyncMock(return_value=(True, 1, 1, None)),
            ),
            self.assertRaises(DebridLinkGenerationError) as raised,
        ):
            await client.generate_download_link(
                self._HASH,
                "4",
                "T1-01. Tarjeta de Navidad [480p].mp4",
                "Los Simuladores",
                1,
                1,
            )

        self.assertEqual(raised.exception.upstream_error_code, "EPISODE_MATCH_NOT_FOUND")

    async def test_trust_file_index_uses_queued_magnet_when_files_exist(self):
        client = self._client()
        files = self._FILES
        calls = []

        async def _post(endpoint, payload, action):
            calls.append((endpoint, payload, action))
            if endpoint.startswith("/magnets"):
                return {"data": {"status": "queued", "files": files}}
            if endpoint.startswith("/link/generate"):
                return {"data": {"link": "https://cdn.example/play"}}
            raise AssertionError(endpoint)

        with patch.object(client, "_post_store_json", side_effect=_post):
            url = await client.generate_download_link(
                self._HASH,
                "6",
                "T1-02. El Gran Bonete [480p].mp4",
                "Los Simuladores",
                1,
                2,
                trust_file_index=True,
            )

        self.assertEqual(url, "https://cdn.example/play")
        self.assertEqual(calls[1][1], {"link": "https://store.example/file6"})

    async def test_trust_file_index_falls_back_to_list_position(self):
        client = self._client()
        files = [
            {
                "name": "nfo.txt",
                "index": -1,
                "size": 10,
                "link": "https://store.example/0",
            },
            {
                "name": "Movie.Name.2024.1080p.mkv",
                "index": -1,
                "size": 100,
                "link": "https://store.example/pos1",
            },
        ]
        post, calls = self._magnet_then_link(files)
        with patch.object(client, "_post_store_json", side_effect=post):
            url = await client.generate_download_link(
                self._HASH,
                "1",
                "Movie.Name.2024.1080p.mkv",
                "Movie.Name.2024",
                None,
                None,
                trust_file_index=True,
            )

        self.assertEqual(url, "https://cdn.example/play")
        self.assertEqual(calls[1][1], {"link": "https://store.example/pos1"})

    async def test_trust_file_index_ignores_torbox_id_and_picks_episode_name(self):
        client = self._client()
        files = [
            {
                "name": "T1-09. El último héroe [480p].ia.mp4",
                "index": 4,
                "size": 1082041816,
                "link": "https://store.example/wrong",
            },
            {
                "name": "T1-01. Tarjeta de Navidad [480p].mp4",
                "index": 2,
                "size": 828608370,
                "link": "https://store.example/orig",
            },
            {
                "name": "T1-01. Tarjeta de Navidad [480p].ia.mp4",
                "index": 1,
                "size": 816708071,
                "link": "https://store.example/ia",
            },
        ]
        post, calls = self._magnet_then_link(files)
        with patch.object(client, "_post_store_json", side_effect=post):
            url = await client.generate_download_link(
                self._HASH,
                "4",
                "Los.Simuladores.S01E01.720p.WEB-DL",
                "Los Simuladores",
                1,
                1,
                trust_file_index=True,
            )

        self.assertEqual(url, "https://cdn.example/play")
        self.assertEqual(calls[1][1], {"link": "https://store.example/ia"})

    async def test_trust_file_index_missing_link_is_not_cached_yet(self):
        client = self._client()
        files = [
            {
                "name": "T1-01. Tarjeta de Navidad [480p].mp4",
                "index": 4,
                "size": 100,
            }
        ]
        post, _calls = self._magnet_then_link(files)
        with (
            patch.object(client, "_post_store_json", side_effect=post),
            self.assertRaises(DebridLinkGenerationError) as raised,
        ):
            await client.generate_download_link(
                self._HASH,
                "4",
                "T1-01. Tarjeta de Navidad [480p].mp4",
                "Los Simuladores",
                1,
                1,
                trust_file_index=True,
            )

        self.assertEqual(raised.exception.upstream_error_code, "MEDIA_NOT_CACHED_YET")


class TrustedFilenameMatchTests(unittest.TestCase):
    def test_parses_archive_style_and_standard_episode_names(self):
        self.assertEqual(
            _season_episode_from_filename("T1-01. Tarjeta de Navidad [480p].ia.mp4"),
            (1, 1),
        )
        self.assertEqual(
            _season_episode_from_filename("T1-12 Marcela & Paul [NF-480p].mp4"),
            (1, 12),
        )
        self.assertEqual(
            _season_episode_from_filename("Show.Name.S02E03.720p.mkv"),
            (2, 3),
        )
        self.assertEqual(_season_episode_from_filename("Movie.2024.1080p.mkv"), None)

    def test_does_not_use_torbox_file_id_as_torrent_index(self):
        files = [
            {
                "name": "T1-09. El último héroe [480p].ia.mp4",
                "index": 4,
                "size": 10,
                "link": "wrong",
            },
            {
                "name": "T1-01. Tarjeta de Navidad [480p].ia.mp4",
                "index": 99,
                "size": 8,
                "link": "ia",
            },
        ]
        picked = _pick_file_by_trusted_index(files, "4", season=1, episode=1)
        self.assertEqual(picked["link"], "ia")

    def test_prefers_ia_variant_when_both_exist(self):
        files = [
            {
                "name": "T1-01. Tarjeta de Navidad [480p].mp4",
                "index": 2,
                "size": 828,
                "link": "orig",
            },
            {
                "name": "T1-01. Tarjeta de Navidad [480p].ia.mp4",
                "index": 0,
                "size": 816,
                "link": "ia",
            },
        ]
        picked = _pick_file_by_trusted_index(files, "4", season=1, episode=1)
        self.assertEqual(picked["link"], "ia")

    def test_unique_size_match_for_movies(self):
        files = [
            {"name": "a.mkv", "index": 9, "size": 111, "link": "a"},
            {"name": "b.mkv", "index": 4, "size": 222, "link": "b"},
        ]
        picked = _pick_file_by_trusted_index(
            files, "4", season=None, episode=None, expected_size=222
        )
        self.assertEqual(picked["link"], "b")
