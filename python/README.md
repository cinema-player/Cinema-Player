# Linux MPV Video Player

Two-instance mpv video player for X11 or GNOME Wayland with NVIDIA.

## Features

- Main mpv instance for dedicated HDMI video output
- Second mpv instance for preview
- Display mode switching via XRandR (X11) or GNOME gdctl (Wayland)
- Automatic video FPS detection with ffprobe
- Selects a matching display refresh rate at the video resolution
- `--geometry` / fullscreen placement for the video window
- Tkinter control GUI
- Play/pause, stop, seek and volume
- Restores the original display mode on exit

## Install

The project uses a local Pixi environment with Python 3.12, Tkinter and ffmpeg.

mpv must be the distro build (the conda-forge mpv cannot open a GPU window).

```bash
# In the repository root
./install.sh
```

This installs Pixi, the Python environment, distro `mpv`, display tools, the application icon, and a launcher. Alternatively, install Pixi yourself and run `pixi install`; then `sudo apt install mpv`.

On X11, `xrandr` comes from `x11-xserver-utils`. On GNOME Wayland, `gdctl` is part of the desktop (Mutter).

## Run

From the repository root:

```bash
pixi run start
```

Or with the environment interpreter:

```bash
.venv/bin/python python/cinema_player.py
```

Set `VIDEO_OUTPUT` in `cinema_player.py` if you want to force a specific output, for example:

```python
VIDEO_OUTPUT = "HDMI-1"
```

With `None`, the program automatically prefers the non-primary output.
