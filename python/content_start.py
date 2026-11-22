"""Detect first audible sound and first non-black picture using FFmpeg.

The detection is heuristic: audible = above silence threshold; picture =
above black threshold. A non-black or audible opening starts at t=0.
"""
from __future__ import annotations

import re
import subprocess
import threading

SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")
BLACK_START = re.compile(r"black_start:\s*([0-9.]+)")
BLACK_END = re.compile(r"black_end:\s*([0-9.]+)")


class StartDetectionCancelled(Exception):
    pass


def parse_audio_start(log):
    """Return first audible time, or 0 when the audio is audible from the start.

    None denotes an entirely silent scan window.
    """
    starts_silent = bool(re.search(r"silence_start:\s*0(?:\.0+)?(?:\s|$)", log))
    if not starts_silent:
        return 0.0
    match = SILENCE_END.search(log)
    return float(match.group(1)) if match else None


def parse_picture_start(log):
    """Return first non-black time; None if picture stays black throughout."""
    match = BLACK_START.search(log)
    if match and float(match.group(1)) <= 0.05:
        end = BLACK_END.search(log)
        return float(end.group(1)) if end else None
    return 0.0


def calculate_in_point(audio_start, picture_start, lead_seconds):
    """Earliest detected content minus lead, never before zero."""
    if lead_seconds < 0:
        raise ValueError("Vorlauf darf nicht negativ sein")
    starts = [value for value in (audio_start, picture_start) if value is not None]
    return max(0.0, min(starts) - lead_seconds) if starts else None


def _run_probe(command, cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise StartDetectionCancelled()
    proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, errors="replace")
    cancelled = threading.Event()
    finished = threading.Event()
    def watch():
        if cancel_event is None:
            return
        while not finished.wait(0.1):
            if cancel_event.is_set():
                cancelled.set()
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                return
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        _out, log = proc.communicate()
    finally:
        finished.set()
        thread.join(timeout=0.5)
    if cancelled.is_set() or (cancel_event is not None and cancel_event.is_set()):
        raise StartDetectionCancelled()
    if proc.returncode:
        raise RuntimeError((log or "").strip()[-400:] or "FFmpeg-Analyse fehlgeschlagen")
    return log or ""


def detect_content_start(path, ffmpeg, *, scan_seconds=120.0, lead_seconds=1.0,
                         silence_db=-45.0, black_threshold=0.10,
                         cancel_event=None):
    """Return (audio_start, picture_start, in_point).

    Scans at most scan_seconds to avoid decoding an entire feature film.
    Missing content in that window is represented by None. The first
    detectable sound or picture determines the In-point.
    """
    if scan_seconds <= 0:
        raise ValueError("Suchdauer muss positiv sein")
    base = [ffmpeg, "-hide_banner", "-nostats", "-t", str(float(scan_seconds)),
            "-i", str(path)]
    audio = _run_probe(base + ["-map", "0:a:0?", "-vn", "-sn", "-dn",
        "-af", f"silencedetect=noise={float(silence_db)}dB:d=0.15",
        "-f", "null", "-"], cancel_event)
    picture = _run_probe(base + ["-map", "0:v:0?", "-an", "-sn", "-dn",
        "-vf", f"blackdetect=d=0.05:pix_th={float(black_threshold)}",
        "-f", "null", "-"], cancel_event)
    audio_start = parse_audio_start(audio) if "Stream #0" in audio else None
    picture_start = parse_picture_start(picture) if "Stream #0" in picture else None
    return audio_start, picture_start, calculate_in_point(audio_start, picture_start, lead_seconds)


def parse_audio_end(log, window_start, duration):
    """Absolute start of trailing silence, or duration if audio stays audible."""
    starts = [float(x) for x in re.findall(r"silence_start:\\s*([0-9.]+)", log)]
    ends = [float(x) for x in SILENCE_END.findall(log)]
    if not starts or (ends and ends[-1] >= starts[-1]):
        return duration
    # FFmpeg timestamps with -ss before -i are normally reset to zero.
    return min(duration, window_start + starts[-1])


def parse_picture_end(log, window_start, duration):
    """Absolute start of trailing black, or duration if picture stays visible."""
    starts = [float(x) for x in BLACK_START.findall(log)]
    ends = [float(x) for x in BLACK_END.findall(log)]
    if not starts or (ends and ends[-1] >= starts[-1]):
        return duration
    return min(duration, window_start + starts[-1])


def calculate_out_point(audio_end, picture_end, duration, tail_seconds):
    """Later of the two ends plus tail, clamped to media duration."""
    if tail_seconds < 0:
        raise ValueError("Nachlauf darf nicht negativ sein")
    ends = [value for value in (audio_end, picture_end) if value is not None]
    return min(duration, max(ends) + tail_seconds) if ends else None


def detect_content_end(path, ffmpeg, *, duration, scan_seconds=120.0,
                       tail_seconds=1.0, silence_db=-45.0,
                       black_threshold=0.10, cancel_event=None):
    """Return (audio_end, picture_end, out_point) from final scan window."""
    if duration <= 0 or scan_seconds <= 0:
        raise ValueError("Gültige Filmdauer und Suchdauer erforderlich")
    offset = max(0.0, duration - scan_seconds)
    length = duration - offset
    base = [ffmpeg, "-hide_banner", "-nostats", "-ss", str(offset),
            "-i", str(path), "-t", str(length)]
    audio_log = _run_probe(base + ["-map", "0:a:0?", "-vn", "-sn", "-dn",
        "-af", f"silencedetect=noise={float(silence_db)}dB:d=0.15",
        "-f", "null", "-"], cancel_event)
    picture_log = _run_probe(base + ["-map", "0:v:0?", "-an", "-sn", "-dn",
        "-vf", f"blackdetect=d=0.05:pix_th={float(black_threshold)}",
        "-f", "null", "-"], cancel_event)
    audio_end = parse_audio_end(audio_log, offset, duration) if "Stream #0" in audio_log else None
    picture_end = parse_picture_end(picture_log, offset, duration) if "Stream #0" in picture_log else None
    return audio_end, picture_end, calculate_out_point(
        audio_end, picture_end, duration, tail_seconds)
