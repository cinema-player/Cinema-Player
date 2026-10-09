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


MOUNTS = "\n".join([
    "sysfs /sys sysfs rw 0 0",
    "/dev/nvme0n1p2 / ext4 rw 0 0",
    "/dev/nvme0n1p1 /boot/efi vfat rw 0 0",
    "/dev/sda1 /home ext4 rw 0 0",
    "tmpfs /run tmpfs rw 0 0",
    "/dev/sdb1 /run/media/booth/KINGSTON\\040STICK vfat rw 0 0",
    "/dev/sdc1 /mnt/backup ext4 rw 0 0",
    "/dev/sdd1 /mnt/archive ext4 rw 0 0",
    "/dev/loop3 /snap/core/123 squashfs ro 0 0",
    "/dev/mmcblk1p1 /run/media/booth/SDCARD vfat rw 0 0",
    "/dev/sde1 /media/booth/CAMERA vfat rw 0 0",
    "/dev/sdf1 /media/booth/CAMERA vfat rw 0 0",
])

DISKS = {
    "nvme0n1": {"removable": False},
    "sda": {"removable": False},
    "sdb": {"removable": True},
    "sdc": {"removable": False, "usb": True},
    "sdd": {"removable": False},
    "mmcblk1": {"removable": True},
    "sde": {"removable": False},
    "sdf": {"removable": False},
}


class RemovableVolumeTests(unittest.TestCase):
    def volumes(self, mounts=MOUNTS, **kwargs):
        options = {"sys_block": DISKS, "isdir": lambda _path: True, "labels": {}}
        options.update(kwargs)
        return player.list_removable_volumes(mounts, **options)

    def test_lists_sticks_usb_disks_and_udisks_mounts(self):
        found = {item["path"]: item["name"] for item in self.volumes()}
        self.assertEqual(found, {
            "/run/media/booth/KINGSTON STICK": "KINGSTON STICK",
            "/mnt/backup": "backup",
            "/run/media/booth/SDCARD": "SDCARD",
            "/media/booth/CAMERA": "CAMERA",
        })

    def test_skips_unmounted_paths(self):
        found = self.volumes(isdir=lambda path: path.endswith("SDCARD"))
        self.assertEqual([item["path"] for item in found], ["/run/media/booth/SDCARD"])

    def test_partition_name_uses_the_base_disk(self):
        mounts = "/dev/nvme0n1p3 /mnt/nvme vfat rw 0 0\n"
        hidden = self.volumes(mounts, sys_block={"nvme0n1p3": {"removable": True}})
        self.assertEqual(hidden, [])
        shown = self.volumes(mounts, sys_block={"nvme0n1": {"removable": True}})
        self.assertEqual(shown[0]["path"], "/mnt/nvme")

    def test_by_label_wins_over_the_folder_name(self):
        found = self.volumes(labels={"sdb1": "Show Stick"})
        names = {item["path"]: item["name"] for item in found}
        self.assertEqual(names["/run/media/booth/KINGSTON STICK"], "Show Stick")

    def test_system_mounts_stay_hidden_even_if_marked_removable(self):
        mounts = "/dev/sdb1 /home ext4 rw 0 0\n/dev/sdb1 /boot/efi vfat rw 0 0\n"
        self.assertEqual(self.volumes(mounts), [])

    def test_live_table_is_a_list_of_mounted_paths(self):
        for item in player.list_removable_volumes():
            self.assertTrue(os.path.isdir(item["path"]), item["path"])
            self.assertNotIn(item["path"], {"/", "/home", "/boot", "/boot/efi"})
            self.assertTrue(item["name"])


class MergeImportDirectoriesTests(unittest.TestCase):
    def test_saved_drive_is_marked_and_not_repeated(self):
        stick = "/run/media/booth/KINGSTON STICK"
        rows = player.merge_import_directories(
            [
                {"path": "/data/films", "name": "Filme"},
                {"path": stick, "name": "Stick"},
            ],
            player.list_removable_volumes(
                MOUNTS, sys_block=DISKS, isdir=lambda _path: True, labels={},
            ),
        )
        self.assertEqual(
            [(row["path"], row["name"], row["removable"]) for row in rows],
            [
                ("/data/films", "Filme", False),
                (stick, "Stick", True),
                ("/mnt/backup", "backup", True),
                ("/media/booth/CAMERA", "CAMERA", True),
                ("/run/media/booth/SDCARD", "SDCARD", True),
            ],
        )

    def test_drives_alone_still_open_a_choice_list(self):
        rows = player.merge_import_directories([], [{"path": "/mnt/backup", "name": "backup"}])
        self.assertEqual(rows, [{"path": "/mnt/backup", "name": "backup", "removable": True}])

    def test_drive_strings_are_in_both_languages(self):
        import language
        self.assertEqual(set(language.STRINGS["en"]), set(language.STRINGS["de"]))
        self.assertIn("Plugged-in", language.STRINGS["en"]["media_directories_drives"])
        self.assertIn("Wechseldatenträger", language.STRINGS["de"]["media_directories_drives"])


if __name__ == "__main__":
    unittest.main()
