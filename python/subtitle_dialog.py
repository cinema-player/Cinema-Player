"""Tkinter dialog to start offline German subtitle generation for a playlist film."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from subtitle_media import audio_tracks, probe_media
from subtitle_jobs import (ArgosTranslator, FasterWhisperRecognizer,
                           SubtitleJob, SubtitleProcessor)


def show_subtitle_generation(parent, video_path, on_finished=None):
    """Choose an audio stream manually, then start a cancellable worker job.

    Models must already be installed locally. UI callbacks are marshalled onto
    Tk's main thread using root.after.
    """
    try:
        tracks = audio_tracks(probe_media(video_path))
    except Exception as exc:
        messagebox.showerror("Untertitel", str(exc), parent=parent)
        return None
    if not tracks:
        messagebox.showwarning("Untertitel", "Keine Audiospur gefunden.", parent=parent)
        return None
    window = tk.Toplevel(parent)
    window.title("Deutsche Untertitel erzeugen")
    window.transient(parent)
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=Path(video_path).name).pack(anchor="w", pady=(0, 8))
    choices = [f"{t.stream_index}: {t.language or 'unbekannt'} · {t.title or t.codec} · {t.channels or '?'} Kanäle" for t in tracks]
    selected = tk.StringVar(value=choices[0])
    ttk.Label(frame, text="Audiospur").pack(anchor="w")
    combo = ttk.Combobox(frame, state="readonly", textvariable=selected,
                         values=choices, width=58)
    combo.pack(fill="x", pady=(0, 8))
    ttk.Label(frame, text="Lokales faster-whisper-Modell (Verzeichnis)").pack(anchor="w")
    model = tk.StringVar()
    ttk.Entry(frame, textvariable=model, width=60).pack(fill="x", pady=(0, 8))
    status = tk.StringVar(value="Modelle müssen lokal installiert sein; keine Downloads.")
    ttk.Label(frame, textvariable=status, wraplength=440).pack(anchor="w")
    progress = ttk.Progressbar(frame, maximum=100, length=440)
    progress.pack(fill="x", pady=8)
    buttons = ttk.Frame(frame)
    buttons.pack(anchor="e")
    active = {"job": None}

    def update(job):
        if not window.winfo_exists():
            return
        progress["value"] = int(job.progress * 100)
        status.set(f"{job.state.value}: {job.error or ''}")
        if job.state.value in ("completed", "failed", "cancelled"):
            start_button.configure(state="normal")
            if job.state.value == "completed" and on_finished:
                on_finished()

    def start():
        if not model.get().strip() or not Path(model.get().strip()).is_dir():
            messagebox.showerror("Untertitel", "Bitte ein vorhandenes lokales Modellverzeichnis angeben.", parent=window)
            return
        track = tracks[choices.index(selected.get())]
        job = SubtitleJob(Path(video_path), track.stream_index, Path(video_path).parent)
        active["job"] = job
        start_button.configure(state="disabled")
        # Queue worker notifications; never call Tk from the worker.
        import queue
        events = queue.SimpleQueue()
        processor = SubtitleProcessor(FasterWhisperRecognizer(model.get().strip()), ArgosTranslator())
        processor.start(job, lambda item: events.put((item.state.value, item.progress, item.error)))
        def poll():
            if not window.winfo_exists():
                return
            while not events.empty():
                state, value, error = events.get_nowait()
                progress["value"] = int(value * 100)
                status.set(f"{state}: {error or ''}")
                if state in ("completed", "failed", "cancelled"):
                    start_button.configure(state="normal")
                    if state == "completed" and on_finished:
                        on_finished()
                    return
            window.after(150, poll)
        poll()

    def close():
        if active["job"] is not None:
            active["job"].cancel()
        window.destroy()

    start_button = ttk.Button(buttons, text="Erzeugen", command=start)
    start_button.pack(side="left", padx=4)
    ttk.Button(buttons, text="Abbrechen / Schließen", command=close).pack(side="left")
    window.protocol("WM_DELETE_WINDOW", close)
    return window
