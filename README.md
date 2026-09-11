# Cinema Player

The Cinema Player is designed to play videos on a projector in a small private cinema. It uses two outputs (HDMI, DVI, or DisplayPort) from a dedicated graphics card to separate the video output from the control interface.

The aim is to provide the audience with a high-quality cinema experience, free from distracting text or OSD elements on the big screen, while offering the projectionist an intuitive yet powerful user interface.

The video output displays only the video image. When no playback is active, the screen remains black. The control screen displays a playlist containing the program, which can include videos and images, as well as playback controls. A preview window allows the projectionist to monitor the video being played, preview videos, and edit the playlist.

Two mpv instances run in parallel: one on the projector output, and one embedded in the control window for preview. Subtitles stay off unless a track is chosen for a clip.

# Function

## Controller

The header shows the Cinema Player logo and a settings menu. The rest of the window is split into two columns.

**Left**

- A status bar with the program state (**OFF** / **PROGRAM** / **PLAYING**), the current clip name, and the playlist position.
- The program block: progress bar, volume, In/Out times, transport buttons, the four clocks, and a VU meter.
- Playlist tools (name, import/new/load/save, global settings).
- The playlist itself.

**Right**

- Beamer status: current resolution, refresh rate, aspect, and the resolutions and rates the projector currently reports.
- Preview header with the Live/Preview badge and clip metadata.
- Clip settings (autoplay, audio, subtitles, or still display time).
- Preview video with a VU meter and optional integrated LUFS readout.
- Preview transport, volume, and In/Out marks.

In **OFF**, the status title reads as program not started and the program clocks show `--:--`. Transport buttons that cannot be used in the current state are shown disabled.

The window can be switched to fullscreen on the control monitor (**F11** or Settings → Fullscreen). Cinema Player can only be quit, or the window closed, while the program is **OFF**.

## Settings

The burger menu in the header covers booth setup:

- Light or dark design
- Fullscreen on the control monitor
- Language (English / Deutsch)
- Beamer output (the connector used for the projector; cannot be changed while **PLAYING**)
- Beamer test image (Cinema Player logo on the projector; only while **OFF**)
- Load the videos from `testdata`
- Quit

If only one display is connected at startup, a warning asks the projectionist to attach a second output and select it under **Beamer output**.

## Playlist

The playlist is the central user interface of the player. It displays a scrollable list of the files in the order in which they will be played. Videos, images, or entire directories can be added to the list. The position of an entry in the list can be changed by dragging it.

Missing files stay in the list and are marked. They are skipped during the program. An entry can be relinked from its context menu.

The playlist menu offers:

- Check video files
- Reset played
- Autosave the playlist when the program pointer changes
- Load the last playlist at start
- Analyze loudness (ffmpeg EBU R128; only while **OFF**)

### Global Settings

These settings control the behavior of the playlist.

- **Beamer change** – When the projector’s zoom is changed between 16:9 and 21:9 to fill a wide screen, this checkbox is selected. When the zoom needs to be changed, a popup window informs the projectionist when to do so. Playback starts once the successful zoom change has been confirmed.  
  When 16:9 images are displayed in 21:9 zoom mode, they are scaled to fit the vertical resolution. The same popup is used when resolution, pixel aspect, or colorspace needs attention.
- **Autoplay delay** – The number of seconds of black to wait before the next video is started automatically, and before idle media appears after a clip.
- **Idle media** – An image or video loop shown instead of a black screen **while the program is armed** (**PROGRAM**). It is never shown in **OFF**. The idle button turns green while that media is on the projector.

### Playback Controls

- **Start** – Arm the program (**OFF** → **PROGRAM**). The projector stays black, or shows idle media if one is set. No clip rolls yet.
- **Resume** – Start or continue the current clip (**PROGRAM** → **PLAYING**), or unpause / leave still.
- **Pause** – Pause playback and retain the current position. The video output is rendered black.
- **Still** – Like Pause, but displays a still image of the current video position.
- **Stop** – While **PLAYING**, end the current clip and return to **PROGRAM**. Pressed again in **PROGRAM**, end the program (**OFF**) and blank the projector.

**Pause**, **Still**, and **Stop** must be confirmed before the action is performed. Pause and Still are only available while a clip is **PLAYING**. Stop is disabled in **OFF**.

### Time Displays

When a clip is on air, four time values are shown. They follow the **clip** length and In/Out marks, not idle-media duration.

- **Total** – The length of the clip (from In to Out when marks are set).
- **Elapsed** – The time that has already been played.
- **Remaining** – The remaining playback time.
- **End** – The absolute time at which the clip will end.

In **OFF**, these clocks stay at `--:--`.

### Program and Playback

The playlist is armed by pressing **Start**. The program status changes from **OFF** (red) to **PROGRAM** (blue), and the button becomes **Resume**. Idle media, if configured, may appear after the autoplay delay.

Pressing **Resume** starts the currently selected video in the list, and the status changes to **PLAYING** (green). When a video ends, the status changes back to **PROGRAM** (blue). The next entry can be started with **Resume**, unless autoplay is set for the clip that just finished.

If the autoplay option is selected for an entry, playback automatically resumes with the next video after the autoplay delay (black). Idle media is not shown in that gap.

