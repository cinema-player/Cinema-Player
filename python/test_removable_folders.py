#!/usr/bin/env python3
"""Drive icon on removable rows in the import-folder chooser."""

import os
import sys
import unittest


def _load_gui():
    tk = sys.modules.get("tkinter")
    mocked = tk is not None and not isinstance(getattr(tk, "Tk", None), type)
    if mocked:
        for name in list(sys.modules):
            if name == "tkinter" or name.startswith("tkinter.") or name in {
                "cinema_gui", "cinema_player", "font_setup",
            }:
                del sys.modules[name]
    sys.path.insert(0, os.path.dirname(__file__))
    import cinema_gui
    return cinema_gui


class ImportFolderListTests(unittest.TestCase):
    def test_removable_rows_keep_a_drive_icon(self):
        gui = _load_gui()
        root = gui.tk.Tk()
        root.withdraw()
        try:
            gui.apply_theme("dark")
            widget = gui.ImportFolderList(root)
            widget.pack()
            widget.set_items([
                {"path": "/data/films", "text": "Filme  —  /data/films", "removable": False},
                {"path": "/run/media/booth/STICK", "text": "STICK  —  /run/media/booth/STICK", "removable": True},
            ])
            widget.select(0)
            root.update_idletasks()
            self.assertFalse(widget.has_icon(0))
            self.assertTrue(widget.has_icon(1))
            self.assertEqual(widget.selected_path(), "/data/films")
            idle = str(widget.icon_label(1).cget("image"))
            self.assertEqual(idle, str(widget._icon_idle))
            widget.select(1)
            root.update_idletasks()
            selected = str(widget.icon_label(1).cget("image"))
            self.assertEqual(selected, str(widget._icon_selected))
            self.assertNotEqual(selected, idle)
            self.assertEqual(widget.selected_path(), "/run/media/booth/STICK")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
