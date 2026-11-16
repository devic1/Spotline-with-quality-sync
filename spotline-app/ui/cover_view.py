"""
Cover View (Left Pane)
Features centered square album art, track title, Google Pixel Material You squiggly wave progress bar,
and three minimal playback controls.
"""

import os
import math
import hashlib
import threading
import urllib.request
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, Pango


COVERS_CACHE_DIR = Path.home() / '.cache' / 'spotline' / 'covers'


class MaterialWaveProgressBar(Gtk.Box):
    """
    Google Pixel Material You Squiggly Wavy Progress Bar.
    Renders played progress as an animated sine wave with a scrubber head,
    and unplayed progress as a subtle straight line.
    """
    def __init__(self, on_seek_requested=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.on_seek_requested = on_seek_requested
        self.fraction = 0.0
        self.is_playing = False
        self.phase = 0.0
        self.width = 320
        self.height = 28
        self.accent_color = "#1ed760"
        self.track_color = "rgba(255, 255, 255, 0.22)"

        # Fixed-size Picture widget for zero-jitter rendering
        self.picture = Gtk.Picture()
        self.picture.set_size_request(self.width, self.height)
        self.picture.set_can_shrink(False)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)

        # Click gesture for seeking
        click = Gtk.GestureClick.new()
        click.connect("pressed", self._on_clicked)
        self.picture.add_controller(click)
        self.append(self.picture)

        # Time labels row
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        time_box.set_size_request(self.width, -1)
        time_box.set_halign(Gtk.Align.CENTER)

        self.time_current = Gtk.Label(label="0:00")
        self.time_current.add_css_class("time-minimal")
        self.time_current.set_halign(Gtk.Align.START)
        self.time_current.set_hexpand(True)

        self.time_total = Gtk.Label(label="0:00")
        self.time_total.add_css_class("time-minimal")
        self.time_total.set_halign(Gtk.Align.END)

        time_box.append(self.time_current)
        time_box.append(self.time_total)
        self.append(time_box)

        # Render initial frame
        self._render_svg()

        # Wave animation timer (50ms ~ 20fps for smooth fluid ripple)
        self.anim_timer_id = GLib.timeout_add(50, self._on_anim_tick)

    def set_colors(self, accent_hex, track_rgba):
        self.accent_color = accent_hex
        self.track_color = track_rgba
        self._render_svg()

    def _render_svg(self):
        y0 = self.height / 2.0
        x_played = max(4.0, min(self.width - 4.0, self.fraction * self.width))
        amplitude = 4.2 if self.is_playing else 1.8
        wavelength = 24.0

        points = []
        step = 3.0
        x = 0.0
        while x <= x_played:
            dist_to_end = x_played - x
            taper = min(1.0, dist_to_end / 14.0)
            y = y0 + amplitude * taper * math.sin((2 * math.pi * x / wavelength) - self.phase)
            points.append(f"{x:.1f},{y:.1f}")
            x += step

        points.append(f"{x_played:.1f},{y0:.1f}")
        wave_d = "M " + " L ".join(points)

        svg = f"""<svg width="{self.width}" height="{self.height}" xmlns="http://www.w3.org/2000/svg">
          <line x1="{x_played:.1f}" y1="{y0:.1f}" x2="{self.width}" y2="{y0:.1f}" stroke="{self.track_color}" stroke-width="3.6" stroke-linecap="round"/>
          <path d="{wave_d}" stroke="{self.accent_color}" stroke-width="3.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="{x_played:.1f}" cy="{y0:.1f}" r="5.5" fill="{self.accent_color}"/>
        </svg>"""

        try:
            loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
            loader.write(svg.encode('utf-8'))
            loader.close()
            pb = loader.get_pixbuf()
            if pb:
                tex = Gdk.Texture.new_for_pixbuf(pb)
                self.picture.set_paintable(tex)
        except Exception:
            pass

    def _on_anim_tick(self):
        if self.is_playing:
            self.phase += 0.22
            self._render_svg()
        return GLib.SOURCE_CONTINUE

    def _on_clicked(self, gesture, n_press, x, y):
        if self.width > 0 and self.on_seek_requested:
            frac = max(0.0, min(1.0, x / self.width))
            self.on_seek_requested(frac)

    def set_progress(self, current_s, total_s, is_playing):
        self.is_playing = is_playing
        if total_s > 0:
            self.fraction = min(1.0, max(0.0, current_s / total_s))
            self.time_current.set_text(self._format_time(current_s))
            self.time_total.set_text(self._format_time(total_s))
        else:
            self.fraction = 0.0
            self.time_current.set_text("0:00")
            self.time_total.set_text("0:00")

        self._render_svg()

    def _format_time(self, seconds):
        if not seconds or seconds < 0:
            return "0:00"
        s = int(seconds)
        m = s // 60
        sec = s % 60
        return f"{m}:{sec:02d}"

    def destroy(self):
        if self.anim_timer_id:
            GLib.source_remove(self.anim_timer_id)
            self.anim_timer_id = None


