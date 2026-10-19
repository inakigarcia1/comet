import unittest
from types import SimpleNamespace
from unittest.mock import patch

from comet.services.ranking import (
    allow_unknown_resolution,
    exceeds_file_size_cap,
    rank_worker,
    release_is_pack,
    shown_byte_size,
)

GB = 1024**3


def _torrent(
    size,
    episodes,
    resolution="1080p",
    seasons=(),
    complete=False,
    file_index=None,
    title="release",
):
    return {
        "size": size,
        "title": title,
        "fileIndex": file_index,
        "parsed": SimpleNamespace(
            episodes=episodes,
            seasons=seasons,
            resolution=resolution,
            complete=complete,
        ),
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

    def test_season_without_episodes_is_a_pack(self):
        cap = 30 * GB
        season = _torrent(
            80 * GB,
            [],
            seasons=(1,),
            title="Breaking.Bad.S01.COMPLETE.1080p.BluRay.x265-PSA",
        )
        show = _torrent(
            200 * GB,
            [],
            seasons=tuple(range(1, 8)),
            title="The.Office.US.S01-S07.1080p.BluRay.x265-SILENCE",
        )
        self.assertTrue(release_is_pack(season["parsed"]))
        self.assertFalse(exceeds_file_size_cap(season, cap, series=True))
        self.assertFalse(exceeds_file_size_cap(show, cap, series=True))

    def test_one_episode_a_movie_and_absolute_anime_stay_capped(self):
        cap = 30 * GB
        episode = _torrent(
            40 * GB,
            [3],
            seasons=(1,),
            title="The.Bear.S01E03.1080p.WEB-DL.H.264-NTb",
        )
        movie = _torrent(
            40 * GB,
            [],
            title="Dune.Part.Two.2024.2160p.BluRay.REMUX",
        )
        complete_movie = _torrent(
            40 * GB,
            [],
            complete=True,
            title="Oppenheimer.2023.COMPLETE.UHD.BluRay.REMUX",
        )
        anime = _torrent(
            40 * GB,
            [1000],
            title="One.Piece.E1000.1080p.CR.WEB-DL",
        )
        self.assertTrue(exceeds_file_size_cap(episode, cap, series=True))
        self.assertTrue(exceeds_file_size_cap(movie, cap))
        self.assertTrue(exceeds_file_size_cap(complete_movie, cap))
        self.assertTrue(exceeds_file_size_cap(anime, cap, series=True))

    def test_complete_series_is_a_pack_only_on_a_series_search(self):
        cap = 30 * GB
        pack = _torrent(
            80 * GB,
            [],
            complete=True,
            title="Greys.Anatomy.Serie.Completa.1080p.BluRay",
        )
        self.assertTrue(release_is_pack(pack["parsed"], series=True))
        self.assertFalse(exceeds_file_size_cap(pack, cap, series=True))
        self.assertTrue(exceeds_file_size_cap(pack, cap, series=False))

    def test_episode_range_stays_exempt_from_the_cap(self):
        bundle = _torrent(
            40 * GB,
            list(range(1, 9)),
            seasons=(1,),
            title="Euphoria.US.1x01-08.1080p.AMZN.WEB-DL",
        )
        self.assertTrue(release_is_pack(bundle["parsed"]))
        self.assertFalse(exceeds_file_size_cap(bundle, 30 * GB, series=True))

    def test_matched_file_size_is_what_the_cap_and_the_label_see(self):
        file_size = int(1.5 * GB)
        matched = _torrent(
            file_size,
            [3],
            seasons=(1,),
            file_index=7,
            title="Breaking.Bad.S01E03.1080p.BluRay.x265",
        )
        self.assertFalse(exceeds_file_size_cap(matched, 30 * GB, series=True))
        self.assertEqual(shown_byte_size(matched, {1: 7}, series=True), file_size)

    def test_pack_without_a_file_shows_the_average_or_the_pack(self):
        pack = _torrent(
            80 * GB,
            [],
            seasons=(1,),
            title="Breaking.Bad.S01.COMPLETE.1080p.BluRay.x265-PSA",
        )
        self.assertEqual(shown_byte_size(pack, {1: 10}, series=True), 8 * GB)
        self.assertEqual(shown_byte_size(pack, None, series=True), 80 * GB)
        self.assertEqual(shown_byte_size(pack, {2: 10}, series=True), 80 * GB)

        whole_show = _torrent(
            90 * GB,
            [],
            complete=True,
            title="Greys.Anatomy.Serie.Completa.1080p.BluRay",
        )
        self.assertEqual(
            shown_byte_size(whole_show, {0: 9, 1: 9, 2: 22}, series=True),
            90 * GB // 31,
        )


class UnknownResolutionTests(unittest.TestCase):
    def test_anime_allows_a_release_with_no_stated_resolution(self):
        updated = allow_unknown_resolution(_Settings(unknown=False))
        self.assertTrue(updated.resolutions.unknown)

    def test_already_allowed_settings_are_left_alone(self):
        settings = _Settings(unknown=True)
        self.assertIs(allow_unknown_resolution(settings), settings)
