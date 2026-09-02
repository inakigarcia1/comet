"""Manual torrents skip resolution caps / cachedOnly."""

import unittest

from comet.api.endpoints.stream import _select_info_hashes_by_resolution


class _Parsed:
    def __init__(self, resolution):
        self.resolution = resolution


class SelectInfoHashesManualTests(unittest.TestCase):
    def test_manual_survives_cached_only_and_resolution_cap(self):
        manual_hash = "a" * 40
        cached_hash = "b" * 40
        extra_hash = "c" * 40
        torrents = {
            manual_hash: {"parsed": _Parsed("480p"), "is_manual": True},
            cached_hash: {"parsed": _Parsed("1080p"), "is_manual": False},
            extra_hash: {"parsed": _Parsed("1080p"), "is_manual": False},
        }
        ranked = [cached_hash, extra_hash, manual_hash]
        selected = _select_info_hashes_by_resolution(
            ranked,
            torrents,
            {cached_hash: {"torbox": True}},
            max_results=1,
            cached_only=True,
            prioritize_cached=False,
        )

        self.assertEqual(selected[0], manual_hash)
        self.assertIn(cached_hash, selected)
        self.assertNotIn(extra_hash, selected)


if __name__ == "__main__":
    unittest.main()
