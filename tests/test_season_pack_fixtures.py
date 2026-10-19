import ast
import csv
import unittest
from pathlib import Path
from types import SimpleNamespace

from comet.services.ranking import release_is_pack

_FIXTURES = Path(__file__).parent / "fixtures" / "torrent_season_pack_fixtures.csv"


def _seasons(raw: str) -> tuple[int, ...]:
    if not raw:
        return ()
    return tuple(int(season) for season in ast.literal_eval(raw))


def _parsed(*, seasons=(), episodes=(), complete=False, title=""):
    return SimpleNamespace(
        seasons=seasons,
        episodes=episodes,
        complete=complete,
        raw_title=title,
    )


class SeasonPackFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with _FIXTURES.open(encoding="utf-8", newline="") as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_fixture_file_is_the_full_set(self):
        self.assertEqual(len(self.rows), 256)

    def test_csv_shapes_match_the_size_cap_pack_rule(self):
        for row in self.rows:
            kind = row["expected_kind"]
            title = row["name"]
            expected_pack = row["expected_is_season_pack"] == "True"
            with self.subTest(id=row["id"], kind=kind, name=title):
                if kind == "episode_bundle":
                    parsed = _parsed(episodes=(1, 2), title=title)
                    self.assertTrue(release_is_pack(parsed, series=True))
                    self.assertFalse(expected_pack)
                    continue
                if kind == "ambiguous_default_no":
                    continue
                if kind == "episode":
                    parsed = _parsed(episodes=(1,), title=title)
                    self.assertFalse(release_is_pack(parsed, series=True))
                    self.assertFalse(expected_pack)
                    continue
                if kind == "non_pack":
                    parsed = _parsed(title=title)
                    self.assertFalse(release_is_pack(parsed))
                    self.assertFalse(release_is_pack(parsed, series=True))
                    self.assertFalse(expected_pack)
                    continue
                seasons = _seasons(row["expected_seasons"])
                if seasons:
                    parsed = _parsed(seasons=seasons, title=title)
                    self.assertTrue(release_is_pack(parsed))
                else:
                    parsed = _parsed(complete=True, title=title)
                    self.assertTrue(release_is_pack(parsed, series=True))
                    self.assertFalse(release_is_pack(parsed))
                self.assertTrue(expected_pack)

    def test_real_parser_season_token_is_a_pack_when_it_sees_one(self):
        from RTN import parse

        parsed = parse("The Mentalist S01 1080p BluRay x265-RARBG")
        if not tuple(getattr(parsed, "seasons", None) or ()):
            self.skipTest("installed parser does not read a glued S01 token")
        self.assertTrue(release_is_pack(parsed))
        self.assertFalse(
            release_is_pack(parse("Dune.Part.Two.2024.2160p.BluRay.REMUX"))
        )
