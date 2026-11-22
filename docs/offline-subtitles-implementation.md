# Offline German subtitles and projector-only notice

Status: foundation implemented; no GUI or playback integration yet.

## Playback contract

- The operator manually chooses an audio track by its absolute ffprobe stream index.
- Recognition and translation happen locally before the screening; output is a German UTF-8 SRT plus provenance metadata (actual recognition/translation tools and model versions).
- A notice is required **only when the selected, active subtitles were generated automatically**.
- The notice is played on the projector only; preview continues to reference the film, while preview UI and playlist show a notice indicator.
- The notice is not a playlist item, must not change film duration, timecode or in/out markers, and is not replayed on seek/resume.
- Before the notice, resolve the actual projector display mode and mpv color output, including HDR versus SDR tone mapping.
- Render the notice to match the film's source dimensions, exact rational frame rate and sample aspect ratio, and match the **actual output** color/HDR mode. Configure display mode once before the notice. Never switch display mode between notice and film.
- The same resolution and frame rate are necessary but not sufficient for seamless playback; verify mpv transition and HDMI signal stability on real hardware.

## Initial foundation

`python/subtitle_media.py` provides ffprobe stream extraction, stable manual audio mapping, an immutable insert profile and a predicate for whether the notice is needed.

## Next integration stages

1. Implement a persistent background subtitle job: selected-track extraction, local ASR, offline German translation, SRT output and provenance JSON. Ensure cancellation, retries and atomic final output.
2. Add the Tkinter audio-track selector and progress dialog, then playlist and preview indicators.
3. Render and cache the Cinema Player logo notice using the resolved output profile; derive the tool list from provenance metadata.
4. Integrate a projector-only pre-roll into the existing main mpv playback state machine without modifying preview mpv or user playlist.
5. Test 24000/1001, 25, 30000/1001 and 50 fps; SDR, native HDR and HDR-to-SDR; non-square pixels; multi-audio files; repeated playback; start/stop/seek; projector mode stability.

Run foundation tests from the repository root:

```sh
PYTHONPATH=python python -m unittest python/test_subtitle_media.py
```
