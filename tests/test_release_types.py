"""Tests for the centralized release-type taxonomy and web_config exposure."""

import base64
import unittest

import orjson

from comet.core.config_validation import config_check
from comet.core.models import ConfigModel, web_config
from comet.utils.release_types import (
    RELEASE_TYPE_KEYS,
    RELEASE_TYPE_LABELS,
    classify_release,
    matches_release_filters,
    release_type_choices,
)
from tests.rtn_stub import parse


class ReleaseTypeTaxonomyTests(unittest.TestCase):
    def test_release_type_keys_contains_expected_categories(self):
        expected = {
            "remux",
            "bluray",
            "web",
            "webdl",
            "webmux",
            "hdtv",
            "dvd",
            "bdrip",
            "brrip",
            "dvdrip",
            "hdrip",
            "webrip",
            "webdlrip",
            "tvrip",
            "cam",
            "screener",
            "telecine",
            "telesync",
            "unknown",
        }
        self.assertEqual(set(RELEASE_TYPE_KEYS), expected)

    def test_release_type_labels_have_one_per_key(self):
        self.assertEqual(set(RELEASE_TYPE_LABELS), set(RELEASE_TYPE_KEYS))

    def test_classify_release_maps_rtn_rip_to_key(self):
        self.assertEqual(classify_release(parse("Movie.2025.REMUX")), "remux")
        self.assertEqual(classify_release(parse("Movie.2025.WEB-DL")), "webdl")
        self.assertEqual(classify_release(parse("Movie.2025.WEBRip")), "webrip")
        self.assertEqual(classify_release(parse("Movie.2025.CAM")), "cam")
        self.assertEqual(classify_release(parse("Movie.2025.DVD")), "dvd")
        self.assertEqual(classify_release(parse("Movie.2025.HDTV")), "hdtv")

    def test_classify_release_unknown_returns_unknown(self):
        self.assertEqual(classify_release(None), "unknown")
        self.assertEqual(classify_release(parse("Movie.2025.WeirdFormat")), "unknown")

    def test_choices_returns_complete_list(self):
        choices = release_type_choices()
        self.assertEqual(len(choices), len(RELEASE_TYPE_KEYS))
        self.assertEqual({c["key"] for c in choices}, set(RELEASE_TYPE_KEYS))

    def test_blocklist_wins_over_allow(self):
        parsed = parse("Movie.2025.REMUX")
        self.assertFalse(
            matches_release_filters(parsed, allow=["remux"], block=["remux"])
        )

    def test_empty_allow_accepts_all_non_blocked(self):
        parsed = parse("Movie.2025.REMUX")
        self.assertTrue(matches_release_filters(parsed, allow=[], block=[]))
        self.assertTrue(matches_release_filters(parsed, allow=[], block=["cam"]))

    def test_allow_filters_out_unspecified(self):
        parsed = parse("Movie.2025.REMUX")
        self.assertFalse(matches_release_filters(parsed, allow=["bluray"], block=[]))
        self.assertTrue(matches_release_filters(parsed, allow=["remux"], block=[]))

    def test_blocklist_catches_blocked(self):
        parsed = parse("Movie.2025.CAM")
        self.assertFalse(matches_release_filters(parsed, allow=[], block=["cam"]))


class ConfigModelNewFieldsTests(unittest.TestCase):
    def test_default_config_has_all_new_fields(self):
        cfg = ConfigModel()
        self.assertEqual(cfg.maxSize, 0)
        self.assertEqual(cfg.maxSizeMovie, 0)
        self.assertEqual(cfg.maxSizeSeries, 0)
        self.assertEqual(cfg.minBitrateMbps, 0)
        self.assertEqual(cfg.maxBitrateMbps, 0)
        self.assertEqual(cfg.filenameInclude, [])
        self.assertEqual(cfg.filenameExclude, [])
        self.assertEqual(cfg.releaseTypesAllowlist, [])
        self.assertEqual(cfg.releaseTypesBlocklist, [])

    def test_max_bitrate_must_exceed_min_bitrate(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            ConfigModel(minBitrateMbps=10, maxBitrateMbps=5)

    def test_negative_max_size_clamps_to_zero(self):
        cfg = ConfigModel(maxSize=-100, maxSizeMovie=-50, maxSizeSeries=-25)
        self.assertEqual(cfg.maxSize, 0)
        self.assertEqual(cfg.maxSizeMovie, 0)
        self.assertEqual(cfg.maxSizeSeries, 0)

    def test_string_lists_normalize_to_lists(self):
        cfg = ConfigModel(
            filenameInclude=["FraMeSToR", " NTb ", ""],
            releaseTypesBlocklist=["CAM", "remux"],
        )
        self.assertEqual(cfg.filenameInclude, ["FraMeSToR", "NTb"])
        self.assertEqual(cfg.releaseTypesBlocklist, ["CAM", "remux"])


class WebConfigReleaseTypesTests(unittest.TestCase):
    def test_web_config_has_release_types(self):
        self.assertIn("releaseTypes", web_config)
        self.assertEqual(len(web_config["releaseTypes"]), len(RELEASE_TYPE_KEYS))


class LegacyConfigCompatibilityTests(unittest.TestCase):
    def test_legacy_b64_config_with_only_maxSize_returns_defaults(self):
        encoded = base64.b64encode(orjson.dumps({"maxSize": 5 * 1024**3})).decode()
        cfg = config_check(encoded, strict_b64config=True)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["maxSize"], 5 * 1024**3)
        # New fields default to inactive.
        self.assertEqual(cfg["maxSizeMovie"], 0)
        self.assertEqual(cfg["maxSizeSeries"], 0)
        self.assertEqual(cfg["minBitrateMbps"], 0)
        self.assertEqual(cfg["maxBitrateMbps"], 0)
        self.assertEqual(cfg["filenameInclude"], [])
        self.assertEqual(cfg["filenameExclude"], [])
        self.assertEqual(cfg["releaseTypesAllowlist"], [])
        self.assertEqual(cfg["releaseTypesBlocklist"], [])

    def test_full_new_fields_survive_round_trip(self):
        payload = {
            "maxSize": 5 * 1024**3,
            "maxSizeMovie": 10 * 1024**3,
            "maxSizeSeries": 2 * 1024**3,
            "minBitrateMbps": 2.0,
            "maxBitrateMbps": 20.0,
            "filenameInclude": ["FraMeSToR", "NTb"],
            "filenameExclude": ["YIFY"],
            "releaseTypesAllowlist": ["remux", "bluray"],
            "releaseTypesBlocklist": ["cam", "telesync"],
        }
        encoded = base64.b64encode(orjson.dumps(payload)).decode()
        cfg = config_check(encoded, strict_b64config=True)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["maxSizeMovie"], 10 * 1024**3)
        self.assertEqual(cfg["maxSizeSeries"], 2 * 1024**3)
        self.assertEqual(cfg["minBitrateMbps"], 2.0)
        self.assertEqual(cfg["maxBitrateMbps"], 20.0)
        self.assertEqual(cfg["filenameInclude"], ["FraMeSToR", "NTb"])
        self.assertEqual(cfg["filenameExclude"], ["YIFY"])
        self.assertEqual(cfg["releaseTypesAllowlist"], ["remux", "bluray"])
        self.assertEqual(cfg["releaseTypesBlocklist"], ["cam", "telesync"])


if __name__ == "__main__":
    unittest.main()
