import unittest

from comet.services.playback_capabilities import torrent_title_allowed


class PlaybackCapabilitiesTests(unittest.TestCase):
    def test_rejects_4k_on_phone_screen(self):
        caps = {
            "screen": {"width": 1080, "height": 2400},
            "decoderCapabilities": {"video/hevc": {"2160p30": True}},
        }
        title = "Movie.2024.2160p.HEVC.WEB-DL-GROUP"
        self.assertFalse(torrent_title_allowed(title, caps))

    def test_allows_1080p_with_matching_cell(self):
        caps = {
            "screen": {"width": 1080, "height": 2400},
            "decoderCapabilities": {"video/avc": {"1080p30": True}},
        }
        title = "Movie.2024.1080p.H264.WEB-DL-GROUP"
        self.assertTrue(torrent_title_allowed(title, caps))


if __name__ == "__main__":
    unittest.main()
