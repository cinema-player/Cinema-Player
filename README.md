# Cinema Player

The Cinema Player is designed to play videos on a projector in a small private cinema. It uses two outputs (HDMI, DVI, or DisplayPort) from a dedicated graphics card to separate the video output from the control interface.

The aim is to provide the audience with a high-quality cinema experience, free from distracting text or OSD elements on the big screen, while offering the projectionist an intuitive yet powerful user interface.

The video output displays only the video image. When no playback is active, the screen remains black. The control screen displays a playlist containing the program, which can include videos and images, as well as playback controls. A preview window allows the projectionist to monitor the video being played, preview videos, and edit the playlist.

Two mpv instances run in parallel: one on the projector output, and one embedded in the control window for preview. Subtitles stay off unless a track is chosen for a clip.

# Function

## Controller

The header shows the Cinema Player logo, the version, and whether the session is X11 or Wayland, plus a settings menu. The rest of the window is split into two columns.

**Left**

- A status bar with the program state (**OFF** / **PROGRAM** / **PLAYING**), the current clip name, and the playlist position.
- The program block: progress bar with live video bitrate, volume with live audio bitrate, In/Out times, transport buttons, the four clocks, and a VU meter.
- Playlist tools (name, import/new/load/save, global settings).
- The playlist itself.

**Right**

- Beamer status: aspect ratio, the rates and resolutions the projector reports, and **OK** / **Mismatch**. The active mode has a border; program values are blue, preview values yellow. **OK** means a listed rate can show the clip (including 2×, so 30 fps is OK when 60 Hz is listed, and 50/60 fps is OK at 25/30 Hz if 50/60 Hz is missing).
- Preview header with the Live/Preview badge and clip metadata.
- Clip settings (autoplay, settings warning, loop, audio, subtitles, or still display time).
- Preview video with a VU meter and optional integrated LUFS readout.
- Preview transport, volume, live bitrates, and In/Out marks.

In **OFF**, the status title reads as program not started and the program clocks show `--:--`. Transport buttons that cannot be used in the current state are shown disabled.

The window can be switched to fullscreen on the control monitor (**F11** or Settings → Fullscreen). Cinema Player can only be quit, or the window closed, while the program is **OFF**.

## Settings

The burger menu in the header covers booth setup:

- Fullscreen on the control monitor (`F11`)
- Media directories (saved folders offered when importing into the playlist)
- **Program** — Use default Idle Media (checkbox; remembered, applies the file in `idle` at startup)
- **Playlist** — check files, reset, settings warning, autosave, load last playlist, idle media, analyze loudness
- **System settings**
  - Beamer output (the connector used for the projector; cannot be changed while **PLAYING**)
  - Light or dark design
  - Language (English / Deutsch)
  - Remote control (LAN HTTP API and smartphone page; port and required token)
  - Light control (Shelly switches and dimmers on the LAN; house-light presets Bright / Medium / Dark)
- **Calibration** (in **OFF** and while already calibrating)
  - Beamer test image (Cinema Player logo on the projector; only in **OFF**)
  - Video / Audio
    - Load all files (clips from `testdata/videotestdata` or `testdata/audiosyncdata`, loop on)
    - Playlists in that folder, listed below a separator when present
- Quit

If only one display is connected at startup, a warning asks the projectionist to attach a second output and select it under **Beamer output**.

## Playlist

The playlist is the central user interface of the player. It displays a scrollable list of the files in the order in which they will be played. Videos, images, or entire directories can be added to the list. Folders saved under **Media directories** are offered when importing. If **Copy files** is enabled there, imports are copied into a chosen folder and the playlist links those copies. A popup shows copy progress. The position of an entry in the list can be changed by dragging it.

Missing files stay in the list and are marked. They are skipped during the program. An entry can be relinked from its context menu.

The playlist menu offers:

