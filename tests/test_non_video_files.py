import unittest

from comet.utils.parsing import is_non_video_file, is_video, video_file_entries


class NonVideoFileTests(unittest.TestCase):
    def test_archives_and_sidecars_are_not_video(self):
        self.assertTrue(is_non_video_file("[JySzE] Naruto Shippuden Complete.zip"))
        self.assertTrue(is_non_video_file("release.nfo"))
        self.assertTrue(is_non_video_file("subs/episode.srt"))
        self.assertFalse(is_video("pack.zip"))

    def test_video_and_extensionless_titles_stay(self):
        self.assertFalse(is_non_video_file("Naruto Shippuden 074 - Under the Starry Sky.mp4"))
        self.assertFalse(is_non_video_file("[JySzE] Naruto Shippuden - 074 [v2].mkv"))
        self.assertFalse(is_non_video_file("Naruto Shippuden 033 - The New Target"))
        self.assertTrue(is_video("episode.mkv"))

    def test_torrent_expansion_keeps_only_video_files(self):
        files = [
            {"title": "complete.zip", "index": 0},
            {"title": "readme.nfo", "index": 1},
            {"title": "Naruto Shippuden - 074.mkv", "index": 73},
        ]
        kept = video_file_entries(files)
        self.assertEqual([item["index"] for item in kept], [73])
        self.assertEqual(video_file_entries([{"title": "only.zip", "index": 0}]), [])
