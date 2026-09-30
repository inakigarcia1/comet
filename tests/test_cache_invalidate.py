import unittest

from comet.services.cache_invalidate import parse_cache_target, parse_invalidate_body


class ParseCacheTargetTests(unittest.TestCase):
    def test_movie_id(self):
        target = parse_cache_target("tt0111161")
        self.assertEqual(target.media_id, "tt0111161")
        self.assertIsNone(target.season)
        self.assertIsNone(target.episode)

    def test_episode_id(self):
        target = parse_cache_target(" tt0098844:1:5 ")
        self.assertEqual((target.media_id, target.season, target.episode), ("tt0098844", 1, 5))

    def test_rejects_partial_or_junk(self):
        self.assertIsNone(parse_cache_target("tt0098844:1"))
        self.assertIsNone(parse_cache_target("../tt0111161"))
        self.assertIsNone(parse_cache_target(""))
        self.assertIsNone(parse_cache_target(None))


class ParseInvalidateBodyTests(unittest.TestCase):
    def test_scopes(self):
        movie = parse_invalidate_body({"scope": "movie", "mediaId": "tt0111161"})
        self.assertEqual((movie.scope, movie.season, movie.episode), ("movie", None, None))

        series = parse_invalidate_body({"scope": "series", "mediaId": " tt0098844 "})
        self.assertEqual(series.scope, "series")
        self.assertEqual(series.media_id, "tt0098844")

        season = parse_invalidate_body(
            {"scope": "season", "mediaId": "tt0098844", "season": 2}
        )
        self.assertEqual((season.scope, season.season, season.episode), ("season", 2, None))

        episode = parse_invalidate_body(
            {"scope": "episode", "mediaId": "tt0098844", "season": "1", "episode": 5}
        )
        self.assertEqual((episode.scope, episode.season, episode.episode), ("episode", 1, 5))

    def test_scope_requires_the_fields_it_needs(self):
        self.assertIsNone(parse_invalidate_body({"scope": "season", "mediaId": "tt0098844"}))
        self.assertIsNone(
            parse_invalidate_body({"scope": "episode", "mediaId": "tt0098844", "season": 1})
        )
        self.assertIsNone(parse_invalidate_body({"scope": "movie", "mediaId": "tt0098844:1:5"}))
        self.assertIsNone(parse_invalidate_body({"scope": "nope", "mediaId": "tt0111161"}))

    def test_legacy_payload_without_scope(self):
        legacy = parse_invalidate_body({"mediaId": "tt0111161"})
        self.assertEqual(legacy.scope, "legacy")
        episode = parse_invalidate_body({"mediaId": "tt0098844:1:5"})
        self.assertEqual((episode.scope, episode.season, episode.episode), ("episode", 1, 5))


if __name__ == "__main__":
    unittest.main()
