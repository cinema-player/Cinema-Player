#!/usr/bin/env python3
"""Media-directory names and the playlist folder line."""

import json
import os
import shutil
import sys
import tempfile
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
        self.assertEqual(language.STRINGS["de"]["import_path_mark"], "Importpfad")
        self.assertEqual(language.STRINGS["de"]["playlist_untitled"], "unbekannt.pls")
        self.assertEqual(language.STRINGS["en"]["playlist_untitled"], "untitled.pls")
        self.assertEqual(language.STRINGS["de"]["copy_files_cancel"], "Abbrechen")
        self.assertEqual(language.STRINGS["en"]["copy_files_cancel"], "Cancel")
        self.assertEqual(language.STRINGS["de"]["edit_imports"], "Importe bearbeiten")
        self.assertEqual(language.STRINGS["en"]["edit_imports"], "Edit imports")
        self.assertEqual(language.STRINGS["de"]["edit_imports_delete_media"], "Mediendateien löschen")
        self.assertEqual(language.STRINGS["en"]["edit_imports_delete_media"], "Delete media files")
        self.assertEqual(language.STRINGS["de"]["playlist_library"], "Playlist wählen")
        self.assertEqual(language.STRINGS["de"]["playlist_with_media"], "Mit Mediendateien")
        self.assertEqual(language.STRINGS["de"]["still_dim"], "Dimmen")
        self.assertEqual(language.STRINGS["en"]["still_dim"], "Dim")
        self.assertEqual(language.STRINGS["de"]["still_dim_time"], "Dimmzeit:")
        self.assertEqual(language.STRINGS["en"]["still_dim_time"], "Dim time:")


class ImportFolderEditTests(unittest.TestCase):
    def test_counts_videos_and_keeps_the_playlist_when_videos_go(self):
        root = tempfile.mkdtemp()
        try:
            evening = os.path.join(root, "Abend")
            os.makedirs(os.path.join(evening, "nested"))
            payloads = {
                os.path.join(evening, "one.mp4"): b"1234",
                os.path.join(evening, "nested", "two.mkv"): b"12345678",
                os.path.join(evening, "still.jpg"): b"ab",
                os.path.join(evening, "Abend.pls"): b"[]",
                os.path.join(root, "loose.mp4"): b"nope",
            }
            for path, data in payloads.items():
                with open(path, "wb") as handle:
                    handle.write(data)
            os.makedirs(os.path.join(root, ".hidden"))
            rows = player.import_folder_rows(root)
            self.assertEqual([row["name"] for row in rows], ["Abend"])
            self.assertEqual(rows[0]["videos"], 2)
            self.assertEqual(rows[0]["bytes"], 16)
            self.assertEqual(rows[0]["media"], 3)
            self.assertEqual(player.delete_import_media(evening), 3)
            self.assertFalse(os.path.exists(os.path.join(evening, "one.mp4")))
            self.assertFalse(os.path.exists(os.path.join(evening, "nested")))
            self.assertTrue(os.path.isfile(os.path.join(evening, "Abend.pls")))
            self.assertFalse(os.path.exists(os.path.join(evening, "still.jpg")))
            self.assertTrue(os.path.isfile(os.path.join(root, "loose.mp4")))
            self.assertFalse(player.delete_import_directory(root, root))
            self.assertFalse(player.delete_import_directory(os.path.join(evening, "nested"), root))
            self.assertTrue(os.path.isdir(evening))
            self.assertTrue(player.delete_import_directory(evening, root))
            self.assertFalse(os.path.exists(evening))
            self.assertTrue(os.path.isfile(os.path.join(root, "loose.mp4")))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class PlaylistLibraryTests(unittest.TestCase):
    def test_only_playlist_folders_are_listed_and_media_is_optional(self):
        root = tempfile.mkdtemp()
        try:
            evening = os.path.join(root, "Abend")
            os.makedirs(evening)
            clip = os.path.join(evening, "clip.mp4")
            with open(clip, "wb") as handle:
                handle.write(b"film")
            source = os.path.join(evening, "Abend.pls")
            with open(source, "w", encoding="utf-8") as handle:
                json.dump({"entries": [{"path": clip, "filename": "clip.mp4"}]}, handle)
            os.makedirs(os.path.join(root, "loose"))
            with open(os.path.join(root, "loose", "note.txt"), "w", encoding="utf-8") as handle:
                handle.write("x")
            rows = player.library_playlists(root)
            self.assertEqual([row["name"] for row in rows], ["Abend"])
            self.assertEqual(rows[0]["path"], source)

            plain = os.path.join(root, "plain-out")
            written = player.place_playlist(source, plain, "Abend", False)
            with open(written, encoding="utf-8") as handle:
                copied = json.load(handle)
            self.assertEqual(copied["entries"][0]["path"], clip)
            self.assertFalse(os.path.exists(os.path.join(plain, "clip.mp4")))

            bundled = os.path.join(root, "with-media")
            written = player.place_playlist(source, bundled, "Abend", True)
            with open(written, encoding="utf-8") as handle:
                copied = json.load(handle)
            dest_clip = os.path.join(bundled, "clip.mp4")
            self.assertEqual(copied["entries"][0]["path"], dest_clip)
            self.assertEqual(copied["entries"][0]["filename"], "clip.mp4")
            self.assertTrue(os.path.isfile(dest_clip))
            self.assertTrue(os.path.isfile(clip))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class PlaylistFolderNameTests(unittest.TestCase):
    def test_placeholders_and_blank_names_are_rejected(self):
        for name in ("", "   ", "untitled.pls", "Unbekannt.pls", "UNTITLED", "unbekannt"):
            self.assertTrue(player.playlist_name_is_placeholder(name), name)
            self.assertEqual(player.playlist_folder_name(name), "")

    def test_a_real_name_becomes_the_folder(self):
        self.assertEqual(player.playlist_folder_name("Abend.pls"), "Abend")
        self.assertEqual(player.playlist_folder_name("Abend.json"), "Abend")
        self.assertEqual(player.playlist_folder_name("  Abend  "), "Abend")
        self.assertFalse(player.playlist_name_is_placeholder("Abend.pls"))

    def test_path_segments_are_rejected(self):
        self.assertEqual(player.playlist_folder_name("../Abend.pls"), "")
        self.assertEqual(player.playlist_folder_name("Abend/Film.pls"), "")
        self.assertEqual(player.playlist_folder_name("."), "")
        self.assertEqual(player.playlist_folder_name(".."), "")


