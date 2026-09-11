#!/usr/bin/env python3
"""Capture Cinema Player GUI screenshots for the operator manual.

Does not open the projector mpv instance or write user settings.
Run from the repository root with the Pixi interpreter and a working DISPLAY.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
os.chdir(ROOT)

IMAGES = os.path.join(ROOT, "manual", "images")
TESTDATA = os.path.join(ROOT, "testdata")
DISPLAY = os.environ.get("DISPLAY", ":0")


def stub_dialogs():
    import cinema_gui
    from tkinter import messagebox

    cinema_gui.save_settings = lambda _settings: None
    cinema_gui.load_settings = lambda: {
        "theme": "dark",
        "language": "en",
        "window_fullscreen": False,
        "load_last_playlist_at_start": False,
        "autosave_on_program_change": False,
    }
    cinema_gui.VideoPlayerGUI.ensure_main_output = lambda self, auto=True: False
    cinema_gui.VideoPlayerGUI._warn_if_no_beamer_output = lambda self: None
    cinema_gui.VideoPlayerGUI._restore_last_playlist = lambda self: None
    cinema_gui.VideoPlayerGUI._restart_main_output = lambda self: None
    messagebox.showwarning = lambda *args, **kwargs: None
    messagebox.showinfo = lambda *args, **kwargs: None
    messagebox.showerror = lambda *args, **kwargs: None
    messagebox.askyesno = lambda *args, **kwargs: True


def import_crop(path, x, y, width, height):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    geometry = f"{max(1, int(width))}x{max(1, int(height))}+{max(0, int(x))}+{max(0, int(y))}"
    subprocess.run(
        ["import", "-silent", "-window", "root", "-crop", geometry, "+repage", path],
        check=True,
        env={**os.environ, "DISPLAY": DISPLAY},
    )


def sync(gui, seconds=0.45):
    gui.root.update_idletasks()
    gui.root.update()
    wait_preview(seconds)


def grab_widget(widget, path, pad=10):
    widget.update_idletasks()
    import_crop(
        path,
        widget.winfo_rootx() - pad,
        widget.winfo_rooty() - pad,
        widget.winfo_width() + pad * 2,
        widget.winfo_height() + pad * 2,
    )


def grab_root(gui, path):
    sync(gui, 0.35)
    grab_widget(gui.root, path, pad=0)


def grab_window(widget, path):
    widget.update_idletasks()
    subprocess.run(
        ["import", "-silent", "-window", str(widget.winfo_id()), path],
        check=True,
        env={**os.environ, "DISPLAY": DISPLAY},
    )


def find_canvas(widget):
    if widget.winfo_class() == "Canvas":
        return widget
    for child in widget.winfo_children():
        found = find_canvas(child)
        if found:
            return found
    return None


def load_testdata(gui):
    from cinema_gui import TESTDATA_DIR, VIDEO_EXTS

    paths = [
        os.path.join(TESTDATA_DIR, name)
        for name in sorted(os.listdir(TESTDATA_DIR))
        if os.path.splitext(name)[1].lower() in VIDEO_EXTS
    ]
    gui.playlist = []
    gui.playlist_path = ""
    gui.program_state = "OFF"
    gui.program_index = 0
    gui.preview_index = None
    gui.preview_live = True
    gui.playlist_name.delete(0, "end")
    gui.playlist_name.insert(0, "testdata.pls")
    for path in paths:
        gui.add_media(path)
    if gui.playlist:
        gui.program_index = 0
        gui.on_row_click(0)
    gui.refresh_all()
    gui.root.update()


def wait_preview(seconds=1.2):
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(0.05)


def post_menu(gui, canvas, fill):
    gui._close_menus()
    menu = gui._menu(gui.root)
    fill(menu)
    gui.root.update_idletasks()
    gui._popup_menu(
        menu,
        canvas.winfo_rootx(),
        canvas.winfo_rooty() + canvas.winfo_height(),
    )
    gui.root.update()
    wait_preview(0.35)
    return menu


def grab_menu(canvas, menu, path):
    canvas.update_idletasks()
    try:
        menu.update_idletasks()
        x = min(canvas.winfo_rootx(), menu.winfo_rootx()) - 8
        y = canvas.winfo_rooty() - 8
        right = max(
            canvas.winfo_rootx() + canvas.winfo_width(),
            menu.winfo_rootx() + menu.winfo_width(),
        )
        bottom = max(
            canvas.winfo_rooty() + canvas.winfo_height(),
            menu.winfo_rooty() + menu.winfo_height(),
        )
        import_crop(path, x, y, right - x + 16, bottom - y + 16)
    except Exception:
        grab_widget(canvas.master, path, pad=4)


def set_state(gui, state):
    gui.program_state = state
    gui.refresh_all()
    sync(gui, 0.55)


def capture_language(gui, lang):
    suffix = lang
    set_state(gui, "OFF")
    grab_root(gui, os.path.join(IMAGES, f"overview-{suffix}.png"))
    grab_widget(gui.now_playing.master, os.path.join(IMAGES, f"status-off-{suffix}.png"), pad=4)
    grab_widget(gui.program_group, os.path.join(IMAGES, f"program-{suffix}.png"))
    grab_widget(gui.playlist_group, os.path.join(IMAGES, f"playlist-tools-{suffix}.png"))
    grab_widget(gui.playlist_canvas.master, os.path.join(IMAGES, f"playlist-{suffix}.png"), pad=6)
    grab_widget(gui.beamer_ok.master.master, os.path.join(IMAGES, f"beamer-{suffix}.png"))
    grab_widget(gui.preview_title.master.master, os.path.join(IMAGES, f"preview-header-{suffix}.png"))
    grab_widget(gui.preview_video.master.master, os.path.join(IMAGES, f"preview-video-{suffix}.png"))
    grab_widget(gui.preview_controls, os.path.join(IMAGES, f"preview-controls-{suffix}.png"))

    set_state(gui, "PROGRAM")
    grab_root(gui, os.path.join(IMAGES, f"overview-program-{suffix}.png"))
    grab_widget(gui.now_playing.master, os.path.join(IMAGES, f"status-program-{suffix}.png"), pad=4)
    grab_widget(gui.program_group, os.path.join(IMAGES, f"program-armed-{suffix}.png"))

    set_state(gui, "PLAYING")
    grab_root(gui, os.path.join(IMAGES, f"overview-playing-{suffix}.png"))
    grab_widget(gui.now_playing.master, os.path.join(IMAGES, f"status-playing-{suffix}.png"), pad=4)
    grab_widget(gui.program_group, os.path.join(IMAGES, f"program-playing-{suffix}.png"))

    set_state(gui, "OFF")

    post_menu(gui, gui.app_menu, gui._fill_app_menu)
    menu = gui._posted_menu
    try:
        grab_window(menu, os.path.join(IMAGES, f"menu-settings-{suffix}.png"))
    except Exception:
        grab_menu(gui.app_menu, menu, os.path.join(IMAGES, f"menu-settings-{suffix}.png"))
    gui._close_menus()
    sync(gui, 0.2)

    burger = find_canvas(gui.playlist_header)
    if burger is not None:
        post_menu(gui, burger, gui._fill_playlist_menu)
        menu = gui._posted_menu
        try:
            grab_window(menu, os.path.join(IMAGES, f"menu-playlist-{suffix}.png"))
        except Exception:
            grab_menu(burger, menu, os.path.join(IMAGES, f"menu-playlist-{suffix}.png"))
        gui._close_menus()
        sync(gui, 0.2)

    class FakeEvent:
        def __init__(self, widget):
            self.x_root = widget.winfo_rootx() + 120
            self.y_root = widget.winfo_rooty() + 28

    if gui.row_widgets:
        row = gui.row_widgets[0]["row"]
        gui.on_row_menu(0, FakeEvent(row))
        wait_preview(0.5)
        menu = gui.row_menu
        try:
            grab_window(menu, os.path.join(IMAGES, f"menu-entry-{suffix}.png"))
        except Exception:
            grab_menu(row, menu, os.path.join(IMAGES, f"menu-entry-{suffix}.png"))
        gui._close_menus()
        sync(gui, 0.2)


def main():
    os.makedirs(IMAGES, exist_ok=True)
    stub_dialogs()

    import tkinter as tk
    import cinema_gui
    from language import set_language

    root = tk.Tk()
    root.geometry("1600x900+40+40")
    gui = cinema_gui.VideoPlayerGUI(root)
    gui.window_fullscreen.set(False)
    gui._apply_window_fullscreen()
    root.attributes("-topmost", True)
    root.lift()
    root.update()
    wait_preview(0.8)
    load_testdata(gui)
    wait_preview(1.4)
    capture_language(gui, "en")

    set_language("de")
    gui.language = "de"
    gui.rebuild_gui()
    gui.idle_media.set(cinema_gui.t("idle_none"))
    gui.playlist_name.delete(0, "end")
    gui.playlist_name.insert(0, "testdata.pls")
    root.update()
    wait_preview(2.0)
    gui.start_preview_player()
    if gui.playlist:
        gui.on_row_click(0)
    gui.refresh_all()
    root.update()
    wait_preview(1.8)
    capture_language(gui, "de")

    root.attributes("-topmost", False)
    try:
        gui.preview_mpv.quit()
        gui.main_mpv.quit()
    except Exception:
        pass
    root.destroy()
    print(f"Wrote screenshots to {IMAGES}")


if __name__ == "__main__":
    main()