- Check video files
- Reset playlist (clears played flags and moves the program pointer to the first entry)
- **Settings warning** — when the projector’s zoom is changed between 16:9 and 21:9 to fill a wide screen, enable this. A popup then informs the projectionist when zoom, resolution, pixel aspect, or colorspace needs attention. Playback starts once the change has been confirmed. 16:9 images in 21:9 zoom are scaled to fit the vertical resolution. Affected clips show red **setting!** in the right-hand playlist column. With this on, Preview → **Settings warning** forces that confirmation on a clip even when the format does not change.
- Autosave the playlist when the program pointer changes
- Load the last playlist at start
- **Idle media** — choose the idle file and the black pause (seconds of black before the next autoplay clip and before idle media appears). **None** clears the file. Settings → **Use default Idle Media** still loads the file from `idle` at startup.
- Analyze loudness (ffmpeg EBU R128; only while **OFF**)

### Global Settings

These settings control the behavior of the playlist.

- **Dark / Medium / Bright** – Manual house-light presets. They are disabled until at least one Shelly is ticked and **House lights** is on in Settings → System settings → Light control (or on the phone).
- **Idle media name** – If an idle file is set, its name is shown here. It turns green while that media is on the projector. Choose or clear the file, and the black pause, in Settings → Playlist. When **Settings warning** is on, red **Settings warning on** appears beside it.

### Playback Controls

- **Start** – Arm the program (**OFF** → **PROGRAM**). The projector stays black, or shows idle media if one is set. No clip rolls yet.
- **Resume** – Start or continue the current clip (**PROGRAM** → **PLAYING**), or unpause / leave still.
- **Pause** – Pause playback and retain the current position. The video output is rendered black.
- **Still** – Like Pause, but displays a still image of the current video position.
- **Stop** – While **PLAYING**, end the current clip and return to **PROGRAM**. Pressed again in **PROGRAM**, end the program (**OFF**) and blank the projector. In **Video calibration** or **Audio calibration**, Stop from **PROGRAM** leaves the mode and clears the test playlist.

**Pause**, **Still**, and **Stop** must be confirmed before the action is performed. Pause and Still are only available while a clip is **PLAYING**. Stop is disabled in **OFF**.

### Remote control

Cinema Player listens on the LAN (default port **8765**) so a smartphone can run the show. Settings → **Remote control** shows a QR code (IP, port, and token) and the matching URL. Scan the code or open the URL in a phone browser. A token is required (`X-Cinema-Token` or `Authorization: Bearer`). A radio icon and a bulb sit in the header. They are coloured while remote control or house-light control is on, and grey while off. Click either icon to open its settings. A native app can use the same JSON API:

- `GET /api/status` — state, playlist, progress, clocks, volume, and which actions are available
- `GET /api/playlist` — playlist only
- `POST /api/resume` — same as **Resume** / **Start** (no booth confirmation dialogs)
- `POST /api/pause` — black pause
- `POST /api/still` — freeze the current frame
- `POST /api/stop` — end the clip on air and return to **PROGRAM** (does not end the program)
- `PUT /api/volume` — body `{"volume": 0…100}`
- `POST /api/program` — body `{"index": 0…}` sets the program pointer (not while **PLAYING**)
- `POST /api/lights` — body `{"preset": "dark"|"medium"|"bright"}` and/or `{"enabled": true|false}`

The smartphone page asks to confirm **Pause**, **Still**, and **Stop**, like the booth. Stop on the phone only ends the clip on air; it cannot stop the program. Tapping a playlist row sets the program pointer after confirmation. If a beamer settings change is required, resume returns `projection_zoom_required` until it has been confirmed on the control PC. Dark / Medium / Bright sit on the playlist tools row and above the progress bar on the phone.

### Lights

Cinema Player talks to Shelly switches and dimmers on the LAN (HTTP, no extra packages). Settings → System settings → **Light control** scans the network (mDNS when `avahi-browse` is installed, otherwise a `/24` probe) or accepts an IP address. Enter the Shelly **user** and **password** (Gen2 is `admin`); they are stored per device and used for HTTP Basic and Gen2 RPC digest. Tick the devices that should follow house-light cues. **Bright**, **Medium**, and **Dark** are dimmer percentages (defaults 100 / 40 / 0); a switch turns on above 0%. Fade is the dimmer transition in seconds.

