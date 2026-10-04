#!/usr/bin/env python3

import json
import os
import unittest
from unittest import mock

import cinema_player as player


KSCREEN_SAMPLE = {
    "outputs": [
        {
            "id": 1,
            "name": "eDP-1",
            "connected": True,
            "enabled": True,
            "priority": 1,
            "pos": {"x": 0, "y": 0},
            "scale": 1.25,
            "size": {"width": 1920, "height": 1080},
            "currentModeId": "10",
            "preferredModes": ["10"],
            "modes": [
                {
                    "id": "10",
                    "name": "1920x1080",
                    "size": {"width": 1920, "height": 1080},
                    "refreshRate": 60.0,
                },
                {
                    "id": "11",
                    "name": "1920x1080",
                    "size": {"width": 1920, "height": 1080},
                    "refreshRate": 48.002,
                },
                {
                    "id": "12",
                    "name": "1920x1080i",
                    "size": {"width": 1920, "height": 1080},
                    "refreshRate": 50.0,
                },
            ],
            "model": "Built-in",
            "vendor": "BOE",
        },
        {
            "id": 2,
            "name": "HDMI-A-1",
            "connected": True,
            "enabled": True,
            "priority": 2,
            "pos": {"x": 0, "y": 0},
            "scale": 1,
            "size": {"width": 1920, "height": 1080},
            "currentModeId": "71",
            "preferredModes": ["71"],
            "modes": [
                {
                    "id": "71",
                    "name": "1920x1080",
                    "size": {"width": 1920, "height": 1080},
                    "refreshRate": 59.94,
                },
                {
                    "id": "72",
                    "name": "1920x1080",
                    "size": {"width": 1920, "height": 1080},
                    "refreshRate": 24.0,
                },
            ],
            "model": "Cinema Projector",
            "vendor": "PJT",
        },
        {
            "id": 3,
            "name": "DP-2",
            "connected": False,
            "enabled": False,
            "priority": 0,
            "pos": {"x": 0, "y": 0},
            "modes": [],
        },
    ]
}


class ParseKscreenJsonTests(unittest.TestCase):
    def test_parses_connected_outputs_and_skips_interlaced(self):
        state = player.parse_kscreen_json(json.dumps(KSCREEN_SAMPLE))
        self.assertEqual(state.order, ["eDP-1", "HDMI-A-1"])
        self.assertEqual(
            {(mode.width, mode.height, round(mode.refresh, 2), mode.name)
             for mode in state.modes["eDP-1"]},
            {
                (1920, 1080, 60.0, "10"),
                (1920, 1080, 48.0, "11"),
            },
        )
        self.assertEqual(state.current["HDMI-A-1"].name, "71")
        self.assertAlmostEqual(state.current["HDMI-A-1"].refresh, 59.94)
        self.assertEqual(state.preferred["HDMI-A-1"].name, "71")
        self.assertEqual(state.identity["HDMI-A-1"]["product"], "Cinema Projector")

    def test_primary_and_geometry(self):
        state = player.parse_kscreen_json(json.dumps(KSCREEN_SAMPLE))
        primary = [item for item in state.logical if item.primary]
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0].connector, "eDP-1")
        self.assertEqual(primary[0].scale, "1.25")
        beamer = next(item for item in state.logical if item.connector == "HDMI-A-1")
        self.assertEqual((beamer.x, beamer.y), (0, 0))
        self.assertEqual(state.current["HDMI-A-1"].x, 0)


class KscreenApplyTests(unittest.TestCase):
    def test_kscreen_apply_builds_doctor_command(self):
        manager = player.VideoOutputManager(video_output="HDMI-A-1")
        state = player.parse_kscreen_json(json.dumps(KSCREEN_SAMPLE))
        mode = state.modes["HDMI-A-1"][1]  # 24 Hz
        with (
            mock.patch.object(manager, "uses_gdctl", return_value=False),
            mock.patch.object(manager, "uses_kscreen", return_value=True),
            mock.patch.object(manager, "wayland_state", return_value=state),
            mock.patch("cinema_player.subprocess.run") as run,
            mock.patch("cinema_player.time.sleep"),
        ):
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            manager._kscreen_apply_mode(mode)
        command = run.call_args.args[0]
        self.assertEqual(command[0], "kscreen-doctor")
        self.assertIn("output.eDP-1.mode.10", command)
        self.assertIn("output.eDP-1.position.0,0", command)
        self.assertIn("output.eDP-1.primary", command)
        self.assertIn("output.HDMI-A-1.mode.72", command)
        self.assertIn("output.HDMI-A-1.position.1920,0", command)


class WaylandBackendSelectionTests(unittest.TestCase):
    def test_kde_prefers_kscreen_even_when_gdctl_exists(self):
        manager = player.VideoOutputManager()
        sample = json.dumps(KSCREEN_SAMPLE)

        def probe(command, timeout=5):
            name = command[0]
            if name == "gdctl":
                return False, ""
            if name == "kscreen-doctor":
                return True, sample
            return False, ""

        with (
            mock.patch("cinema_player.session_is_wayland", return_value=True),
            mock.patch("cinema_player.session_desktop_hint", return_value="kde"),
            mock.patch("cinema_player.shutil.which", side_effect=lambda n: f"/usr/bin/{n}"),
            mock.patch.object(manager, "_probe", side_effect=probe),
        ):
            self.assertEqual(manager.wayland_backend(), "kscreen")
            self.assertTrue(manager.uses_kscreen())
            self.assertFalse(manager.uses_gdctl())

    def test_falls_back_when_preferred_tool_fails(self):
        manager = player.VideoOutputManager()
        sample = json.dumps(KSCREEN_SAMPLE)

        def probe(command, timeout=5):
            if command[0] == "gdctl":
                return False, "mutter not running"
            if command[0] == "kscreen-doctor":
                return True, sample
            return False, ""

        with (
            mock.patch("cinema_player.session_is_wayland", return_value=True),
            mock.patch("cinema_player.session_desktop_hint", return_value="gnome"),
            mock.patch("cinema_player.shutil.which", side_effect=lambda n: f"/usr/bin/{n}"),
            mock.patch.object(manager, "_probe", side_effect=probe),
        ):
            self.assertEqual(manager.wayland_backend(), "kscreen")

    def test_session_desktop_hint_reads_kde(self):
        with mock.patch.dict(
            os.environ,
            {
                "XDG_CURRENT_DESKTOP": "KDE",
                "XDG_SESSION_DESKTOP": "KDE",
                "DESKTOP_SESSION": "plasma",
            },
            clear=False,
        ):
            self.assertEqual(player.session_desktop_hint(), "kde")


if __name__ == "__main__":
    unittest.main()
