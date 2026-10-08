import unittest
from types import SimpleNamespace

from comet.metadata.episode_index import absolute_index_from_rows
from comet.scrapers.models import ScrapeRequest
from comet.services.orchestration import TorrentManager
from comet.utils.parsing import match_parsed_episode_target

# Season lengths from Cinemeta on 2026-10-08. That is the feed Comet writes
# into series_episode_index. A special in season 0 is added in the fixture
# and must not move the absolute number.
CATALOG = (
    ("Naruto: Shippuden", "tt0988824", (32, 21, 18, 17, 24, 31, 8, 24, 21, 26, 20, 18, 35, 25, 28, 13, 32, 20, 18, 19, 8, 42)),
    ("Naruto", "tt0409591", (35, 48, 48, 48, 41)),
    ("One Piece", "tt0388629", (8, 22, 17, 13, 9, 22, 39, 13, 52, 31, 99, 56, 100, 35, 62, 49, 118, 33, 98, 14, 194, 70, 25)),
    ("Attack on Titan", "tt2560140", (25, 12, 22, 30)),
    ("Dragon Ball Z", "tt0121220", (39, 35, 33, 32, 26, 29, 25, 34, 38)),
    ("Death Note", "tt0877057", (37,)),
    ("Fullmetal Alchemist: Brotherhood", "tt1355642", (64,)),
    ("Cowboy Bebop", "tt0213338", (26,)),
    ("Neon Genesis Evangelion", "tt0112159", (26,)),
    ("Demon Slayer: Kimetsu no Yaiba", "tt9335498", (26, 7, 11, 11, 8)),
    ("Jujutsu Kaisen", "tt12343534", (24, 23, 12, 1)),
    ("Spy x Family", "tt13706018", (25, 12, 13)),
    ("Bleach", "tt0434665", (20, 21, 22, 28, 18, 22, 20, 16, 22, 16, 7, 17, 36, 51, 26, 24)),
    ("Hunter x Hunter", "tt2098220", (58, 78, 12)),
    ("One Punch Man", "tt4508902", (12, 12, 12)),
    ("Steins;Gate", "tt1910272", (24,)),
    ("Code Geass", "tt0994314", (25, 25)),
    ("My Hero Academia", "tt5626028", (13, 25, 25, 25, 25, 25, 21, 11)),
    ("Vinland Saga", "tt10233448", (24, 24)),
    ("Re: Zero - Starting Life in Another World", "tt5607616", (25, 25, 16, 19)),
    ("JoJo's Bizarre Adventure", "tt2359704", (26, 48, 39, 39, 38, 12)),
    ("Pokemon", "tt0168366", (82, 36, 41, 52, 65, 40, 52, 52, 47, 51, 52, 52, 34, 84, 58, 93, 47, 146, 136, 155)),
    ("Chainsaw Man", "tt13616990", (12,)),
    ("Mob Psycho 100", "tt5897304", (12, 13, 12)),
    ("Tokyo Ghoul", "tt3741634", (12, 12, 24)),
    ("Sword Art Online", "tt2250192", (25, 24, 24, 23)),
    ("Haikyu!!", "tt3398540", (25, 25, 10, 25)),
    ("Violet Evergarden", "tt7078180", (13,)),
    ("Made in Abyss", "tt7222086", (13, 12)),
    ("Black Clover", "tt7441658", (170, 13)),
    ("Mushoku Tensei: Jobless Reincarnation", "tt13293588", (23, 24, 14)),
    ("Solo Leveling", "tt21209876", (12, 13)),
    ("Rurouni Kenshin", "tt0182629", (27, 35, 33)),
    ("Clannad", "tt1118804", (23, 24)),
)

# Spots where the seasonal number and the broadcast number are easy to mix up.
CHECKPOINTS = (
    ("Naruto: Shippuden", 2, 1, 33),
    ("Naruto: Shippuden", 3, 1, 54),
    ("Naruto: Shippuden", 22, 42, 500),
    ("Naruto", 2, 1, 36),
    ("Naruto", 5, 41, 220),
    ("One Piece", 2, 1, 9),
    ("Attack on Titan", 2, 1, 26),
    ("Attack on Titan", 4, 1, 60),
    ("Dragon Ball Z", 2, 1, 40),
    ("Death Note", 1, 37, 37),
    ("Demon Slayer: Kimetsu no Yaiba", 2, 1, 27),
    ("Jujutsu Kaisen", 2, 1, 25),
    ("Bleach", 2, 1, 21),
    ("Hunter x Hunter", 2, 1, 59),
    ("Code Geass", 2, 1, 26),
    ("Spy x Family", 2, 1, 26),
    ("Solo Leveling", 2, 1, 13),
    ("My Hero Academia", 2, 1, 14),
    ("Black Clover", 2, 1, 171),
    ("Cowboy Bebop", 1, 1, 1),
    ("Chainsaw Man", 1, 12, 12),
    ("Pokemon", 2, 1, 83),
)


def _rows(counts):
    rows = [{"season": 0, "episode": 1}]
    for season, length in enumerate(counts, start=1):
        for episode in range(1, length + 1):
            rows.append({"season": season, "episode": episode})
    return rows


def _catalog_by_name():
    return {name: counts for name, _imdb, counts in CATALOG}