**Dark**, **Medium**, and **Bright** sit on the playlist tools row and on the smartphone remote so the house lights can be set by hand. The chosen button blinks while the fade runs. **House lights** in Settings → System settings → Light control (and on the phone) switches the whole Shelly control off: no manual buttons, no playlist cues, no film-start or film-end fades. The choice is saved. It cannot be switched on until at least one Shelly is ticked. Launching Cinema Player sends **Bright** to every selected Shelly.

In Settings → System settings → **Light control**, **Start film** is how many seconds before the dim-down finishes the clip starts (0 waits until the fade is done). **Lights up** is how many seconds before the clip ends the house lights come up. With Autoplay to the next clip the lights stay dark.

Each playlist entry has a **Dimmer** (`Dark` default, `Medium`, `Bright`). It runs when the clip **starts** (fade and blinking buttons, then the picture). It is not used at the end: house lights come up automatically unless Autoplay continues (then they stay dark). Stop clip, the last clip, or Stop program brings the lights up. The playlist shows **MEDIUM** / **BRIGHT** when the play dimmer is not Dark. The cue is stored in the playlist file.

### Calibration

**Video** and **Audio** under **Calibration** (only while **OFF** or already calibrating) use the same mode. Each submenu offers **Load all files** (every clip in `testdata/videotestdata` or `testdata/audiosyncdata`) and, below a separator, any `.pls` playlists in that folder. The chosen list replaces the current playlist with loop on and arms the program. Idle media is not shown. The status reads **Video calibration** or **Audio calibration**. Stop from **PROGRAM** leaves the mode and clears the test playlist.

In **Audio calibration**, a delay slider under the program volume sets audio vs. video in 1 ms steps (mpv `audio-delay`); the value is stored per resolution and frame rate. **Delays** lists the stored values; **Load** / **Save** read and write them as JSON. During a normal show, the matching delay is applied and shown next to the program volume.

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

If **Loop** is set on a video, it repeats (including In/Out) until **Resume** is pressed. That ends the loop, marks the clip played, and returns to **PROGRAM** — then autoplay can start the next clip.

If the autoplay option is selected for an entry, playback automatically resumes with the next video after the autoplay delay (black). Idle media is not shown in that gap.

In **PROGRAM** mode, **Stop** ends timeline processing, and the program status changes back to **OFF**. The projector stays black; idle media is not shown.

The playback position in the playlist can be changed by clicking on a video. However, the change must be confirmed before it takes effect, to avoid confusion about the playback order. This option is disabled during video playback.

A cursor on the left side of the list shows the current position in the program. The entry is highlighted in the color corresponding to the program status.

Already played videos are grayed out.

If a video requires attention, such as a change in aspect ratio (when **Settings warning** is enabled), a change in resolution, a different pixel aspect ratio, or a different colorspace compared with the previous video, a popup window reminds the projectionist of the necessary actions. The affected data in the playlist entries are marked in red. The program can only be resumed after this information has been confirmed.

### Media Entries

An entry in the playlist displays the filename, folder, codecs, volume, optional loudness, and technical metadata.

If no entry is selected by the projectionist, the preview window shows the data of the current entry. The preview status is set to **Live** (program color).

When an entry is selected by clicking it in the playlist, it gets a yellow border (not a yellow fill), its data is displayed in the preview, and the preview status changes to **Preview** (dark yellow). If that clip is also the program pointer, the row fill follows the program state (blue **PROGRAM**, green **PLAYING**) and the border stays yellow.

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
- Settings warning (forces the beamer confirmation and red **setting!** even when aspect, PAR, and colorspace do not change; only while **Settings warning** is on in the playlist menu)
- Volume (saved per entry from the preview)
- Dimmer while playing (Dark default, Medium, Bright; saved on the playlist entry; applied when the clip starts)

**Settings (video only)**

- Loop checkbox (repeats until **Resume** on the program)
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
- **Loop** repeats a video (In/Out if set) until **Resume** ends it.
- **Dimmer** (`Dark`, `Medium`, `Bright`) is applied when the clip starts, not at the end. House lights come up automatically after the film unless Autoplay continues.
- Volume is adjusted in preview and stored on the entry with **Save volume**.

