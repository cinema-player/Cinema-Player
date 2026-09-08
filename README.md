# Cinema Player

The Cinema Player is designed to play videos on a projector in a small private cinema. It uses two outputs (HDMI, DVI, or DisplayPort) from a dedicated graphics card to separate the video output from the control interface.

The aim is to provide the audience with a high-quality cinema experience, free from distracting text or OSD elements on the big screen, while offering the projectionist an intuitive yet powerful user interface.

The video output displays only the video image. When no playback is active, the screen remains black. The control screen displays a playlist containing the program, which can include videos and images, as well as playback controls. A preview window allows the projectionist to monitor the video being played, preview videos, and edit the playlist.

# Function

## Controller

The control window is divided into three parts:

- A status area at the top shows the playback and projector status.
- Below, on the left, are the playback controls, including a progress bar and time displays, as well as the playlist with functions for loading media files, sorting them, and saving and loading playlists.
- On the right is the preview window with a video player and an editing area for the settings.

### Playlist

The playlist is the central user interface of the player. It displays a scrollable list of the video files in the order in which they will be played. Videos or entire directories can be added to the list. The position of an entry in the list can be changed by dragging it.

#### Global Settings

These settings control the behavior of the playlist.

- **Projection zoom** – When the projector's zoom is changed between 16:9 and 21:9 to fill a wide screen, this checkbox is selected. When the zoom needs to be changed, a popup window informs the projectionist when to do so. Playback starts once the successful zoom change has been confirmed.  
  When 16:9 images are displayed in 21:9 zoom mode, they are scaled to fit the vertical resolution.
- **Autoplay delay** – The number of seconds to wait before the next video is started automatically.
- **Idle screen media** – An image or video loop to be shown instead of a black screen when no video is playing.

#### Playback Controls

- **Play**/**Resume** – Start or resume playback.
- **Pause** – Pause playback and retain the current position. The video output is rendered black.
- **Still** – Like Pause, but displays a still image of the current video position.
- **Stop** – Stop playback and set the position to the next entry in the list.

**Pause**, **Still**, and **Stop** must be confirmed before the action is performed.

#### Time Displays

When a video is playing, four time values are shown:

- **Total** – The length of the video.
- **Elapsed** – The time that has already been played.
- **Remaining** – The remaining playback time.
- **End** – The absolute time at which the video will end.

#### Program and Playback

The playlist is started by pressing the **Play** button. The program status in the status bar changes from **OFF** (red) to **PROGRAM** (blue), and the **Play** button changes to **Resume** to indicate that the program is running. The playlist is now processed.

Pressing **Resume** starts the currently selected video in the list, and the status changes to **PLAYING** (green). When a video ends, the status changes back to **PROGRAM** (blue), and the next entry in the list can be started with the **Resume** button.

If the autoplay option is selected for an entry, playback automatically resumes with the next video. The autoplay delay in the timeline settings determines how many seconds of black are shown before the next video starts.

In **PROGRAM** mode, **Stop** only ends the playback of the current video; it does not stop the execution of the timeline. Pressing **Stop** a second time ends timeline processing, and the program status changes back to **OFF**.

The playback position in the playlist can be changed by clicking on a video. However, the change must be confirmed before it takes effect, to avoid confusion about the playback order. This option is disabled during video playback.

A cursor on the left side of the list shows the current position in the program. The entry is highlighted in the color corresponding to the program status.

Already played videos are grayed out.

If a video requires attention, such as a change in aspect ratio (when projection zoom is enabled), a change in resolution, or a different pixel aspect ratio compared with the previous video, a popup window reminds the projectionist of the necessary actions. The affected data in the playlist entries are marked in red. The program can only be resumed after this information has been confirmed.

#### Media Entries

An entry in the playlist displays the filename, additional information, and the individual settings.

If no entry is selected by the projectionist, the preview window shows the data of the current entry. The preview status in the upper-right corner of the preview area is set to **Live** (program color).

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

**Settings (all media)**

- Autoplay checkbox

**Settings (video only)**

- Audio track
- Subtitle track
- Start position
- End position

**Settings (image only)**

- Display time

#### Entry Settings

Different options can be selected for each entry in the playlist.

- If multiple audio tracks are available, the track to be used can be selected.
- If subtitles are embedded, the desired subtitle track can be selected.
- A checkbox overrides the automatic stop behavior and automatically starts playback of the next entry.

#### Images

Images can also be integrated into the playlist. They behave somewhat differently from videos because they do not have an inherent running time. A display time can be set in the settings. After this time has elapsed, playback either stops or starts the next item, depending on the settings.

If no display time is set, the image must be stopped using the playback controls, and the focus then moves to the next entry.

Playlists, including all their settings, can be saved for later use.

When an image is followed by a video the framerate of the output for the image is set to the video framerate before it is displayed. This means there is no need to renegotiate the handshake with the projector when the video starts.

### Preview

The preview displays a video in a window within the control panel. The source can be switched between the live video output being sent to the projector (**Live**) and a video from the playlist (**Preview**) by clicking the preview status.

When a playlist entry is selected, the playback position can be selected using a progress bar. A start point and an end point can be defined to determine where the video starts and ends when it goes on air. This option is disabled while the video is on air.

# Technique

## Architecture

The computer runs Linux, and the application is written in Python. The open-source video player MPV provides the high-quality video and audio output for the projector. FFprobe is used to read all metadata from the video files.

For good performance, the graphics card must support hardware decoding of both the H.264 and H.265 codecs.

## Frame Rate

To achieve smooth, flicker-free playback, the graphics card's refresh rate must be adapted before video playback starts.

1. The video's metadata is read.
2. The refresh rates supported by the projector are checked.
3. The graphics card is set to the video's frame rate or an integer multiple of it.

If the process is successful, the projector status shows **OK** (green).

If no matching refresh rate is found, the status changes to **Mismatch** (red), and the incorrect settings are highlighted in red. In this case, the video can still be displayed, but frame-dropping artifacts may occur.

This check is performed when videos are added to the playlist and when a playlist is loaded. Each entry indicates whether the video can be played correctly.

## Audio

The audio track of the video is streamed via the HDMI output to the projector. When watching a video in the preview, the audio is not only provided through the second HDMI output but can also be routed to a dedicated audio output.