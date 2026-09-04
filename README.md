# Spotline (with Quality Sync)

A GNOME Shell extension that displays the currently playing Spotify song and real-time synchronized lyrics directly in your top panel, along with live audio quality stream metrics.

---

## ✨ Features & Improvements

- **Accurate Lyrics Finder & Resilient Polling**:
  - Searches LRCLIB (`/api/search?q=...`) using the exact track title.
  - Automatically filters candidates within $\pm 5$ seconds duration drift and sorts by closest duration match to the playing track.
  - **Resilient Retry Polling**: If the lyrics API returns an error (e.g. HTTP 503 Service Unavailable) or transient failure, Spotline runs backup retries with staggered intervals (1s, 3s, 6s, 12s) for up to 30 seconds per song before cleanly stopping.
  - Seamlessly falls back to the track title if no synced lyrics match, preventing stuck first lines or unsynced plain text.

- **Added Quality Inspector (Zero-Debug Native)**:
  - Verifies real download payload sizes and content bitrates **directly inside GNOME Shell** without requiring Spotify debug flags, wrapper scripts, or external Python daemons.
  - Inspects active Spotify file descriptors in Linux `/proc/<pid>/fd/` and cursor positions (`pos:`) to identify the exact audio file in real time.
  - **1.0-Second Stability Sampling**: Flags tracks as `Buffering (<size>MB)` during downloads so premature bitrates are never shown, calculating accurate bitrate once bytes stabilize.
  - **10-Second Stream Polling**: Non-blocking periodic checks detect chunk growth on long tracks/podcasts and dynamically refresh metrics.

- **Scrolling Animations**:
  - **Horizontal Slide (Title $\rightarrow$ Lyrics)**: When a song starts, the title appears immediately. As soon as synced lyrics are loaded, the title slides out to the left and the first lyric slides smoothly in from the right.
  - **Vertical Roll (Line $\rightarrow$ Line)**: Subtle vertical roll transitions animate subsequent lyric lines as playback advances.

- **Duration & Live Stream Metrics**:
  - Displays formatted song duration alongside real measured bitrate and stream cache size directly in the dropdown menu:
    ```text
    {duration} | ~{bitrate}kbps ({size}MB)
    ```
    *(e.g., `4m 55s | ~316kbps (11.1MB)`)*

- **Spotify-Exclusive Tracking & Clean Panel Presence**:
  - Exclusively monitors Spotify via MPRIS (`org.mpris.MediaPlayer2.spotify`), ignoring browser media sessions or other audio players.
  - Automatically hides from the top bar when Spotify is closed or not running—no clutter or empty placeholder text.

- **Interactive Playback Controls**:
  - Control Spotify directly from the panel menu with Prev, Play/Pause, and Next buttons.

---

## 🚀 Installation

### User Installation (Recommended):

```bash
mkdir -p ~/.local/share/gnome-shell/extensions/spotify-lyrics-ext@devic1
cp -r * ~/.local/share/gnome-shell/extensions/spotify-lyrics-ext@devic1/
```

### Reloading the Extension:

- **On GNOME on Xorg (X11)**:
  Press `Alt + F2`, type `r`, and press `Enter`.
- **On Wayland**:
  Log out and log back in.

### Enable the Extension:

```bash
gnome-extensions enable spotify-lyrics-ext@devic1
```

Or enable it via the **GNOME Extensions** application.

---

## 🛠️ Development & Debugging

### View Extension Logs:
```bash
journalctl -f -o cat /usr/bin/gnome-shell | grep -i spotify
```

### Verify MPRIS Connection:
```bash
dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.freedesktop.DBus.Properties.Get string:org.mpris.MediaPlayer2.Player string:Metadata
```

---

## 👏 Credits & Acknowledgements

* **Original Creator**: [d3osaju](https://github.com/d3osaju/Spotline) for creating the original Spotline / Music Lyrics extension.
* **Enhancements & Fork**: [devic1](https://github.com/devic1/Spotline-with-quality-sync) for adding the native zero-debug quality inspector, periodic stream polling, accurate duration-matched lyrics finder, right-to-left slide animation, and duration metrics.

