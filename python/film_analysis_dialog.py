"""Batch film analysis dialog: LUFS and offline subtitle generation.

All Tk operations stay on the main thread; work runs in a single background
worker. Existing loudness probe and subtitle processor are reused.
"""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from subtitle_discovery import subtitle_status
from subtitle_jobs import (ArgosTranslator, FasterWhisperRecognizer,
                           JobState, SubtitleJob, SubtitleProcessor)
from subtitle_media import audio_tracks, probe_media


def default_analysis_selection(lufs, subtitles):
    """Existing results are not selected for recomputation."""
    return {"lufs": lufs is None, "subtitles": not subtitles}


def show_film_analysis(parent, entries, *, probe_audio, find_ffmpeg,
                       on_update=None):
    """Show a list of film tasks with independently selectable operations."""
    valid = [e for e in entries if not getattr(e, "missing", False)
             and not getattr(e, "is_image", False)
             and getattr(e, "path", None) and Path(e.path).is_file()]
    if not valid:
        messagebox.showinfo("Filmanalyse", "Keine analysierbaren Filme vorhanden.", parent=parent)
        return None
    window = tk.Toplevel(parent)
    window.title("Filmanalyse – LUFS und Untertitel")
    window.geometry("920x580")
    window.transient(parent)
    outer = ttk.Frame(window, padding=12)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="Filmanalyse", font=("TkDefaultFont", 15, "bold")).pack(anchor="w")
    ttk.Label(outer, text="Vorhandene Ergebnisse werden nicht automatisch neu berechnet.").pack(anchor="w", pady=(2, 8))
    top = ttk.Frame(outer)
    top.pack(fill="x", pady=4)
    ttk.Label(top, text="Alle auswählen / abwählen:").pack(side="left", padx=(0, 8))
    rows = []
    # Initial sidecar status is cheap; embedded stream discovery is asynchronous.
    for entry in valid:
        rows.append({"entry": entry, "lufs": tk.BooleanVar(value=False),
                     "subtitles": tk.BooleanVar(value=False),
                     "subtitle_info": None, "tracks": [], "track_choice": tk.StringVar(),
                     "status": tk.StringVar(value="Prüfung…")})
    def toggle_all(key):
        target = not all(row[key].get() for row in rows)
        for row in rows:
            row[key].set(target)
    ttk.Button(top, text="LUFS: alle", command=lambda: toggle_all("lufs")).pack(side="left", padx=4)
    ttk.Button(top, text="Untertitel: alle", command=lambda: toggle_all("subtitles")).pack(side="left", padx=4)
    columns = ttk.Frame(outer)
    columns.pack(fill="x", pady=(6, 0))
    columns.columnconfigure(0, weight=1)
    ttk.Label(columns, text="Film").grid(row=0, column=0, sticky="w")
    ttk.Label(columns, text="LUFS", width=8).grid(row=0, column=1)
    ttk.Label(columns, text="Untertitel", width=12).grid(row=0, column=2)
    ttk.Label(columns, text="Vorhandene Daten / Status", width=32).grid(row=0, column=3, sticky="w")
    list_holder = ttk.Frame(outer)
    list_holder.pack(fill="both", expand=True)
    canvas = tk.Canvas(list_holder, highlightthickness=0)
    scrollbar = ttk.Scrollbar(list_holder, orient="vertical", command=canvas.yview)
    list_frame = ttk.Frame(canvas)
    list_frame.columnconfigure(0, weight=1)
    list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=list_frame, anchor="nw", tags="content")
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure("content", width=e.width))
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    for index, row in enumerate(rows):
        entry = row["entry"]
        ttk.Label(list_frame, text=Path(entry.path).name).grid(row=index, column=0, sticky="w", padx=4, pady=4)
        ttk.Checkbutton(list_frame, variable=row["lufs"]).grid(row=index, column=1)
        ttk.Checkbutton(list_frame, variable=row["subtitles"]).grid(row=index, column=2)
        ttk.Label(list_frame, textvariable=row["status"], width=32).grid(
            row=index, column=3, sticky="w", padx=8)
    # Bottom controls are outside the scrolling list.
    footer = ttk.Frame(outer, padding=(0, 8, 0, 4))
    footer.pack(side="bottom", fill="x")
    ttk.Label(footer, text="Lokales faster-whisper-Modell:").pack(side="left")
    model_path = tk.StringVar()
    ttk.Entry(footer, textvariable=model_path, width=30).pack(side="left", padx=6)
    overall = tk.StringVar(value="Filme werden geprüft…")
    ttk.Label(footer, textvariable=overall).pack(side="left", padx=8)
    controls = ttk.Frame(outer, padding=(0, 0, 0, 8))
    controls.pack(side="bottom", fill="x")
    events = queue.SimpleQueue()
    stopped = threading.Event()
    running = {"value": False}
    ready = {"value": False}

    def scan():
        for index, row in enumerate(rows):
            if stopped.is_set():
                return
            try:
                status = subtitle_status(row["entry"].path)
                tracks = audio_tracks(probe_media(row["entry"].path))
                events.put(("scan", index, status, tracks))
            except Exception as exc:
                events.put(("scan_error", index, str(exc)))
        events.put(("ready",))

    def start():
        if not ready["value"] or running["value"]:
            return
        tasks = [(i, row["lufs"].get(), row["subtitles"].get())
                 for i, row in enumerate(rows) if row["lufs"].get() or row["subtitles"].get()]
        if not tasks:
            messagebox.showinfo("Filmanalyse", "Keine Funktionen ausgewählt.", parent=window)
            return
        if any(sub for _, _, sub in tasks) and not Path(model_path.get()).is_dir():
            messagebox.showerror("Filmanalyse", "Für Untertitel bitte ein lokales faster-whisper-Modellverzeichnis angeben.", parent=window)
            return
        for i, _, sub in tasks:
            if sub and not rows[i]["tracks"]:
                messagebox.showerror("Filmanalyse", f"Keine Audiospur für {Path(rows[i]['entry'].path).name} verfügbar.", parent=window)
                return
        selected_model = model_path.get()
        selected_tracks = {i: row["track_choice"].get() for i, row in enumerate(rows)}
        running["value"] = True
        start_button.configure(state="disabled")
        def work():
            ffmpeg = None
            processor = None
            for i, do_lufs, do_subs in tasks:
                if stopped.is_set():
                    break
                entry = rows[i]["entry"]
                events.put(("working", i))
                if do_lufs:
                    try:
                        if ffmpeg is None:
                            ffmpeg = find_ffmpeg()
                        lufs, envelope = probe_audio(entry.path, ffmpeg)
                        events.put(("lufs", i, lufs, envelope))
                    except Exception as exc:
                        events.put(("error", i, "LUFS: " + str(exc)))
                if do_subs and not stopped.is_set():
                    try:
                        if processor is None:
                            processor = SubtitleProcessor(
                                FasterWhisperRecognizer(selected_model), ArgosTranslator())
                        # Use explicitly selected audio track (default: first track).
                        track_index = selected_tracks[i]
                        job = SubtitleJob(Path(entry.path), int(track_index),
                                          Path(entry.path).parent)
                        active_job["value"] = job
                        processor.run(job)
                        active_job["value"] = None
                        if job.state == JobState.COMPLETED:
                            events.put(("subtitles_done", i))
                        else:
                            events.put(("error", i, "Untertitel: " + (job.error or job.state.value)))
                    except Exception as exc:
                        events.put(("error", i, "Untertitel: " + str(exc)))
            events.put(("done",))
        threading.Thread(target=work, daemon=True).start()

    active_job = {"value": None}
    def cancel():
        stopped.set()
        if active_job["value"] is not None:
            active_job["value"].cancel()
        if not running["value"]:
            window.destroy()
        else:
            overall.set("Abbruch angefordert – laufende LUFS-Analyse endet regulär.")

    start_button = ttk.Button(controls, text="Ausgewählte Analysen starten", command=start, state="disabled")
    start_button.pack(side="left")
    ttk.Button(controls, text="Abbrechen / Schließen", command=cancel).pack(side="right")

    def poll():
        if not window.winfo_exists():
            return
        while not events.empty():
            event = events.get_nowait()
            kind = event[0]
            if kind == "scan":
                _, i, status, tracks = event
                row = rows[i]
                row["subtitle_info"] = status
                row["tracks"] = tracks
                row["track_choice"].set(str(tracks[0].stream_index) if tracks else "")
                selection = default_analysis_selection(
                    getattr(row["entry"], "loudness_lufs", None),
                    status["original"] or status["generated"])
                row["lufs"].set(selection["lufs"])
                row["subtitles"].set(selection["subtitles"] and bool(tracks))
                found = []
                if getattr(row["entry"], "loudness_lufs", None) is not None:
                    found.append("LUFS vorhanden")
                if status["original"]:
                    found.append("UT Original")
                if status["generated"]:
                    found.append("UT KI")
                row["status"].set(", ".join(found) or "Keine Analyse")
                # A per-film selector is accessible via the row's subtitle checkbox tooltip-less menu.
                if len(tracks) > 1:
                    choice = ttk.Combobox(list_frame, textvariable=row["track_choice"],
                                          values=[str(t.stream_index) for t in tracks],
                                          state="readonly", width=4)
                    choice.grid(row=i, column=4, padx=4)
            elif kind == "scan_error":
                rows[event[1]]["status"].set("Prüffehler: " + event[2][:40])
            elif kind == "ready":
                ready["value"] = True
                overall.set(f"{len(rows)} Filme")
                start_button.configure(state="normal")
            elif kind == "working":
                overall.set(f"Analysiere {event[1]+1}/{len(rows)}")
                rows[event[1]]["status"].set("Wird analysiert…")
            elif kind == "lufs":
                _, i, value, envelope = event
                rows[i]["entry"].loudness_lufs = value
                rows[i]["entry"].audio_envelope = envelope
                rows[i]["lufs"].set(False)
                if on_update:
                    on_update()
                rows[i]["status"].set("LUFS berechnet")
            elif kind == "subtitles_done":
                rows[event[1]]["subtitles"].set(False)
                rows[event[1]]["status"].set("Untertitel erzeugt")
                if on_update:
                    on_update()
            elif kind == "error":
                rows[event[1]]["status"].set(event[2][:80])
            elif kind == "done":
                running["value"] = False
                start_button.configure(state="normal")
                overall.set("Analyse beendet" if not stopped.is_set() else "Abgebrochen")
        window.after(150, poll)

    threading.Thread(target=scan, daemon=True).start()
    window.after(150, poll)
    window.protocol("WM_DELETE_WINDOW", cancel)
    return window
