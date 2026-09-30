import unittest

from comet.services.cache_admission import cap_per_resolution


class _Parsed:
    def __init__(self, resolution):
        self.resolution = resolution


class CacheAdmissionTests(unittest.TestCase):
    def test_cap_keeps_eight_per_resolution_and_the_rest_of_a_short_bucket(self):
        torrents = [
            {"seeders": i, "size": i, "parsed": _Parsed("2160p")} for i in range(10)
        ]
        torrents.extend(
            {"seeders": i, "size": 1, "parsed": _Parsed("1080p")} for i in range(3)
        )

        kept = cap_per_resolution(torrents, limit=8)
        by_resolution = {}
        for torrent in kept:
            by_resolution.setdefault(torrent["parsed"].resolution, []).append(torrent)

        self.assertEqual(len(by_resolution["2160p"]), 8)
        self.assertEqual({item["seeders"] for item in by_resolution["2160p"]}, set(range(2, 10)))
        self.assertEqual(len(by_resolution["1080p"]), 3)


if __name__ == "__main__":
    unittest.main()
