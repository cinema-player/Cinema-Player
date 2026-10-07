#!/usr/bin/env python3
"""Media-directory names and the playlist folder line."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import cinema_player as player


class NormalizeMediaDirectoriesTests(unittest.TestCase):
    def test_legacy_paths_and_named_entries(self):
        home = os.path.expanduser("~")
        items = player.normalize_media_directories([
            "~/films",
            {"path": "~/films", "name": "should not replace"},
            {"path": "/data/stills", "name": "  Stills  "},
            {"path": "  ", "name": "empty"},
            {"name": "no path"},
            12,
            {"path": "/data/stills", "name": "Other"},
        ])
        self.assertEqual(
            items,
            [
                {"path": os.path.abspath(os.path.join(home, "films")), "name": ""},
                {"path": "/data/stills", "name": "Stills"},
            ],
        )

    def test_name_is_trimmed_to_the_limit(self):
        name = "N" * (player.MEDIA_DIRECTORY_NAME_LIMIT + 5)
        items = player.normalize_media_directories([{"path": "/media/a", "name": name}])
        self.assertEqual(len(items[0]["name"]), player.MEDIA_DIRECTORY_NAME_LIMIT)

    def test_rejects_non_lists(self):
        self.assertEqual(player.normalize_media_directories(None), [])
        self.assertEqual(player.normalize_media_directories({"path": "/a"}), [])


class PlaylistLocationLabelTests(unittest.TestCase):
    def test_unnamed_directory_keeps_the_path(self):
        directories = [{"path": "/media/films", "name": ""}]
        label = player.playlist_location_label("/media/films/day/clip.mp4", directories)
        self.assertEqual(label, "/media/films/day")

    def test_name_replaces_the_directory(self):
        directories = [{"path": "/media/films", "name": "Filme"}]
        self.assertEqual(
            player.playlist_location_label("/media/films/clip.mp4", directories),
            "Filme",
        )

    def test_subfolders_stay_after_the_name(self):
        directories = [{"path": "/media/films", "name": "Filme"}]
        self.assertEqual(
            player.playlist_location_label("/media/films/2024/day/clip.mp4", directories),
            "Filme / 2024 / day",
        )

    def test_longest_named_directory_wins(self):
        directories = [
            {"path": "/media", "name": "Server"},
            {"path": "/media/films", "name": "Filme"},
        ]
        self.assertEqual(
            player.playlist_location_label("/media/films/clip.mp4", directories),
            "Filme",
        )
        self.assertEqual(
            player.playlist_location_label("/media/stills/a.jpg", directories),
            "Server / stills",
        )

    def test_sibling_prefix_does_not_match(self):
        directories = [{"path": "/media/film", "name": "Filme"}]
        self.assertEqual(
            player.playlist_location_label("/media/films/clip.mp4", directories),
            "/media/films",
        )

    def test_legacy_string_entries_have_no_name(self):
        label = player.playlist_location_label("/media/films/clip.mp4", ["/media/films"])
        self.assertEqual(label, "/media/films")

    def test_missing_path(self):
        self.assertEqual(player.playlist_location_label("", []), "")
        self.assertEqual(player.playlist_location_label("clip.mp4", []), "")

    def test_short_label_uses_the_last_folder(self):
        directories = [{"path": "/media/films", "name": ""}]
        self.assertEqual(
            player.playlist_location_short("/media/films/day/clip.mp4", directories),
            "day",
        )

    def test_short_label_keeps_a_named_directory(self):
        directories = [{"path": "/media/films", "name": "Filme"}]
        self.assertEqual(
            player.playlist_location_short("/media/films/2024/day/clip.mp4", directories),
            "Filme / 2024 / day",
        )
        self.assertEqual(player.playlist_location_short("", []), "")


if __name__ == "__main__":
    unittest.main()
