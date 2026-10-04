#!/usr/bin/env python3
"""EDID color-format parsing and RGB→YCbCr preference."""

import unittest

import cinema_player as player


def _cta_edid(flags=0x30, vsdb=b"\x03\x0c\x00\x10\x00\x38\x2d", hf=None, y420_ext=False):
    """Minimal EDID with one CTA block advertising the given color bits."""
    base = bytearray(128)
    base[0:8] = bytes.fromhex("00ffffffffffff00")
    base[20] = 0x80  # digital
    base[126] = 1  # one extension
    cta = bytearray(128)
    cta[0] = 0x02
    cta[1] = 0x03
    cta[3] = flags
    payload = bytearray()
    # Video data block with one VIC so the CTA is valid-looking.
    payload.extend([0x41, 16])  # tag 2, length 1, VIC 16
    if vsdb is not None:
        payload.append(0x60 | len(vsdb))  # vendor tag 3
        payload.extend(vsdb)
    if hf is not None:
        payload.append(0x60 | len(hf))
        payload.extend(hf)
    if y420_ext:
        payload.extend([0xE2, 0x0E])  # extended tag length 2, tag 0x0E
    cta[2] = 4 + len(payload)  # dtd offset
    cta[4:4 + len(payload)] = payload
    return bytes(base + cta)


class ParseEdidColorInfoTests(unittest.TestCase):
    def test_rgb_ycbcr444_422_from_cta_flags(self):
        data = _cta_edid(flags=0x30)
        info = player.parse_edid_color_info(data)
        self.assertEqual(
            info.formats,
            [player.COLOR_FMT_RGB, player.COLOR_FMT_444, player.COLOR_FMT_422],
        )
        self.assertAlmostEqual(info.max_tmds_mhz, 225.0)

    def test_ycbcr420_from_hf_vsdb(self):
        hf = bytes([0xD8, 0x5D, 0xC4, 0x01, 120, 0x07, 0x00])
        data = _cta_edid(flags=0x10, vsdb=None, hf=hf)
        info = player.parse_edid_color_info(data)
        self.assertIn(player.COLOR_FMT_RGB, info.formats)
        self.assertIn(player.COLOR_FMT_422, info.formats)
        self.assertIn(player.COLOR_FMT_420, info.formats)
        self.assertAlmostEqual(info.max_tmds_mhz, 600.0)

    def test_ycbcr420_from_extended_block(self):
        data = _cta_edid(flags=0x00, vsdb=None, y420_ext=True)
        info = player.parse_edid_color_info(data)
        self.assertEqual(info.formats, [player.COLOR_FMT_RGB, player.COLOR_FMT_420])


class ChooseColorFormatTests(unittest.TestCase):
    def test_prefers_rgb_when_link_allows(self):
        info = player.EdidColorInfo(
            formats=[player.COLOR_FMT_RGB, player.COLOR_FMT_422, player.COLOR_FMT_420],
            max_tmds_mhz=300.0,
        )
        # 1080p50 ≈ 148 MHz with blanking — fits RGB.
        self.assertEqual(
            player.choose_color_format(1920, 1080, 50.0, info),
            player.COLOR_FMT_RGB,
        )

    def test_falls_back_to_ycbcr422_when_rgb_over_budget(self):
        info = player.EdidColorInfo(
            formats=[player.COLOR_FMT_RGB, player.COLOR_FMT_422, player.COLOR_FMT_420],
            max_tmds_mhz=200.0,
        )
        # 4K50 needs far more than 200 MHz TMDS in RGB.
        self.assertEqual(
            player.choose_color_format(3840, 2160, 50.0, info),
            player.COLOR_FMT_422,
        )

    def test_falls_back_to_ycbcr420_when_only_420_fits(self):
        info = player.EdidColorInfo(
            formats=[player.COLOR_FMT_RGB, player.COLOR_FMT_422, player.COLOR_FMT_420],
            max_tmds_mhz=300.0,
        )
        # Force a clock where even 422 (0.75x) exceeds 300 MHz but 420 (0.5x) fits.
        # 3840*2160*60*1.35/1e6 ≈ 671 MHz; *0.75≈503; *0.5≈335 — still over 300.
        # Use max_tmds=340 so only 420 fits.
        info.max_tmds_mhz = 340.0
        self.assertEqual(
            player.choose_color_format(3840, 2160, 60.0, info),
            player.COLOR_FMT_420,
        )


if __name__ == "__main__":
    unittest.main()
