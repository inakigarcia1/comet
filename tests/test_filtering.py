import unittest
from unittest.mock import patch

from RTN import parse

from comet.services.filtering import (
    _clone_parsed,
    _normalize_aliases,
    exact_alias_match,
    filter_worker,
    settings,
)


class AliasFilteringTests(unittest.TestCase):
    def test_cached_parse_clone_detaches_mutated_languages(self):
        cached = parse("Movie.2024.MULTI.FRENCH.1080p.WEB-DL")
        clone = _clone_parsed(cached)

        clone.languages.append("de")

        self.assertNotIn("de", cached.languages)
        self.assertIn("de", clone.languages)

    def test_empty_alias_does_not_match_every_title(self):
        self.assertFalse(exact_alias_match("unrelated title", [""]))

    def test_short_or_partial_alias_does_not_bypass_title_matching(self):
        self.assertFalse(exact_alias_match("quality release", ["it"]))
        self.assertFalse(exact_alias_match("friends swapped places", ["swap"]))
        self.assertFalse(exact_alias_match("friends swapped places", ["swapped"]))
        self.assertTrue(exact_alias_match("swapped", ["swapped"]))

    def test_alias_normalization_keeps_only_current_unique_entries(self):
        self.assertEqual(
            _normalize_aliases(
                {
                    "": ["Ignored"],
                    "en": "Ignored",
                    "fr": [None, "", "  ", " Titre ", "Titre", 1],
                }
            ),
            {"fr": ["Titre"]},
        )
        self.assertEqual(_normalize_aliases([]), {})

    def test_empty_alias_cannot_bypass_worker_title_matching(self):
        torrents = [
            {
                "title": "Completely.Different.2024.1080p.WEB-DL.x264",
                "infoHash": "1" * 40,
            }
        ]

        actual = filter_worker(
            torrents,
            "The Matrix",
            1999,
            0,
            "movie",
            {"ez": [""]},
            False,
        )

        self.assertEqual(actual, [])

    def test_language_scoped_alias_sets_the_exact_language(self):
        torrent = {
            "title": "Il.Postino.2020.1080p.WEB-DL",
            "infoHash": "1" * 40,
        }

        with patch.object(settings, "SMART_LANGUAGE_DETECTION", True):
            actual = filter_worker(
                [torrent],
                "The Postman",
                2020,
                None,
                "movie",
                {"lang:it": ["Il Postino"]},
                False,
            )

        self.assertEqual(actual[0]["parsed"].languages, ["it"])

    def test_uk_spinoff_does_not_match_the_us_show(self):
        actual = filter_worker(
            [
                {
                    "title": "Law and Order UK S01E01 Care 1080p AMZN WEB-DL",
                    "infoHash": "1" * 40,
                }
            ],
            "Law & Order",
            1990,
            None,
            "series",
            {},
            False,
            origin="United States",
        )

        self.assertEqual(actual, [])

    def test_same_show_without_a_country_suffix_stays(self):
        actual = filter_worker(
            [
                {
                    "title": "Law.and.Order.S01E01.1080p.WEB-DL",
                    "infoHash": "1" * 40,
                }
            ],
            "Law & Order",
            1990,
            None,
            "series",
            {},
            False,
            origin="United States",
        )

        self.assertEqual(len(actual), 1)

    def test_country_suffix_stays_when_it_is_the_shows_origin(self):
        actual = filter_worker(
            [
                {
                    "title": "The.Office.UK.S01E01.1080p.WEB-DL",
                    "infoHash": "1" * 40,
                }
            ],
            "The Office",
            2001,
            2003,
            "series",
            {},
            False,
            origin="United Kingdom",
        )

        self.assertEqual(len(actual), 1)

    def test_region_tag_after_the_year_stays(self):
        actual = filter_worker(
            [
                {
                    "title": "Paddington.2014.1080p.BluRay.UK",
                    "infoHash": "1" * 40,
                }
            ],
            "Paddington",
            2014,
            None,
            "movie",
            {},
            False,
            origin="United Kingdom",
        )

        self.assertEqual(len(actual), 1)

    def test_movie_search_drops_collections_and_series_packs(self):
        kept = "Resident Evil (2026) 1080p AMZN WEB-DL DDP5 1 H 264-FLUX"
        actual = filter_worker(
            [
                {
                    "title": "Resident Evil (2002-2016) Hexalogie BluRay 1080p x264",
                    "infoHash": "1" * 40,
                },
                {
                    "title": "Resident Evil S01 COMPLETE 720p NF WEBRip x264",
                    "infoHash": "2" * 40,
                },
                {
                    "title": kept,
                    "infoHash": "3" * 40,
                },
                {
                    "title": "Resident Evil HD Remaster - [DODI Repack]",
                    "infoHash": "4" * 40,
                },
            ],
            "Resident Evil",
            2026,
            None,
            "movie",
            {},
            False,
            origin="Germany, United States",
        )

        self.assertEqual([torrent["title"] for torrent in actual], [kept])


if __name__ == "__main__":
    unittest.main()
