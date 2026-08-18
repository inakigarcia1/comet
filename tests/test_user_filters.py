"""Tests for the user-controlled filter pipeline."""

import unittest

from comet.services.user_filters import (
    BitrateFilter,
    FilenameFilter,
    ReleaseTypeFilter,
    build_user_filters,
    compute_effective_max_size,
    has_include_but_no_match,
)
from tests.rtn_stub import parse


class FilenameFilterTests(unittest.TestCase):
    def test_empty_lists_accept_anything(self):
        f = FilenameFilter(None, None)
        self.assertTrue(f.matches("Anything.2024.1080p.WEB-DL-GROUP"))
        self.assertTrue(f.is_active is False)

    def test_include_matches_substring_case_insensitive(self):
        f = FilenameFilter(["FraMeSToR"], [])
        self.assertTrue(f.matches("Movie.2024.1080p.FraMeSToR-Group"))
        self.assertTrue(f.matches("movie.2024.1080p.framestor-group"))
        self.assertFalse(f.matches("Movie.2024.1080p.YTS"))

    def test_exclude_blocks_substring(self):
        f = FilenameFilter([], ["YIFY"])
        self.assertFalse(f.matches("Movie.2024.1080p.YIFY"))
        self.assertTrue(f.matches("Movie.2024.1080p.NTb"))

    def test_exclude_wins_over_include(self):
        f = FilenameFilter(["FraMeSToR"], ["YIFY"])
        self.assertTrue(f.matches("Movie.2024.1080p.FraMeSToR"))
        self.assertFalse(f.matches("Movie.2024.1080p.FraMeSToR.YIFY"))

    def test_whitespace_normalized(self):
        f = FilenameFilter(["  FraMeSToR  ", ""], None)
        self.assertTrue(f.matches("Movie.2024.framestor-Group"))

    def test_is_active(self):
        self.assertFalse(FilenameFilter(None, None).is_active)
        self.assertTrue(FilenameFilter(["x"], None).is_active)
        self.assertTrue(FilenameFilter(None, ["y"]).is_active)


class ReleaseTypeFilterTests(unittest.TestCase):
    def test_empty_lists_pass_through(self):
        f = ReleaseTypeFilter(None, None)
        self.assertTrue(f.matches(parse("Movie.2025.REMUX")))
        self.assertFalse(f.is_active)

    def test_blocklist(self):
        f = ReleaseTypeFilter(None, ["cam"])
        self.assertFalse(f.matches(parse("Movie.2025.CAM")))
        self.assertTrue(f.matches(parse("Movie.2025.REMUX")))

    def test_allowlist(self):
        f = ReleaseTypeFilter(["remux", "bluray"], None)
        self.assertTrue(f.matches(parse("Movie.2025.REMUX")))
        self.assertFalse(f.matches(parse("Movie.2025.WEB-DL")))

    def test_blocklist_wins(self):
        f = ReleaseTypeFilter(["remux"], ["remux"])
        self.assertFalse(f.matches(parse("Movie.2025.REMUX")))


class BitrateFilterTests(unittest.TestCase):
    def test_disabled_when_zero(self):
        f = BitrateFilter(0, 0, 100)
        self.assertFalse(f.is_active)
        self.assertTrue(f.matches(10_000_000_000, scope_matches=True))

    def test_disabled_when_duration_zero(self):
        f = BitrateFilter(5, 50, 0)
        self.assertFalse(f.is_active)

    def test_exact_calculation(self):
        # size=10 GB, duration=100 min → (10*1024^3 * 8) / (100*60 * 1e6) ≈ 14.32 Mbps
        f = BitrateFilter(0, 0, 100)
        size = 10 * 1024**3
        # With no min/max, the filter is inactive.
        self.assertTrue(f.matches(size, scope_matches=True))
        # min=1.0, max=20.0 → 14.32 is in range.
        f = BitrateFilter(1.0, 20.0, 100)
        self.assertTrue(f.matches(size, scope_matches=True))
        # min=15.0 → fail (14.32 < 15).
        f = BitrateFilter(15.0, 100, 100)
        self.assertFalse(f.matches(size, scope_matches=True))
        # max=14.0 → fail (14.32 > 14).
        f = BitrateFilter(0.0, 14.0, 100)
        self.assertFalse(f.matches(size, scope_matches=True))

    def test_missing_size_does_not_filter(self):
        f = BitrateFilter(100, 200, 60)
        self.assertTrue(f.matches(None, scope_matches=True))

    def test_scope_mismatch_skips_bitrate(self):
        f = BitrateFilter(100, 200, 60)
        self.assertTrue(f.matches(10_000_000_000, scope_matches=False))

    def test_boundary_exact(self):
        # size=12 MB, duration=8s → (12e6*8)/(8*1e6) = 12 Mbps
        f = BitrateFilter(12, 13, 0.1333)
        size = 12 * 1024 * 1024
        self.assertTrue(f.matches(size, scope_matches=True))

    def test_invalid_duration_inputs(self):
        f = BitrateFilter(5, 50, None)
        self.assertFalse(f.is_active)
        f = BitrateFilter(5, 50, -1)
        self.assertFalse(f.is_active)


