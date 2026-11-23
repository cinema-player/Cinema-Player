"""Subtitle appearance settings for the Cinema Player projector MPV.

Standalone Tk dialog; can be opened from an existing GUI using
show_subtitle_settings(parent, settings_dict, save_callback, main_mpv).
Never changes the preview MPV instance.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

DEFAULT_SUBTITLE_STYLE = {
    "font": "Noto Sans",
    "font_size": 46,
    "color": "#FFFFFF",
    "border_color": "#000000",
    "border_size": 2.5,
    "shadow_offset": 0,
    "position": 92,
    "bold": False,
    "spacing": 0,
}
STYLE_PRESETS = {
    "Kino Standard": DEFAULT_SUBTITLE_STYLE,
    "Große Schrift": {**DEFAULT_SUBTITLE_STYLE, "font_size": 60},
    "Hoher Kontrast": {**DEFAULT_SUBTITLE_STYLE, "color": "#F5DF67",
                      "border_size": 3.5},
}
MPV_PROPERTIES = {
    "font": "sub-font",
    "font_size": "sub-font-size",
    "color": "sub-color",
    "border_color": "sub-border-color",
    "border_size": "sub-border-size",
    "shadow_offset": "sub-shadow-offset",
    "position": "sub-pos",
    "bold": "sub-bold",
    "spacing": "sub-spacing",
}


def normalize_subtitle_style(style):
    data = dict(DEFAULT_SUBTITLE_STYLE)
    if isinstance(style, dict):
        data.update({key: value for key, value in style.items() if key in data})
    data["font"] = str(data["font"]).strip()[:100] or DEFAULT_SUBTITLE_STYLE["font"]
    for key in ("color", "border_color"):
        value = str(data[key]).strip().upper()
        if len(value) != 7 or value[0] != "#" or any(c not in "0123456789ABCDEF" for c in value[1:]):
            raise ValueError(f"Invalid subtitle {key}: {value}")
        data[key] = value
    for key, low, high, cast in (
        ("font_size", 12, 120, int),
        ("border_size", 0, 10, float),
        ("shadow_offset", 0, 10, float),
        ("position", 0, 100, int),
        ("spacing", -10, 20, float),
    ):
        data[key] = cast(data[key])
        if not low <= data[key] <= high:
            raise ValueError(f"Invalid subtitle {key}: {data[key]}")
    data["bold"] = bool(data["bold"])
    return data


def apply_subtitle_style(main_mpv, style):
    """Apply via the existing MPVController.command() IPC method."""
    data = normalize_subtitle_style(style)
    for key, mpv_property in MPV_PROPERTIES.items():
        main_mpv.command("set_property", mpv_property, data[key])
    return data


def show_subtitle_settings(parent, settings, save_callback, main_mpv):
    """Open a modal style editor; changes take effect on projector after Apply.

    save_callback receives the complete settings dictionary and should persist
    it using the host application's existing save_settings function.
    """
    current = normalize_subtitle_style(settings.get("subtitle_style"))
    dialog = tk.Toplevel(parent)
    dialog.title("Untertitel – Darstellung")
    dialog.transient(parent)
    dialog.resizable(False, False)
    frame = ttk.Frame(dialog, padding=16)
    frame.grid(sticky="nsew")
    variables = {
        "font": tk.StringVar(value=current["font"]),
        "font_size": tk.StringVar(value=str(current["font_size"])),
        "color": tk.StringVar(value=current["color"]),
        "border_color": tk.StringVar(value=current["border_color"]),
        "border_size": tk.StringVar(value=str(current["border_size"])),
        "shadow_offset": tk.StringVar(value=str(current["shadow_offset"])),
        "position": tk.StringVar(value=str(current["position"])),
        "bold": tk.BooleanVar(value=current["bold"]),
        "spacing": tk.StringVar(value=str(current["spacing"])),
    }
    preset = tk.StringVar(value="Kino Standard")
    ttk.Label(frame, text="Profil").grid(row=0, column=0, sticky="w", pady=4)
    selector = ttk.Combobox(frame, textvariable=preset,
                            values=list(STYLE_PRESETS), state="readonly", width=24)
    selector.grid(row=0, column=1, sticky="ew", pady=4)

    def select_preset(_event=None):
        for key, value in STYLE_PRESETS[preset.get()].items():
            variables[key].set(value)

    selector.bind("<<ComboboxSelected>>", select_preset)
    labels = (
        ("font", "Schriftart"), ("font_size", "Schriftgröße"),
        ("color", "Schriftfarbe (#RRGGBB)"),
        ("border_color", "Konturfarbe (#RRGGBB)"),
        ("border_size", "Konturstärke"),
        ("shadow_offset", "Schatten"),
        ("position", "Position (0–100 %)"),
        ("spacing", "Zeilenabstand"),
    )
    for row, (key, label) in enumerate(labels, 1):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        ttk.Entry(frame, textvariable=variables[key], width=25).grid(
            row=row, column=1, sticky="ew", pady=4)
    ttk.Checkbutton(frame, text="Fett", variable=variables["bold"]).grid(
        row=9, column=1, sticky="w")
    message = tk.StringVar(value="Änderungen gelten nur für den Projektor.")
    ttk.Label(frame, textvariable=message).grid(
        row=10, column=0, columnspan=2, sticky="w", pady=(8, 4))

    def apply():
        try:
            chosen = normalize_subtitle_style({k: var.get() for k, var in variables.items()})
            apply_subtitle_style(main_mpv, chosen)
            settings["subtitle_style"] = chosen
            save_callback(settings)
        except (ValueError, TypeError, tk.TclError, OSError) as exc:
            message.set(f"Fehler: {exc}")
            return
        message.set("Untertitel-Einstellungen gespeichert.")

    buttons = ttk.Frame(frame)
    buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(12, 0))
    ttk.Button(buttons, text="Übernehmen", command=apply).pack(side="left", padx=4)
    ttk.Button(buttons, text="Schließen", command=dialog.destroy).pack(side="left")
    dialog.grab_set()
    dialog.focus_set()
    return dialog