In **PROGRAM** mode, **Stop** ends timeline processing, and the program status changes back to **OFF**. The projector stays black; idle media is not shown.

The playback position in the playlist can be changed by clicking on a video. However, the change must be confirmed before it takes effect, to avoid confusion about the playback order. This option is disabled during video playback.

A cursor on the left side of the list shows the current position in the program. The entry is highlighted in the color corresponding to the program status.

Already played videos are grayed out.

If a video requires attention, such as a change in aspect ratio (when beamer change is enabled), a change in resolution, a different pixel aspect ratio, or a different colorspace compared with the previous video, a popup window reminds the projectionist of the necessary actions. The affected data in the playlist entries are marked in red. The program can only be resumed after this information has been confirmed.

### Media Entries

An entry in the playlist displays the filename, folder, codecs, volume, optional loudness, and technical metadata.

If no entry is selected by the projectionist, the preview window shows the data of the current entry. The preview status is set to **Live** (program color).

When an entry is selected by clicking it in the playlist, it is highlighted in dark yellow, its data is displayed in the preview, and the preview status changes to **Preview** (dark yellow).

The displayed metadata are:

- Length
- Container format
- Frame rate
- Resolution
- Video codec / bit rate
- Audio codec / bit rate
- Aspect ratio
- Pixel aspect ratio
- Colorspace (for example Rec.709 or Rec.2020 PQ)
- Color range (`limited` or `full`), only when the file records it

**Settings (all media)**

- Autoplay checkbox
- Volume (saved per entry from the preview)

**Settings (video only)**

- Audio track
- Subtitle track (off unless a track is chosen)
- Start position (In)
- End position (Out)

**Settings (image only)**

- Display time

### Entry Settings

Different options can be selected for each entry in the playlist.

- If multiple audio tracks are available, the track to be used can be selected.
- If subtitles are embedded, the desired subtitle track can be selected.
- A checkbox overrides the automatic stop behavior and automatically starts playback of the next entry.
- Volume is adjusted in preview and stored on the entry with **Save volume**.

### Images

Images can also be integrated into the playlist. They behave somewhat differently from videos because they do not have an inherent running time. A display time can be set in the settings. After this time has elapsed, playback either stops or starts the next item, depending on the settings.

If no display time is set, the image stays on screen until **Resume** is pressed, and the focus then moves to the next entry.

Playlists, including all their settings, can be saved for later use.

When an image is followed by a video the framerate of the output for the image is set to the video framerate before it is displayed. This means there is no need to renegotiate the handshake with the projector when the video starts.

### Preview

The preview displays a video in a window within the control panel. The source can be switched between the live video output being sent to the projector (**Live**) and a video from the playlist (**Preview**) by clicking the preview status.

When a playlist entry is selected, the playback position can be selected using a progress bar. A start point and an end point can be defined (buttons or **I** / **O**) to determine where the video starts and ends when it goes on air. This option is disabled while the video is on air. Preview In/Out/Clear sit beside the preview transport.

The preview meter shows program-independent audio levels. After **Analyze loudness**, integrated LUFS is shown above the meter and in the playlist row.

# Technique

## Architecture

The computer runs Linux, and the application is written in Python. The open-source video player mpv provides the high-quality video and audio output for the projector and the embedded preview. FFprobe is used to read metadata from the media files. ffmpeg is used only for optional loudness analysis.

For good performance, the graphics card must support hardware decoding of both the H.264 and H.265 codecs.

mpv is started with OSD and subtitles off. The projector instance uses `--screen-name` / `--fs-screen-name` for the selected output.

## Frame Rate

To achieve smooth, flicker-free playback, the graphics card’s refresh rate is adapted before video playback starts.

1. The video’s metadata is read.
2. The refresh rates supported by the projector are checked (shown as **Rates** in the beamer panel).
3. The output is set to the video’s frame rate or an integer multiple of it, preferring the **video resolution**.
4. If no matching mode exists, a custom xrandr mode can be created at playback time by scaling the native modeline (X11 only; GNOME Wayland is limited to EDID modes).

If the process is successful, the projector status shows **OK** (green).

If no matching refresh rate is found, the status changes to **Mismatch** (red), and the incorrect settings are highlighted in red. In this case, the video can still be displayed, but frame-dropping artifacts may occur.

This check is performed when videos are added to the playlist and when a playlist is loaded. Each entry indicates whether the video can be played correctly. Import and probe do not create custom modes; that happens when a clip is prepared for the projector.

## Audio

The audio track of the program is streamed via the HDMI output of the selected projector connector, not the desktop default. Preview audio can be listened to on a separate device. Each clip has its own volume; program and preview each have a VU meter.

## Run

The bilingual operator manual (English / Deutsch, with screenshots) is `manual/index.html`.

From the repository root:

```bash
./install.sh
./start
```

`./install.sh` installs system packages (mpv, ffmpeg, xrandr, gdctl), Pixi and the Python environment, registers the application icon, and adds a menu / Desktop launcher. `./start` uses Pixi when it is available, otherwise the local Pixi environment or `.venv`.

mpv must be the distro build (the conda-forge mpv cannot open a GPU window). On X11 the player uses `xrandr`; on GNOME Wayland it uses `gdctl`.
