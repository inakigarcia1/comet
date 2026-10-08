import unittest
from types import SimpleNamespace
from unittest.mock import patch

from comet.services.ranking import (
    allow_unknown_resolution,
    exceeds_file_size_cap,
    rank_worker,
)

GB = 1024**3


def _torrent(size, episodes, resolution="1080p"):
    return {
        "size": size,
        "title": "release",
        "parsed": SimpleNamespace(episodes=episodes, resolution=resolution),
    }


class _Resolutions:
    def __init__(self, unknown):
        self.unknown = unknown

    def model_copy(self, *, update=None):
        clone = _Resolutions(self.unknown)
        if update:
            clone.unknown = update.get("unknown", clone.unknown)
        return clone


class _Settings:
    def __init__(self, unknown):
        self.resolutions = _Resolutions(unknown)

    def model_copy(self, *, update=None):
        clone = _Settings(self.resolutions.unknown)
        if update and "resolutions" in update:
            clone.resolutions = update["resolutions"]
        return clone


class FileSizeCapTests(unittest.TestCase):
    def test_single_file_over_the_plan_is_dropped(self):
        cap = 30 * GB
        self.assertTrue(exceeds_file_size_cap(_torrent(40 * GB, []), cap))
        self.assertTrue(exceeds_file_size_cap(_torrent(40 * GB, [33]), cap))

    def test_pack_size_is_not_the_file_size(self):
        cap = 30 * GB
        pack = _torrent(252 * GB, [1, 500])
        self.assertFalse(exceeds_file_size_cap(pack, cap))
        self.assertFalse(exceeds_file_size_cap(_torrent(80 * GB, [1, 10]), cap))

    def test_matched_file_uses_its_own_size(self):
        cap = 30 * GB
        self.assertFalse(exceeds_file_size_cap(_torrent(288 * 1024**2, [33]), cap))
        self.assertTrue(exceeds_file_size_cap(_torrent(40 * GB, [33]), cap))

    def test_rank_worker_keeps_packs_and_drops_oversized_files(self):
        torrents = {
            "movie": _torrent(40 * GB, []),
            "pack": _torrent(252 * GB, [1, 500]),
            "episode": _torrent(288 * 1024**2, [33]),
            "fat": _torrent(40 * GB, [4]),
        }

        def fetch_all(parsed, settings, ranking):
            return [(True, [], 1) for _ in parsed]

        def keep_all(ranked, _limit):
            return {item.infohash: item for item in ranked}

        with (
            patch("comet.services.ranking.check_fetch_and_rank_many", fetch_all),
            patch("comet.services.ranking.sort_torrents", keep_all),
        ):
            kept = rank_worker(torrents, None, None, 0, 30 * GB, False)

        self.assertEqual(set(kept), {"pack", "episode"})


class UnknownResolutionTests(unittest.TestCase):
    def test_anime_allows_a_release_with_no_stated_resolution(self):
        updated = allow_unknown_resolution(_Settings(unknown=False))
        self.assertTrue(updated.resolutions.unknown)

    def test_already_allowed_settings_are_left_alone(self):
        settings = _Settings(unknown=True)
        self.assertIs(allow_unknown_resolution(settings), settings)
