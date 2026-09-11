#!/usr/bin/env python3
"""Capture Cinema Player GUI screenshots for the operator manual.

Does not open the projector mpv instance or write user settings.
Run from the repository root with the Pixi interpreter and a working DISPLAY.
"""

from __future__ import annotations

import ctypes
import ctypes.util
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

_X11 = None
_XDISPLAY = None


class _XWinAttr(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("border_width", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("visual", ctypes.c_void_p),
        ("root", ctypes.c_ulong),
        ("class", ctypes.c_int),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("map_installed", ctypes.c_int),
        ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long),
        ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("screen", ctypes.c_void_p),
    ]


class _XImage(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("xoffset", ctypes.c_int),
        ("format", ctypes.c_int),
        ("data", ctypes.c_void_p),
        ("byte_order", ctypes.c_int),
        ("bitmap_unit", ctypes.c_int),
        ("bitmap_bit_order", ctypes.c_int),
        ("bitmap_pad", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("bytes_per_line", ctypes.c_int),
        ("bits_per_pixel", ctypes.c_int),
        ("red_mask", ctypes.c_ulong),
        ("green_mask", ctypes.c_ulong),
        ("blue_mask", ctypes.c_ulong),
        ("obdata", ctypes.c_void_p),
        ("f", ctypes.c_void_p * 8),
    ]


def _x11():
    global _X11, _XDISPLAY
    if _X11 is None:
        lib = ctypes.CDLL(ctypes.util.find_library("X11"))
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XGetWindowAttributes.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
        ]
        lib.XCreatePixmap.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ]
        lib.XCreatePixmap.restype = ctypes.c_ulong
        lib.XCreateGC.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
        ]
        lib.XCreateGC.restype = ctypes.c_void_p
        lib.XSetSubwindowMode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        lib.XCopyArea.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int,
        ]
        lib.XGetImage.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int,
        ]
        lib.XGetImage.restype = ctypes.c_void_p
        lib.XDestroyImage.argtypes = [ctypes.c_void_p]
        lib.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XFreeGC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _X11 = lib
        _XDISPLAY = lib.XOpenDisplay(None)
        if not _XDISPLAY:
            raise RuntimeError("XOpenDisplay failed")
    return _X11, _XDISPLAY


def capture_x11_window(xid, path):
    """Grab a Tk/X11 window including children (needed on GNOME Wayland)."""
    x11, dpy = _x11()
    attr = _XWinAttr()
    if not x11.XGetWindowAttributes(dpy, xid, ctypes.byref(attr)):
        raise RuntimeError(f"XGetWindowAttributes failed for {xid}")
    width, height, depth = attr.width, attr.height, attr.depth
    pixmap = x11.XCreatePixmap(dpy, xid, width, height, depth)
    gc = x11.XCreateGC(dpy, xid, 0, None)
    x11.XSetSubwindowMode(dpy, gc, 1)  # IncludeInferiors
    x11.XCopyArea(dpy, xid, pixmap, gc, 0, 0, width, height, 0, 0)
    x11.XSync(dpy, 0)
    image_ptr = x11.XGetImage(dpy, pixmap, 0, 0, width, height, ctypes.c_ulong(~0), 2)
    if not image_ptr:
        x11.XFreePixmap(dpy, pixmap)
        x11.XFreeGC(dpy, gc)
        raise RuntimeError(f"XGetImage failed for {xid}")
    image = ctypes.cast(image_ptr, ctypes.POINTER(_XImage)).contents
    raw = ctypes.string_at(image.data, image.bytes_per_line * image.height)
    pixfmt = "bgra" if image.bits_per_pixel == 32 else "rgb24"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pixel_format", pixfmt,
            "-video_size", f"{image.width}x{image.height}",
            "-i", "pipe:0", path,
        ],
        input=raw,
        check=True,
    )
    x11.XDestroyImage(image_ptr)
    x11.XFreePixmap(dpy, pixmap)
    x11.XFreeGC(dpy, gc)


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


def crop_png(src, path, x, y, width, height):
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", src, "-vf",
            f"crop={max(2, int(width))}:{max(2, int(height))}:{max(0, int(x))}:{max(0, int(y))}",
            path,
        ],
        check=True,
    )


def sync(gui, seconds=0.45):
    gui.root.update_idletasks()
    gui.root.update()
    wait_preview(seconds)


def grab_widget(widget, path, pad=10):
    widget.update_idletasks()
    top = widget.winfo_toplevel()
    top.update_idletasks()
    tmp = path + ".full.png"
    capture_x11_window(top.winfo_id(), tmp)
    x = widget.winfo_rootx() - top.winfo_rootx() - pad
    y = widget.winfo_rooty() - top.winfo_rooty() - pad
    width = widget.winfo_width() + pad * 2
    height = widget.winfo_height() + pad * 2
    max_w = top.winfo_width()
    max_h = top.winfo_height()
    x = max(0, x)
    y = max(0, y)
    width = min(width, max_w - x)
    height = min(height, max_h - y)
    try:
        crop_png(tmp, path, x, y, width, height)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def grab_root(gui, path):
    sync(gui, 0.35)
    capture_x11_window(gui.root.winfo_id(), path)


def grab_window(widget, path):
    widget.update_idletasks()
    capture_x11_window(widget.winfo_id(), path)


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
        gui.on_row_click(1 if len(gui.playlist) > 1 else 0)
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
    menu.update_idletasks()
    top = canvas.winfo_toplevel()
    tmp = path + ".full.png"
    capture_x11_window(top.winfo_id(), tmp)
    x0 = min(canvas.winfo_rootx(), menu.winfo_rootx()) - 8
    y0 = min(canvas.winfo_rooty(), menu.winfo_rooty()) - 8
    x1 = max(
        canvas.winfo_rootx() + canvas.winfo_width(),
        menu.winfo_rootx() + menu.winfo_width(),
    ) + 8
    y1 = max(
        canvas.winfo_rooty() + canvas.winfo_height(),
        menu.winfo_rooty() + menu.winfo_height(),
    ) + 8
    x = max(0, x0 - top.winfo_rootx())
    y = max(0, y0 - top.winfo_rooty())
    width = min(x1 - x0, top.winfo_width() - x)
    height = min(y1 - y0, top.winfo_height() - y)
    try:
        crop_png(tmp, path, x, y, width, height)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


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
        gui.on_row_click(1 if len(gui.playlist) > 1 else 0)
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
