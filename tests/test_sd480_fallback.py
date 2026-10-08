import unittest
from types import SimpleNamespace

from comet.api.endpoints.stream import (
    _client_disabled_480p,
    _has_playable_stream,
    _sd480_fallback_hashes,
)


def _torrent(resolution, seeders=1, size=1):
    return {
        "parsed": SimpleNamespace(resolution=resolution),
        "seeders": seeders,
        "size": size,
    }


class Sd480FallbackTests(unittest.TestCase):
    def test_disabled_flag_is_only_the_client_480p_switch(self):
        self.assertTrue(_client_disabled_480p({"resolutions": {"r480p": False}}))
        self.assertFalse(_client_disabled_480p({"resolutions": {"r480p": True}}))
        self.assertFalse(_client_disabled_480p({}))

    def test_notices_are_not_playable_results(self):
        self.assertFalse(
            _has_playable_stream(
                [{"name": "[INFO] Comet", "url": "https://comet.feels.legal"}]
            )
        )
        self.assertTrue(
            _has_playable_stream(
                [{"behaviorHints": {"bingeGroup": "comet|torbox|abc"}}]
            )
        )

    def test_fallback_keeps_the_best_480p_and_skips_higher_resolutions(self):
        torrents = {
            "hd": _torrent("1080p", seeders=50),
            "low": _torrent("360p", seeders=40),
            "sd-a": _torrent("480p", seeders=2, size=10),
            "sd-b": _torrent("480p", seeders=9, size=5),
            "sd-c": _torrent("480p", seeders=9, size=20),
        }

        self.assertEqual(
            _sd480_fallback_hashes(torrents, already={"hd"}, limit=2),
            ["sd-c", "sd-b"],
        )
        self.assertEqual(
            _sd480_fallback_hashes(torrents, already={"sd-b"}, limit=5),
            ["sd-c", "sd-a"],
        )
