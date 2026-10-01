import unittest

from comet.services.compatibility import (
    evaluate_title,
    parse_filename,
    playback_sort_key,
    score_band,
)
from comet.services.playback_capabilities import torrent_title_allowed

UNABOMBER = "UNABOMBER.2026.2160p.NF.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FHC.mkv"
BATMAN = "The.Batman.2022.1080p.BluRay.x264.DTS.mkv"
EIGHT_BIT = "2160p.HEVC.Main.8bit.SDR.mkv"
UNKNOWN_HEVC = "Random.Release.2160p.x265.DDP5.1.mkv"
DUNE = "Dune.Part.Two.2024.2160p.WEB-DL.x265.10bit.HDR10.DDP5.1.Atmos.mkv"


def _device(*, main10: bool, dolby: bool = False, screen=(3840, 2160), profiles: bool = True):
    hevc_profiles = ["Main", "Main10"] if main10 else ["Main"]
    hevc_bits = [8, 10] if main10 else [8]
    payload = {
        "platform": "android-tv",
        "playerBackend": "exoplayer",
        "screen": {"width": screen[0], "height": screen[1]},
        "decoderCapabilities": {
            "video/hevc": {"2160p24": True, "2160p30": True, "1080p60": True},
            "video/avc": {"1080p60": True, "2160p30": True},
        },
        "hdr": {
            "hdr10": main10,
            "hdr10Plus": False,
            "dolbyVision": dolby,
            "hlg": main10,
            "probed": True,
        },
        "audio": {"aac": True, "ac3": True, "eac3": True, "dts": True, "truehd": False, "opus": True},
    }
    if profiles:
        payload["video"] = {
            "hevc": {
                "profiles": hevc_profiles,
                "maxLevel": "5.1",
                "bitDepths": hevc_bits,
                "maxWidth": 3840,
                "maxHeight": 2160,
                "hdr": ["hdr10"] if main10 else [],
            },
            "avc": {
                "profiles": ["Baseline", "Main", "High"],
                "maxLevel": "5.1",
                "bitDepths": [8],
                "maxWidth": 3840,
                "maxHeight": 2160,
            },
        }
    return payload


class CompatibilityScoreTests(unittest.TestCase):
    def test_unabomber_is_incompatible_without_main10_and_1080p_ranks_above(self):
        device = _device(main10=False)
        risky = evaluate_title(UNABOMBER, device)
        safe = evaluate_title(BATMAN, device)
        self.assertIsNotNone(risky)
        self.assertIsNotNone(safe)
        self.assertTrue(risky.incompatible)
        self.assertLessEqual(risky.score, 8)
        self.assertFalse(safe.incompatible)
        self.assertGreater(safe.score, risky.score)
        self.assertIn("Main10", risky.summary)

    def test_explicit_8bit_4k_outranks_1080p_when_main_is_supported(self):
        device = _device(main10=False)
        plain = evaluate_title(EIGHT_BIT, device)
        safe = evaluate_title(BATMAN, device)
        unknown = evaluate_title(UNKNOWN_HEVC, device)
        self.assertFalse(plain.incompatible)
        self.assertFalse(unknown.incompatible)
        self.assertGreater(plain.score, safe.score)
        self.assertGreater(safe.score, unknown.score)

    def test_main10_device_prefers_explicit_10bit_4k_over_1080p(self):
        device = _device(main10=True, dolby=True)
        dune = evaluate_title(DUNE, device)
        safe = evaluate_title(BATMAN, device)
        self.assertFalse(dune.incompatible)
        self.assertGreater(score_band(dune.score), score_band(safe.score))

    def test_unknown_4k_hevc_ties_or_loses_to_1080p_only_when_main10_is_missing(self):
        missing = _device(main10=False)
        present = _device(main10=True)
        unknown_missing = evaluate_title(UNKNOWN_HEVC, missing)
        safe_missing = evaluate_title(BATMAN, missing)
        unknown_present = evaluate_title(UNKNOWN_HEVC, present)
        safe_present = evaluate_title(BATMAN, present)
        self.assertGreater(score_band(safe_missing.score), score_band(unknown_missing.score))
        ordered = sorted(
            (unknown_present, safe_present),
            key=lambda item: playback_sort_key(item.score, item.height),
            reverse=True,
        )
        self.assertEqual(ordered[0].height, 2160)

    def test_dv_without_dolby_vision_support_ranks_below_plain_1080p(self):
        device = _device(main10=True, dolby=False)
        risky = evaluate_title(UNABOMBER, device)
        safe = evaluate_title(BATMAN, device)
        self.assertFalse(risky.incompatible)
        self.assertGreater(safe.score, risky.score)

    def test_phone_screen_rejects_4k_and_keeps_1080p(self):
        device = _device(main10=True, screen=(1080, 2400))
        self.assertFalse(torrent_title_allowed("Movie.2024.2160p.HEVC.WEB-DL-GROUP", device))
        self.assertTrue(torrent_title_allowed(BATMAN, device))

    def test_legacy_size_matrix_does_not_treat_main10_as_proven(self):
        legacy = {
            "screen": {"width": 3840, "height": 2160},
            "decoderCapabilities": {"video/hevc": {"2160p30": True}, "video/avc": {"1080p30": True}},
        }
        risky = evaluate_title(UNABOMBER, legacy)
        safe = evaluate_title(BATMAN, legacy)
        self.assertFalse(risky.incompatible)
        self.assertGreater(safe.score, risky.score)

    def test_observed_main10_failure_blocks_the_same_class(self):
        device = _device(main10=True, dolby=True)
        device["observedFailures"] = [
            {"codec": "hevc", "profile": "Main10", "minHeight": 2160, "codecs": "hvc1.2.4.L150.90", "count": 1}
        ]
        failed = evaluate_title(DUNE, device)
        safe = evaluate_title(EIGHT_BIT, device)
        self.assertTrue(failed.incompatible)
        self.assertFalse(safe.incompatible)

    def test_level_and_fps_blocks_when_the_device_reported_them(self):
        device = _device(main10=True)
        device["video"]["hevc"]["maxLevel"] = "5.0"
        device["decoderCapabilities"]["video/hevc"] = {"2160p30": True}
        level = evaluate_title("2160p.HEVC.Main10.Level5.1.60fps.HDR10.mkv", device)
        self.assertTrue(level.incompatible)

    def test_similar_scores_break_the_tie_toward_higher_resolution(self):
        self.assertLess(playback_sort_key(92, 1080), playback_sort_key(90, 2160))
        self.assertGreater(playback_sort_key(92, 1080), playback_sort_key(70, 2160))
        self.assertEqual(score_band(92), score_band(88))
        self.assertNotEqual(score_band(92), score_band(70))

    def test_unknown_codec_scores_below_an_explicit_compatible_1080p(self):
        device = _device(main10=False)
        unknown = evaluate_title("Succession.S04E10.2160p.MAX.WEB-DL.DDP5.1.mkv", device)
        safe = evaluate_title(BATMAN, device)
        self.assertFalse(unknown.incompatible)
        self.assertGreater(safe.score, unknown.score)
        self.assertEqual(parse_filename("2160p.mkv").codec.source, "unknown")


if __name__ == "__main__":
    unittest.main()