class CoverView(Gtk.Box):
    def __init__(self, spotify_client, on_color_extracted=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_hexpand(True)
        self.add_css_class("left-pane-minimal")

        self.spotify_client = spotify_client
        self.on_color_extracted = on_color_extracted
        self.current_art_url = None
        self.current_duration_s = 0
        self.is_playing = False

        COVERS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._build_ui()

    def _build_ui(self):
        # 1. Centered Square Cover (fixed 300x300, non-interactive to prevent drag artifact)
        self.cover_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.cover_frame.set_halign(Gtk.Align.CENTER)
        self.cover_frame.set_valign(Gtk.Align.CENTER)
        self.cover_frame.set_size_request(300, 300)
        self.cover_frame.add_css_class("square-cover-container")

        self.cover_picture = Gtk.Picture()
        self.cover_picture.set_size_request(300, 300)
        self.cover_picture.set_can_shrink(False)
        self.cover_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.cover_picture.add_css_class("square-cover-image")
        self.cover_frame.append(self.cover_picture)
        self.append(self.cover_frame)

        self._set_default_cover()

        # 2. Lower Area: Just Track Name
        self.title_label = Gtk.Label(label="No Track Playing")
        self.title_label.add_css_class("track-name-bold")
        self.title_label.set_halign(Gtk.Align.CENTER)
        self.title_label.set_justify(Gtk.Justification.CENTER)
        self.title_label.set_wrap(True)
        self.title_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.title_label.set_max_width_chars(24)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(self.title_label)

        # 3. Material You Squiggly Progress Bar
        self.wave_progress = MaterialWaveProgressBar(on_seek_requested=self._on_seek_requested)
        self.wave_progress.set_halign(Gtk.Align.CENTER)
        self.wave_progress.set_size_request(320, -1)
        self.append(self.wave_progress)

        # 4. Three Minimal Controls (Prev, Play/Pause, Next)
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        controls_box.set_halign(Gtk.Align.CENTER)
        controls_box.set_margin_top(6)

        self.btn_prev = Gtk.Button.new_from_icon_name("media-skip-backward-symbolic")
        self.btn_prev.add_css_class("btn-minimal")
        self.btn_prev.set_tooltip_text("Previous")
        self.btn_prev.connect("clicked", lambda _: self.spotify_client.previous())
        controls_box.append(self.btn_prev)

        self.btn_play_pause = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        self.btn_play_pause.add_css_class("btn-minimal-play")
        self.btn_play_pause.set_tooltip_text("Play / Pause")
        self.btn_play_pause.connect("clicked", lambda _: self.spotify_client.play_pause())
        controls_box.append(self.btn_play_pause)

        self.btn_next = Gtk.Button.new_from_icon_name("media-skip-forward-symbolic")
        self.btn_next.add_css_class("btn-minimal")
        self.btn_next.set_tooltip_text("Next")
        self.btn_next.connect("clicked", lambda _: self.spotify_client.next())
        controls_box.append(self.btn_next)

        self.append(controls_box)

    def _set_default_cover(self):
        icon_path = Path(__file__).parent.parent / 'assets' / 'spotline-lyrics.png'
        if icon_path.exists():
            file = Gio.File.new_for_path(str(icon_path))
            self.cover_picture.set_file(file)

    def _on_seek_requested(self, fraction):
        if self.current_duration_s > 0 and self.spotify_client:
            target_ms = fraction * self.current_duration_s * 1000.0
            self.spotify_client.set_position(target_ms)

    def update_track(self, meta):
        if not meta:
            self.title_label.set_text("No Track Playing")
            self.current_duration_s = 0
            self.wave_progress.set_progress(0, 0, False)
            self._set_default_cover()
            return

        self.title_label.set_text(meta.get('title', 'Unknown Title'))
        self.current_duration_s = meta.get('length_s', 0)

        art_url = meta.get('art_url')
        if art_url and art_url != self.current_art_url:
            self.current_art_url = art_url
            self._load_art_async(art_url)

    def update_playback_status(self, status):
        self.is_playing = (status == 'Playing')
        if self.is_playing:
            self.btn_play_pause.set_icon_name("media-playback-pause-symbolic")
        else:
            self.btn_play_pause.set_icon_name("media-playback-start-symbolic")

    def update_position(self, pos_s):
        self.wave_progress.set_progress(pos_s, self.current_duration_s, self.is_playing)

    def _load_art_async(self, art_url):
        def worker():
            cache_name = hashlib.md5(art_url.encode('utf-8')).hexdigest() + ".jpg"
            cache_path = COVERS_CACHE_DIR / cache_name

            if not cache_path.exists():
                try:
                    req = urllib.request.Request(art_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = resp.read()
                        with open(cache_path, 'wb') as f:
                            f.write(data)
                except Exception as e:
                    print(f"[CoverView] Failed to download cover: {e}")
                    return

            GLib.idle_add(self._apply_cover_pixbuf, str(cache_path))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_cover_pixbuf(self, image_path):
        try:
            file = Gio.File.new_for_path(image_path)
            self.cover_picture.set_file(file)

            # Sample dominant color to inform main window gradient and progress wave
            if self.on_color_extracted:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(image_path, 32, 32, False)
                pixels = pb.get_pixels()
                n_channels = pb.get_n_channels()
                rowstride = pb.get_rowstride()
                r_tot, g_tot, b_tot, count = 0, 0, 0, 0
                for y in range(0, 32, 3):
                    for x in range(0, 32, 3):
                        idx = y * rowstride + x * n_channels
                        r_tot += pixels[idx]
                        g_tot += pixels[idx + 1]
                        b_tot += pixels[idx + 2]
                        count += 1
                if count > 0:
                    r = r_tot // count
                    g = g_tot // count
                    b = b_tot // count
                    self.on_color_extracted(r, g, b)

                    # Update wave progress bar colors to match cover
                    accent_hex = f"#{min(255, int(r * 1.35)):02x}{min(255, int(g * 1.35)):02x}{min(255, int(b * 1.35)):02x}"
                    track_rgba = f"rgba({r}, {g}, {b}, 0.28)"
                    self.wave_progress.set_colors(accent_hex, track_rgba)
        except Exception as e:
            print(f"[CoverView] Error applying cover: {e}")
        return GLib.SOURCE_REMOVE
