# X11 MPV Video Player

Two-instance mpv video player for X11/NVIDIA.

## Features

- Main mpv instance for dedicated HDMI video output
- Second mpv instance for preview
- XRandR display mode switching
- Automatic video FPS detection with ffprobe
- Selects a matching display refresh rate
- `--geometry` for exact video window placement
- Tkinter control GUI
- Play/pause, stop, seek and volume
- Restores the original display mode on exit

## Install

The project uses a local Pixi environment with Python 3.12, Tkinter and ffmpeg.

mpv must be the distro build with X11 (the conda-forge mpv cannot open a GPU window on X11).

```bash
# Once: install Pixi (https://pixi.sh)
curl -fsSL https://pixi.sh/install.sh | bash

# In the repository root
pixi install
./scripts/fetch-mpv.sh
```

Alternatively: `sudo apt install mpv`.

`xrandr` comes from the system package `x11-xserver-utils` (already typical on Linux Mint).

## Run

From the repository root:

```bash
pixi run start
```

Or with the environment interpreter:

```bash
.venv/bin/python python/cinema_player.py
```

Set `VIDEO_OUTPUT` in `cinema_player.py` if you want to force a specific X11 output, for example:

```python
VIDEO_OUTPUT = "HDMI-1"
```

With `None`, the program automatically prefers the non-primary output.
