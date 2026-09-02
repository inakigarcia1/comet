import unittest
from unittest.mock import AsyncMock, patch

from comet.api.endpoints.playback import (
    _build_playback_media_id,
    _cache_download_link_safely,
    _decode_sources,
    _parse_playback_path,
    _resolve_playback_file_index,
    _row_expected_size,
    _row_is_manual,
    _valid_download_url,
)


class PlaybackCacheTests(unittest.IsolatedAsyncioTestCase):
    def test_playback_media_id_preserves_aggregate_series_scopes(self):
        self.assertEqual(
            _build_playback_media_id("tt1234567", "series", None, None),
            "tt1234567",
        )
        self.assertEqual(
            _build_playback_media_id("tt1234567", "series", 2, None),
            "tt1234567:2",
        )
        self.assertEqual(
            _build_playback_media_id("tt1234567", "series", 2, 3),
            "tt1234567:2:3",
        )
        self.assertEqual(
            _build_playback_media_id("tt1234567", "movie", None, None),
            "tt1234567",
        )

    def test_sources_require_current_string_list_schema(self):
        self.assertEqual(
            _decode_sources(b'["tracker:first", null, "", 42, "tracker:second"]'),
            ["tracker:first", "tracker:second"],
        )
        self.assertEqual(_decode_sources(b"not-json"), [])
        self.assertEqual(_decode_sources(b'{"tracker": "first"}'), [])

    async def test_cache_write_failure_does_not_discard_generated_link(self):
        with (
            patch(
                "comet.api.endpoints.playback.cache_download_link",
                new=AsyncMock(
                    side_effect=RuntimeError(
                        "database rejected https://download.test/?token=secret"
                    )
                ),
            ) as cache,
            patch("comet.api.endpoints.playback.logger.warning") as warning,
        ):
            await _cache_download_link_safely(
                debrid_service="realdebrid",
                account_key_hash="account",
                info_hash="a" * 40,
                season=None,
                episode=None,
                download_url="https://download.test/video",
            )

        cache.assert_awaited_once()
        message = warning.call_args.args[0]
        self.assertIn("RuntimeError", message)
        self.assertNotIn("token=secret", message)

    def test_playback_path_requires_current_canonical_scope(self):
        self.assertEqual(
            _parse_playback_path("a" * 40, "2", "n", "1", "0"),
            ("a" * 40, 2, "n", 1, 0),
        )

        invalid_paths = (
            ("A" * 40, "2", "n", "1", "0"),
            ("a" * 39, "2", "n", "1", "0"),
            ("a" * 40, "n", "n", "1", "0"),
            ("a" * 40, "02", "n", "1", "0"),
            ("a" * 40, "2", "-1", "1", "0"),
            ("a" * 40, "2", "n", "bad", "0"),
            ("a" * 40, "2", "n", "1", "+1"),
        )
        for path in invalid_paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                _parse_playback_path(*path)

    def test_download_urls_require_absolute_http_current_shape(self):
        valid = "https://download.test/video?token=secret"
        self.assertEqual(_valid_download_url(valid), valid)

        for value in (
            None,
            42,
            "",
            "/relative/video",
            "javascript:alert(1)",
            "https://",
            "https://download.test:invalid/video",
            "https://download.test/video\r\nX-Injected: yes",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_valid_download_url(value))

    def test_resolves_n_from_manual_row(self):
        row = {"is_manual": 1, "file_index": 4}
        self.assertTrue(_row_is_manual(row))
        self.assertEqual(
            _resolve_playback_file_index("n", row, is_manual=True),
            "4",
        )

    def test_keeps_n_for_non_manual(self):
        row = {"is_manual": 0, "file_index": 4}
        self.assertEqual(
            _resolve_playback_file_index("n", row, is_manual=False),
            "n",
        )

    def test_numeric_path_index_stays_numeric_for_non_manual(self):
        row = {"is_manual": 0, "file_index": 4}
        self.assertEqual(
            _resolve_playback_file_index("6", row, is_manual=False),
            "6",
        )

    def test_expected_size_ignores_missing_or_zero(self):
        self.assertEqual(_row_expected_size({"size": 816708071}), 816708071)
        self.assertIsNone(_row_expected_size({"size": 0}))
        self.assertIsNone(_row_expected_size(None))