### Images

Images can also be integrated into the playlist. They behave somewhat differently from videos because they do not have an inherent running time. A display time can be set in the settings. After this time has elapsed, playback either stops or starts the next item, depending on the settings.

If no display time is set, the image stays on screen until **Resume** is pressed, and the focus then moves to the next entry.

Playlists, including all their settings, can be saved for later use.

When an image is followed by a video the framerate of the output for the image is set to the video framerate before it is displayed. This means there is no need to renegotiate the handshake with the projector when the video starts.

### Preview

The preview displays a video in a window within the control panel. The source can be switched between the live video output being sent to the projector (**Live**) and a video from the playlist (**Preview**) by clicking the preview status.

When a playlist entry is selected, the playback position can be selected using a progress bar. A start point and an end point can be defined (buttons or **I** / **O**) to determine where the video starts and ends when it goes on air. This option is disabled while the video is on air. Preview In/Out/Clear sit beside the preview transport.

The preview meter shows program-independent audio levels. After **Analyze loudness**, integrated LUFS is shown above the meter and in the playlist row. During playback the current video bitrate sits next to the progress bar and the current audio bitrate next to the volume slider (program and preview).

# Technique

## Architecture

The computer runs Linux, and the application is written in Python. The open-source video player mpv provides the high-quality video and audio output for the projector and the embedded preview. FFprobe is used to read metadata from the media files. ffmpeg is used only for optional loudness analysis.

For good performance, the graphics card must support hardware decoding of both the H.264 and H.265 codecs.

mpv is started with OSD and subtitles off. The projector instance uses `--screen-name` / `--fs-screen-name` for the selected output.

## Frame Rate

To achieve smooth, flicker-free playback, the graphics card’s refresh rate is adapted before video playback starts.

1. The video’s metadata is read.
2. The refresh rates supported by the projector are checked (shown as **Rates** / **Frequenzen** in the beamer panel).
3. The output is set to the video’s frame rate or an integer multiple of it, preferring the **video resolution**. For 50 and 60 fps, if the projector has no 50/60 Hz mode, Cinema Player uses 25/30 Hz instead.
4. If no matching mode exists, a custom xrandr mode can be created at playback time by scaling the native modeline (X11 only; GNOME Wayland is limited to EDID modes).

If a listed rate can show the clip (native, 2× refresh, or the 25/30 Hz fallback for 50/60 fps), the projector status shows **OK** (green). 30 fps is **OK** when 60 Hz is in the list, even if the projector is not yet switched to 60 Hz. 50 fps is **OK** when 25 Hz is listed and 50 Hz is not.

If no matching refresh rate is found, the status changes to **Mismatch** (red). The clip’s unsupported rate or resolution is then added to the list in blue (program) or yellow (preview). The video can still be displayed, but frame-dropping artifacts may occur.

This check is performed when videos are added to the playlist and when a playlist is loaded. Each entry indicates whether the video can be played correctly. Import and probe do not create custom modes; that happens when a clip is prepared for the projector.

## Audio

The audio track of the program is streamed via the HDMI output of the selected projector connector, not the desktop default. Preview audio can be listened to on a separate device. Each clip has its own volume; program and preview each have a VU meter. Live video and audio bitrates come from mpv (`video-bitrate` / `audio-bitrate`) and show the rate of the last few seconds, not the file average.

## Run

The bilingual operator manual (English / Deutsch, with screenshots) is `manual/index.html`.

From the repository root:

```bash
./install.sh
./start
```

`./install.sh` installs system packages (mpv, ffmpeg, xrandr, gdctl), Pixi and the Python environment, registers the application icon, and adds a menu / Desktop launcher. `./start` uses Pixi when it is available, otherwise the local Pixi environment or `.venv`.

mpv must be the distro build (the conda-forge mpv cannot open a GPU window). On X11 the player uses `xrandr`; on GNOME Wayland it uses `gdctl`.