class AnimeAbsoluteCatalogTests(unittest.TestCase):
    def test_every_episode_keeps_broadcast_order(self):
        for name, _imdb, counts in CATALOG:
            rows = _rows(counts)
            running = 0
            with self.subTest(name=name):
                for season, length in enumerate(counts, start=1):
                    for episode in range(1, length + 1):
                        running += 1
                        absolute, _mapping = absolute_index_from_rows(rows, season, episode)
                        self.assertEqual(
                            absolute,
                            running,
                            f"{name} S{season:02d}E{episode:02d}",
                        )
                self.assertEqual(running, sum(counts), name)

    def test_famous_checkpoints(self):
        catalog = _catalog_by_name()
        for name, season, episode, expected in CHECKPOINTS:
            with self.subTest(name=name, season=season, episode=episode):
                absolute, mapping = absolute_index_from_rows(
                    _rows(catalog[name]), season, episode
                )
                self.assertEqual(absolute, expected)
                self.assertEqual(mapping[expected], (season, episode))

    def test_seasonless_file_matches_absolute_number_not_episode_one(self):
        catalog = _catalog_by_name()
        for name, _imdb, counts in CATALOG:
            if len(counts) < 2:
                continue
            absolute, _mapping = absolute_index_from_rows(_rows(counts), 2, 1)
            with self.subTest(name=name):
                self.assertGreater(absolute, 1)
                self.assertTrue(
                    match_parsed_episode_target(
                        SimpleNamespace(seasons=[], episodes=[absolute]),
                        2,
                        1,
                        absolute_episode=absolute,
                    )
                )
                self.assertTrue(
                    match_parsed_episode_target(
                        SimpleNamespace(seasons=[2], episodes=[1]),
                        2,
                        1,
                        absolute_episode=absolute,
                    )
                )
                self.assertFalse(
                    match_parsed_episode_target(
                        SimpleNamespace(seasons=[], episodes=[1]),
                        2,
                        1,
                        absolute_episode=absolute,
                    )
                )

    def test_queries_keep_season_codes_and_add_the_absolute_number(self):
        catalog = _catalog_by_name()
        for name, imdb, counts in CATALOG:
            if len(counts) < 2:
                continue
            absolute, _mapping = absolute_index_from_rows(_rows(counts), 2, 1)
            request = ScrapeRequest(
                media_type="series",
                media_id=f"{imdb}:2:1",
                media_only_id=imdb,
                title=name,
                season=2,
                episode=1,
                absolute_episode=absolute,
            )
            queries = request.title_queries(include_episode_variants=True)
            with self.subTest(name=name):
                self.assertIn(f"{name} S02E01", queries)
                self.assertIn(f"{name} {absolute}", queries)
                self.assertIn(f"{name} {absolute:03d}", queries)
                self.assertNotIn(f"{name} 001", queries)

    def test_single_cour_does_not_add_a_second_number_for_episode_one(self):
        for name, imdb, counts in CATALOG:
            if len(counts) != 1:
                continue
            request = ScrapeRequest(
                media_type="series",
                media_id=f"{imdb}:1:1",
                media_only_id=imdb,
                title=name,
                season=1,
                episode=1,
                absolute_episode=1,
            )
            with self.subTest(name=name):
                self.assertEqual(
                    request.title_queries(include_episode_variants=True),
                    (name, f"{name} S01", f"{name} S01E01"),
                )

    def test_shippuden_pack_range_covers_the_cour_but_not_episode_one(self):
        self.assertTrue(
            match_parsed_episode_target(
                SimpleNamespace(seasons=[], episodes=[33, 53]),
                2,
                1,
                absolute_episode=33,
            )
        )
        self.assertFalse(
            match_parsed_episode_target(
                SimpleNamespace(seasons=[], episodes=[33, 53]),
                2,
                1,
                absolute_episode=54,
            )
        )

    def test_absolute_file_is_stored_on_the_seasonal_slot(self):
        catalog = _catalog_by_name()
        for name, imdb, counts in CATALOG:
            if len(counts) < 2:
                continue
            _absolute, mapping = absolute_index_from_rows(_rows(counts), 2, 1)
            manager = TorrentManager(
                media_type="series",
                media_full_id=f"{imdb}:2:1",
                media_only_id=imdb,
                title=name,
                year=2000,
                year_end=None,
                season=2,
                episode=1,
                aliases={},
                remove_adult_content=False,
                search_season=2,
                search_episode=1,
                absolute_episode=_absolute,
                absolute_index=mapping,
            )
            stored = []
            manager._append_cache_file_infos(
                stored,
                {
                    "parsed": SimpleNamespace(seasons=[], episodes=[_absolute]),
                    "infoHash": "hash",
                    "fileIndex": None,
                    "title": name,
                    "size": 1,
                    "seeders": 1,
                    "tracker": "Nyaa",
                    "sources": [],
                },
            )
            opener = []
            manager._append_cache_file_infos(
                opener,
                {
                    "parsed": SimpleNamespace(seasons=[], episodes=[1]),
                    "infoHash": "hash",
                    "fileIndex": None,
                    "title": name,
                    "size": 1,
                    "seeders": 1,
                    "tracker": "Nyaa",
                    "sources": [],
                },
            )
            with self.subTest(name=name):
                self.assertEqual(
                    [(row["season"], row["episode"]) for row in stored],
                    [(2, 1)],
                )
                self.assertEqual(
                    [(row["season"], row["episode"]) for row in opener],
                    [(1, 1)],
                )

    def test_a_normal_series_without_an_absolute_number_still_matches_episode_one(self):
        self.assertTrue(
            match_parsed_episode_target(
                SimpleNamespace(seasons=[], episodes=[1]),
                2,
                1,
            )
        )
        request = ScrapeRequest(
            media_type="series",
            media_id="tt0903747:2:1",
            media_only_id="tt0903747",
            title="Breaking Bad",
            season=2,
            episode=1,
        )
        self.assertEqual(
            request.title_queries(include_episode_variants=True),
            (
                "Breaking Bad",
                "Breaking Bad S02",
                "Breaking Bad S02E01",
            ),
        )