class ComputeMaxSizeTests(unittest.TestCase):
    def test_movie_override(self):
        cfg = {"maxSizeMovie": 10 * 1024**3, "maxSize": 5 * 1024**3}
        self.assertEqual(compute_effective_max_size(cfg, "movie"), 10 * 1024**3)

    def test_series_override(self):
        cfg = {"maxSizeSeries": 2 * 1024**3, "maxSize": 5 * 1024**3}
        self.assertEqual(compute_effective_max_size(cfg, "series"), 2 * 1024**3)

    def test_falls_back_to_legacy(self):
        cfg = {"maxSize": 5 * 1024**3}
        self.assertEqual(compute_effective_max_size(cfg, "movie"), 5 * 1024**3)
        self.assertEqual(compute_effective_max_size(cfg, "series"), 5 * 1024**3)

    def test_zero_means_disable(self):
        cfg = {"maxSize": 0, "maxSizeMovie": 0, "maxSizeSeries": 0}
        self.assertEqual(compute_effective_max_size(cfg, "movie"), 0)
        self.assertEqual(compute_effective_max_size(cfg, "series"), 0)

    def test_invalid_values(self):
        self.assertEqual(compute_effective_max_size({}, "movie"), 0)
        self.assertEqual(compute_effective_max_size({"maxSize": "x"}, "movie"), 0)


class BuildUserFiltersTests(unittest.TestCase):
    def test_build_full_config(self):
        cfg = {
            "filenameInclude": ["FraMeSToR"],
            "filenameExclude": ["YIFY"],
            "releaseTypesAllowlist": ["remux"],
            "releaseTypesBlocklist": ["cam"],
            "minBitrateMbps": 5,
            "maxBitrateMbps": 50,
        }
        f = build_user_filters(cfg, duration_minutes=100)
        self.assertTrue(f.any_active())
        self.assertTrue(f.bitrate.is_active)

    def test_full_aggregate_filter(self):
        cfg = {
            "filenameInclude": ["FraMeSToR"],
            "releaseTypesBlocklist": ["cam"],
            "minBitrateMbps": 5,
            "maxBitrateMbps": 50,
        }
        f = build_user_filters(cfg, duration_minutes=100)
        torrent = {
            "title": "Movie.2025.REMUX.FraMeSToR",
            "size": 5 * 1024**3,
            "parsed": parse("Movie.2025.REMUX.FraMeSToR"),
        }
        self.assertTrue(f.filter_torrent(torrent, scope_matches=True))

    def test_full_aggregate_filter_rejects_cam(self):
        cfg = {"releaseTypesBlocklist": ["cam"]}
        f = build_user_filters(cfg)
        cam = parse("Movie.2025.CAM")
        self.assertFalse(
            f.filter_torrent(
                {"title": "Movie.2025.CAM", "parsed": cam}, scope_matches=True
            )
        )


class HasIncludeButNoMatchTests(unittest.TestCase):
    def test_returns_true_when_no_match(self):
        f = FilenameFilter(["FraMeSToR"], None)
        self.assertTrue(has_include_but_no_match([{"title": "Movie.2025.YTS"}], f))

    def test_returns_false_when_match(self):
        f = FilenameFilter(["FraMeSToR"], None)
        self.assertFalse(
            has_include_but_no_match(
                [{"title": "Movie.2025.FraMeSToR"}, {"title": "Movie.2025.YTS"}],
                f,
            )
        )

    def test_returns_false_when_include_empty(self):
        f = FilenameFilter(None, None)
        self.assertFalse(has_include_but_no_match([{"title": "anything"}], f))


if __name__ == "__main__":
    unittest.main()