class RemovablePathTests(unittest.TestCase):
    def test_files_inside_a_volume_count_and_siblings_do_not(self):
        volumes = [{"path": "/run/media/booth/STICK", "name": "STICK"}]
        self.assertTrue(player.path_is_on_removable_volume(
            "/run/media/booth/STICK/day/clip.mp4", volumes,
        ))
        self.assertTrue(player.path_is_on_removable_volume("/run/media/booth/STICK", volumes))
        self.assertFalse(player.path_is_on_removable_volume(
            "/run/media/booth/STICK-extra/clip.mp4", volumes,
        ))
        self.assertFalse(player.path_is_on_removable_volume("/data/films/clip.mp4", volumes))
        self.assertFalse(player.path_is_on_removable_volume("", volumes))


class InstallRelativePlaylistTests(unittest.TestCase):
    def test_relative_paths_use_the_install_directory(self):
        absolute = player.resolve_install_path("/data/films/clip.mp4")
        self.assertEqual(absolute, "/data/films/clip.mp4")
        self.assertEqual(player.resolve_install_path(""), "")
        self.assertEqual(player.resolve_install_path("  "), "")
        relative = player.resolve_install_path("media/testdata/videotestdata/UHD_25fps.mp4")
        self.assertEqual(
            relative,
            os.path.join(player.ROOT_DIR, "media", "testdata", "videotestdata", "UHD_25fps.mp4"),
        )
        self.assertEqual(
            player.relativize_install_path(relative),
            "media/testdata/videotestdata/UHD_25fps.mp4",
        )
        self.assertEqual(player.relativize_install_path("/data/films/clip.mp4"), "/data/films/clip.mp4")
        shipped = os.path.join(player.ROOT_DIR, "media", "testdata", "videotestdata", "framerates.pls")
        self.assertTrue(player.path_is_in_install(shipped))
        self.assertFalse(player.path_is_in_install(os.path.join(tempfile.gettempdir(), "show.pls")))

    def test_saving_inside_the_install_tree_keeps_relative_paths(self):
        clip = os.path.join(player.ROOT_DIR, "media", "testdata", "audiosyncdata", "rec2020-test.mp4")
        idle = os.path.join(player.ROOT_DIR, "media", "idle", "AFC Idle.mp4")
        outside = "/data/films/feature.mp4"
        stored = player.playlist_for_install_file({
            "idle_media_path": idle,
            "entries": [
                {"path": clip, "filename": "rec2020-test.mp4"},
                {"path": outside, "filename": "feature.mp4"},
            ],
        })
        self.assertEqual(stored["idle_media_path"], "media/idle/AFC Idle.mp4")
        self.assertEqual(stored["entries"][0]["path"], "media/testdata/audiosyncdata/rec2020-test.mp4")
        self.assertEqual(stored["entries"][1]["path"], outside)
        loaded = player.playlist_entries(stored["entries"])
        self.assertEqual(loaded[0].path, clip)
        self.assertEqual(loaded[1].path, outside)

    def test_shipped_playlists_resolve_away_from_the_working_directory(self):
        previous = os.getcwd()
        os.chdir(tempfile.gettempdir())
        try:
            folders = [
                os.path.join(player.ROOT_DIR, "media", "testdata", "videotestdata"),
                os.path.join(player.ROOT_DIR, "media", "testdata", "audiosyncdata"),
            ]
            seen = 0
            for folder in folders:
                for name in os.listdir(folder):
                    if not name.endswith(".pls"):
                        continue
                    with open(os.path.join(folder, name), encoding="utf-8") as handle:
                        document = json.load(handle)
                    entries = player.playlist_entries(document.get("entries"))
                    self.assertTrue(entries, name)
                    for entry in entries:
                        self.assertTrue(os.path.isabs(entry.path), entry.path)
                        self.assertTrue(os.path.isfile(entry.path), entry.path)
                        self.assertTrue(entry.path.startswith(player.ROOT_DIR + os.sep), entry.path)
                        seen += 1
                    idle = player.resolve_install_path(document.get("idle_media_path") or "")
                    if idle:
                        self.assertTrue(os.path.isfile(idle), idle)
                        self.assertTrue(idle.startswith(player.ROOT_DIR + os.sep), idle)
            self.assertGreaterEqual(seen, 7)
        finally:
            os.chdir(previous)

    def test_export_finds_an_install_relative_clip(self):
        root = tempfile.mkdtemp()
        previous = os.getcwd()
        os.chdir(tempfile.gettempdir())
        try:
            clip = os.path.join(player.ROOT_DIR, "media", "testdata", "audiosyncdata", "rec2020-test.mp4")
            source = os.path.join(root, "audiosync.pls")
            with open(source, "w", encoding="utf-8") as handle:
                json.dump({
                    "entries": [{
                        "path": "media/testdata/audiosyncdata/rec2020-test.mp4",
                        "filename": "rec2020-test.mp4",
                    }],
                    "idle_media_path": "media/idle/AFC Idle.mp4",
                }, handle)
            dest = os.path.join(root, "copy")
            written = player.place_playlist(source, dest, "audiosync", True)
            with open(written, encoding="utf-8") as handle:
                copied = json.load(handle)
            dest_clip = os.path.join(dest, "rec2020-test.mp4")
            self.assertEqual(copied["entries"][0]["path"], dest_clip)
            self.assertEqual(
                copied["idle_media_path"],
                os.path.join(dest, "AFC Idle.mp4"),
            )
            self.assertTrue(os.path.isfile(dest_clip))
            self.assertTrue(os.path.isfile(os.path.join(dest, "AFC Idle.mp4")))
            self.assertTrue(os.path.isfile(clip))
        finally:
            os.chdir(previous)
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
