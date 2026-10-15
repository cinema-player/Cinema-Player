#!/usr/bin/env python3
"""GPU detection, NVIDIA color mapping, and hwdec choice."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import cinema_player as player


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class GpuDetectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        nvidia = self.root / "card1" / "device"
        _write(nvidia / "vendor", "0x10de\n")
        _write(nvidia / "device", "0x2782\n")
        _write(
            nvidia / "uevent",
            "DRIVER=nvidia\nPCI_ID=10DE:2782\nPCI_SLOT_NAME=0000:01:00.0\n",
        )
        (self.root / "card1-HDMI-A-1").mkdir()
        amd = self.root / "card0" / "device"
        _write(amd / "vendor", "0x1002\n")
        _write(amd / "product_name", "Navi 21 [Radeon RX 6800]\n")
        _write(
            amd / "uevent",
            "DRIVER=amdgpu\nPCI_ID=1002:73BF\nPCI_SLOT_NAME=0000:0c:00.0\n",
        )
        (self.root / "card0-DP-1").mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_nvidia_connector_uses_nvdec_and_pretty_name(self):
        names = [("0000:01:00.0", "NVIDIA GeForce RTX 4070")]
        gpu = player.gpu_for_output(
            "HDMI-A-1", drm_dir=str(self.root), nvidia_names=names,
        )
        self.assertEqual(gpu.vendor, "nvidia")
        self.assertEqual(gpu.driver, "nvidia")
        self.assertEqual(gpu.card, "card1")
        self.assertEqual(player.format_gpu_label(gpu), "NVIDIA GeForce RTX 4070")
        self.assertEqual(player.hwdec_for_gpu(gpu), "auto-safe")
        self.assertEqual(player.hwdec_for_gpu(gpu, embed=True), "auto-safe")

    def test_amd_connector_uses_vaapi(self):
        gpu = player.gpu_for_output("DP-1", drm_dir=str(self.root), nvidia_names=[])
        self.assertEqual(gpu.vendor, "amd")
        self.assertEqual(gpu.driver, "amdgpu")
        self.assertEqual(player.format_gpu_label(gpu), "AMD Navi 21 [Radeon RX 6800]")
        self.assertEqual(player.hwdec_for_gpu(gpu), "auto-safe")

    def test_hdmi0_maps_onto_hdmi_a1(self):
        gpu = player.gpu_for_output("HDMI-0", drm_dir=str(self.root), nvidia_names=[])
        self.assertEqual(gpu.card, "card1")
        self.assertEqual(gpu.vendor, "nvidia")

    def test_unknown_gpu_falls_back_to_auto_safe(self):
        self.assertEqual(player.hwdec_for_gpu(player.GpuInfo()), "auto-safe")
        self.assertEqual(player.format_gpu_label(None), "")
        self.assertEqual(player.format_gpu_label(player.GpuInfo()), "")


class NvidiaColorTests(unittest.TestCase):
    def test_ycbcr444_uses_limited_range(self):
        spec = player.nvidia_output_color(player.COLOR_FMT_444)
        self.assertEqual(spec["ColorSpace"], "YCbCr444")
        self.assertEqual(spec["ColorRange"], "Limited")
        rgb = player.nvidia_output_color(player.COLOR_FMT_RGB)
        self.assertEqual(rgb["ColorSpace"], "RGB")
        self.assertEqual(rgb["ColorRange"], "Full")

    def test_parse_nvidia_colorspace(self):
        self.assertEqual(
            player.parse_nvidia_color_format("YCbCr444"), player.COLOR_FMT_444,
        )
        self.assertEqual(player.parse_nvidia_color_format("RGB"), player.COLOR_FMT_RGB)
        self.assertEqual(
            player.parse_nvidia_color_format("YCbCr422"), player.COLOR_FMT_422,
        )

    def test_settings_names_include_hdmi0(self):
        names = player.nvidia_dpy_candidates("HDMI-A-1")
        self.assertIn("HDMI-A-1", names)
        self.assertIn("HDMI-0", names)
        self.assertIn("HDMI-1", names)

    def test_lspci_and_smi_parsers(self):
        self.assertEqual(
            player.parse_nvidia_smi_gpus(
                "pci.bus_id, name\n00000000:01:00.0, NVIDIA GeForce RTX 4070\n"
            ),
            [("0000:01:00.0", "NVIDIA GeForce RTX 4070")],
        )
        self.assertEqual(
            player.parse_lspci_mm_name(
                '01:00.0 "VGA compatible controller" "NVIDIA Corporation" '
                '"GA104 [GeForce RTX 3070]" "Gigabyte"\n'
            ),
            "NVIDIA GeForce RTX 3070",
        )


class NvidiaManagerTests(unittest.TestCase):
    def test_preferred_format_on_nvidia_is_ycbcr444(self):
        manager = player.VideoOutputManager("HDMI-A-1")
        manager.get_color_info = lambda output_name=None: player.EdidColorInfo(
            formats=[player.COLOR_FMT_RGB, player.COLOR_FMT_444, player.COLOR_FMT_422],
            max_tmds_mhz=600.0,
        )
        manager.gpu_for_output = lambda output_name=None: player.GpuInfo(
            vendor="nvidia", driver="nvidia", name="GeForce RTX 4070",
        )
        self.assertEqual(
            manager.preferred_color_format(1920, 1080, 24.0),
            player.COLOR_FMT_444,
        )


if __name__ == "__main__":
    unittest.main()
