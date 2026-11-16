#!/usr/bin/env python3
"""
Spotline Lyrics - Minimal Glassy Desktop Experience.
Features dynamic background matching cover artwork, Material You squiggly wave visualizer,
minimal controls, preferences dialog, and language-aware deduplicated lyrics selector.
"""

import sys
import os
import threading
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio

APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

from preferences import Preferences
from spotify_client import SpotifyClient
from lyrics_manager import LyricsManager
from ui.cover_view import CoverView
from ui.lyrics_view import LyricsView
from ui.lyrics_search_dialog import LyricsSearchDialog
from ui.preferences_dialog import PreferencesDialog


class SpotlineApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id='com.spotline.lyrics',
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.prefs = Preferences()
        self.window = None
        self.spotify = None
        self.lyrics_mgr = None
        self.cover_view = None
        self.lyrics_view = None
        self.position_timer_id = None
        self.current_track = None
        self.current_lyrics = None
        self.current_cover_rgb = (45, 30, 75)
        self.dynamic_css_provider = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._load_base_css()
        style_mgr = Adw.StyleManager.get_default()
        style_mgr.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

    def _load_base_css(self):
        css_file = APP_DIR / 'style.css'
        if css_file.exists():
            provider = Gtk.CssProvider()
            provider.load_from_path(str(css_file))
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )

    def do_activate(self):
        if self.window:
            self.window.present()
            return

        self.lyrics_mgr = LyricsManager()
        self.spotify = SpotifyClient(
            on_track_changed=self._on_track_changed,
            on_status_changed=self._on_status_changed,
            on_running_changed=self._on_running_changed
        )

        # Build Main Window
        self.window = Adw.ApplicationWindow(application=self)
        self.window.set_title("Spotline")
        self.window.set_default_size(1060, 680)
        self.window.add_css_class("main-window")

        icon_path = APP_DIR / 'assets' / 'spotline-lyrics.png'
        if icon_path.exists():
            self.window.set_icon_name("spotline-lyrics")

        # Root Box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.window.set_content(main_box)

        # HeaderBar (Transparent, No dividing line)
        self.header = Adw.HeaderBar()
        self.header.set_show_end_title_buttons(True)

        # Top Right Actions Box
        right_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # 1. Lyrics Search Button
        btn_search = Gtk.Button(label="Lyrics")
        btn_search.set_icon_name("system-search-symbolic")
        btn_search.add_css_class("btn-search-header")
        btn_search.set_tooltip_text("Search & Select Lyrics")
        btn_search.connect("clicked", lambda _: self._open_change_lyrics_dialog())
        right_actions.append(btn_search)

        # 2. Preferences / Settings Button
        btn_prefs = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        btn_prefs.add_css_class("btn-search-header")
        btn_prefs.set_tooltip_text("Display Settings (Opacity & Font)")
        btn_prefs.connect("clicked", lambda _: self._open_preferences_dialog())
        right_actions.append(btn_prefs)

        # 3. Fullscreen Button
        self.btn_fullscreen = Gtk.Button.new_from_icon_name("view-fullscreen-symbolic")
        self.btn_fullscreen.add_css_class("btn-search-header")
        self.btn_fullscreen.set_tooltip_text("Toggle Fullscreen (F11)")
        self.btn_fullscreen.connect("clicked", lambda _: self.toggle_fullscreen())
        right_actions.append(self.btn_fullscreen)

        self.header.pack_end(right_actions)
        main_box.append(self.header)

        # Keyboard shortcuts (F11 = Fullscreen, Esc = Exit Fullscreen)
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.window.add_controller(key_ctrl)

        # Body (Symmetrical 50/50 centered layout, no dividing line)
        body_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body_box.set_homogeneous(True)
        body_box.set_hexpand(True)
        body_box.set_vexpand(True)

        # Left Column: Cover View (Centered in left half)
        self.cover_view = CoverView(
            spotify_client=self.spotify,
            on_color_extracted=self._on_cover_color_extracted
        )
        body_box.append(self.cover_view)

        # Right Column: Lyrics View (Centered in right half)
        self.lyrics_view = LyricsView(spotify_client=self.spotify)
        body_box.append(self.lyrics_view)

        main_box.append(body_box)

        # Initial dynamic styling from preferences
        self._apply_preferences_styling()

        # 250ms position tracking loop
        self.position_timer_id = GLib.timeout_add(250, self._poll_position)

        # Initial Spotify sync
        if self.spotify.current_metadata:
            self._on_track_changed(self.spotify.current_metadata)
        if self.spotify.current_status:
            self._on_status_changed(self.spotify.current_status)

        self.window.present()

    def toggle_fullscreen(self):
        if not self.window:
            return
        if self.window.is_fullscreen():
            self.window.unfullscreen()
            if hasattr(self, 'header') and self.header:
                self.header.set_visible(True)
            if hasattr(self, 'btn_fullscreen') and self.btn_fullscreen:
                self.btn_fullscreen.set_icon_name("view-fullscreen-symbolic")
                self.btn_fullscreen.set_tooltip_text("Fullscreen (F11)")
        else:
            self.window.fullscreen()
            if hasattr(self, 'header') and self.header:
                self.header.set_visible(False)
            if hasattr(self, 'btn_fullscreen') and self.btn_fullscreen:
                self.btn_fullscreen.set_icon_name("view-restore-symbolic")
                self.btn_fullscreen.set_tooltip_text("Exit Fullscreen (F11 or Esc)")

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        elif keyval == Gdk.KEY_Escape and self.window and self.window.is_fullscreen():
            self.toggle_fullscreen()
            return True
        return False

    def _on_cover_color_extracted(self, r, g, b):
        self.current_cover_rgb = (r, g, b)
        self._apply_preferences_styling()

    def _apply_preferences_styling(self):
        """
        Applies dynamic gradient, customizable background opacity, and lyrics font size.
        """
        try:
            r, g, b = self.current_cover_rgb
            opacity = self.prefs.get('bg_opacity', 0.32)
            font_size = self.prefs.get('lyrics_font_size', 24)

            dim_size = max(14, font_size - 6)
            r2 = int(r * 0.35)
            g2 = int(g * 0.35)
            b2 = int(b * 0.35)

            # Calculate theme-matching accent for play button hover
            ar = min(255, int(r * 1.35))
            ag = min(255, int(g * 1.35))
            ab = min(255, int(b * 1.35))
            if ar + ag + ab < 200:
                ar = min(255, ar + 70)
                ag = min(255, ag + 70)
                ab = min(255, ab + 70)

            dynamic_css = f"""
            .main-window {{
                background: radial-gradient(circle at 26% 40%, rgba({r}, {g}, {b}, {opacity}) 0%, rgba({r2}, {g2}, {b2}, {opacity * 0.35}) 55%, #08060f 100%);
            }}
            .square-cover-container {{
                background: rgba(255, 255, 255, {opacity * 0.2});
            }}
            .lyric-active {{
                font-size: {font_size}px;
            }}
            .lyric-dimmed {{
                font-size: {dim_size}px;
            }}
            .btn-minimal-play:hover {{
                background: rgb({ar}, {ag}, {ab});
                color: #08060f;
                box-shadow: 0 4px 22px rgba({r}, {g}, {b}, 0.65);
                border-color: rgba({ar}, {ag}, {ab}, 0.7);
                transform: scale(1.08);
            }}
            """
            display = Gdk.Display.get_default()
            if not display:
                return

            if not self.dynamic_css_provider:
                self.dynamic_css_provider = Gtk.CssProvider()
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    self.dynamic_css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_USER
                )

            self.dynamic_css_provider.load_from_data(dynamic_css.encode('utf-8'))
        except Exception as e:
            print(f"[SpotlineApp] Error updating dynamic styles: {e}")

    def _poll_position(self):
        if not self.spotify or not self.spotify.is_running:
            return GLib.SOURCE_CONTINUE

        pos_ms = self.spotify.get_position_ms()
        pos_s = pos_ms / 1000.0

        if self.cover_view:
            self.cover_view.update_position(pos_s)
        if self.lyrics_view:
            self.lyrics_view.update_position(pos_ms)

        return GLib.SOURCE_CONTINUE

    def _on_track_changed(self, meta):
        GLib.idle_add(self._apply_track_changed, meta)

    def _apply_track_changed(self, meta):
        self.current_track = meta
        if self.cover_view:
            self.cover_view.update_track(meta)

        if not meta:
            if self.lyrics_view:
                self.lyrics_view.set_lyrics(None)
            return GLib.SOURCE_REMOVE

        title = meta.get('title')
        artist = meta.get('artist')
        dur_s = meta.get('length_s')

        def worker():
            lyrics_data = self.lyrics_mgr.find_best_lyrics(title, artist, dur_s)
            GLib.idle_add(self._apply_lyrics, lyrics_data, title)

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _apply_lyrics(self, lyrics_data, expected_title):
        if self.current_track and self.current_track.get('title') != expected_title:
            return GLib.SOURCE_REMOVE

        self.current_lyrics = lyrics_data
        if self.lyrics_view:
            self.lyrics_view.set_lyrics(lyrics_data)

        return GLib.SOURCE_REMOVE

    def _on_status_changed(self, status):
        GLib.idle_add(self._apply_status_changed, status)

    def _apply_status_changed(self, status):
        if self.cover_view:
            self.cover_view.update_playback_status(status)
        return GLib.SOURCE_REMOVE

    def _on_running_changed(self, is_running):
        pass

    def _open_change_lyrics_dialog(self):
        title = self.current_track.get('title', '') if self.current_track else ''
        artist = self.current_track.get('artist', '') if self.current_track else ''

        dialog = LyricsSearchDialog(
            parent_window=self.window,
            lyrics_manager=self.lyrics_mgr,
            initial_track=title,
            initial_artist=artist,
            on_lyrics_selected=self._on_manual_lyrics_selected
        )
        dialog.present()

    def _open_preferences_dialog(self):
        dialog = PreferencesDialog(
            parent_window=self.window,
            preferences=self.prefs,
            on_changed_callback=self._apply_preferences_styling,
            on_toggle_fullscreen=self.toggle_fullscreen
        )
        dialog.present()

    def _on_manual_lyrics_selected(self, lyrics_data):
        self.current_lyrics = lyrics_data
        if self.lyrics_view:
            self.lyrics_view.set_lyrics(lyrics_data)

    def do_shutdown(self):
        if self.position_timer_id:
            GLib.source_remove(self.position_timer_id)
            self.position_timer_id = None
        if self.cover_view and hasattr(self.cover_view, 'wave_progress'):
            self.cover_view.wave_progress.destroy()
        Adw.Application.do_shutdown(self)


def main():
    app = SpotlineApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
