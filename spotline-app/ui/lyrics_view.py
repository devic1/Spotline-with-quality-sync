"""
Minimal Floating Lyrics View (Right Pane)
Real-time synchronized lyrics with karaoke active-line glow,
ultra-smooth kinetic auto-scroll, centered layout, and click-to-seek.
"""

import time
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, GLib, Pango


class LyricsView(Gtk.Box):
    def __init__(self, spotify_client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.FILL)
        self.add_css_class("right-pane-minimal")

        self.spotify_client = spotify_client
        self.current_lyrics_data = None
        self.synced_lines = []
        self.line_widgets = []
        self.active_index = -1
        self.user_scrolling_until = 0

        # Smooth scrolling variables
        self.scroll_target_y = 0.0
        self.scroll_timer_id = None

        self._build_ui()

    def _build_ui(self):
        # Scrolled Window (Centered, generous readable width)
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_halign(Gtk.Align.CENTER)
        self.scrolled.set_size_request(520, -1)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.add_css_class("lyrics-scroll-minimal")

        # Container for lines (Centered)
        self.lyrics_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.lyrics_container.set_valign(Gtk.Align.START)
        self.lyrics_container.set_halign(Gtk.Align.CENTER)
        self.lyrics_container.set_size_request(500, -1)
        self.lyrics_container.set_margin_top(80)
        self.lyrics_container.set_margin_bottom(240)
        self.lyrics_container.set_margin_start(16)
        self.lyrics_container.set_margin_end(16)

        self.scrolled.set_child(self.lyrics_container)
        self.append(self.scrolled)

        v_adj = self.scrolled.get_vadjustment()
        v_adj.connect("value-changed", self._on_scroll_value_changed)

        self._show_empty_state("Play a song on Spotify to start")

    def _on_scroll_value_changed(self, adj):
        pass

    def set_lyrics(self, lyrics_data):
        self._cancel_smooth_scroll()
        self.current_lyrics_data = lyrics_data
        self.synced_lines = []
        self.line_widgets = []
        self.active_index = -1

        while True:
            child = self.lyrics_container.get_first_child()
            if not child:
                break
            self.lyrics_container.remove(child)

        if not lyrics_data:
            self._show_empty_state("No lyrics found for this track")
            return

        if lyrics_data.get('instrumental'):
            self._show_empty_state("♪ Instrumental ♪")
            return

        if lyrics_data.get('has_synced') and lyrics_data.get('synced_lines'):
            self.synced_lines = lyrics_data['synced_lines']
            self._render_synced_lines()
        elif lyrics_data.get('has_plain') and lyrics_data.get('plain_text'):
            self._render_plain_lyrics(lyrics_data['plain_text'])
        else:
            self._show_empty_state("No lyrics found")

    def _render_synced_lines(self):
        for idx, item in enumerate(self.synced_lines):
            line_text = item.get('text', '')
            if not line_text:
                line_text = "• • •"

            btn = Gtk.Button()
            btn.add_css_class("lyric-minimal-btn")
            btn.add_css_class("lyric-dimmed")
            btn.set_size_request(480, -1)
            btn.set_halign(Gtk.Align.CENTER)

            label = Gtk.Label(label=line_text)
            label.set_wrap(True)
            label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_halign(Gtk.Align.START)
            label.set_xalign(0.0)
            btn.set_child(label)

            t_ms = item.get('time_ms', 0)
            btn.connect("clicked", lambda _, ms=t_ms: self._seek_to(ms))

            self.lyrics_container.append(btn)
            self.line_widgets.append(btn)

    def _render_plain_lyrics(self, plain_text):
        label = Gtk.Label(label=plain_text.strip())
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_selectable(True)
        label.set_justify(Gtk.Justification.LEFT)
        label.add_css_class("plain-lyrics-minimal")
        label.set_size_request(480, -1)
        self.lyrics_container.append(label)

    def _show_empty_state(self, message):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.set_hexpand(True)
        box.set_vexpand(True)
        box.set_margin_top(140)

        lbl = Gtk.Label(label=message)
        lbl.add_css_class("meta-subtle")
        lbl.set_justify(Gtk.Justification.CENTER)
        box.append(lbl)
        self.lyrics_container.append(box)

    def _seek_to(self, time_ms):
        if self.spotify_client:
            self.spotify_client.set_position(time_ms)
            self.user_scrolling_until = time.time() + 1.5

    def update_position(self, pos_ms):
        if not self.synced_lines or not self.line_widgets:
            return

        new_active = -1
        for i in range(len(self.synced_lines) - 1, -1, -1):
            if self.synced_lines[i]['time_ms'] <= pos_ms:
                new_active = i
                break

        if new_active == -1 and len(self.synced_lines) > 0:
            new_active = 0

        if new_active != self.active_index and 0 <= new_active < len(self.line_widgets):
            # Smoothly crossfade lines
            if 0 <= self.active_index < len(self.line_widgets):
                old_btn = self.line_widgets[self.active_index]
                old_btn.remove_css_class("lyric-active")
                old_btn.add_css_class("lyric-dimmed")

            new_btn = self.line_widgets[new_active]
            new_btn.remove_css_class("lyric-dimmed")
            new_btn.add_css_class("lyric-active")
            self.active_index = new_active

            # Kinetic auto-scroll
            if time.time() > self.user_scrolling_until:
                self._smooth_scroll_to_active(new_btn)

    def _smooth_scroll_to_active(self, widget):
        try:
            adj = self.scrolled.get_vadjustment()
            if not adj:
                return
            res, bounds = widget.compute_bounds(self.lyrics_container)
            if res:
                widget_y = bounds.get_top_left().y
                page_size = adj.get_page_size()
                target = max(0.0, widget_y - (page_size * 0.38))
                self.scroll_target_y = target

                if not self.scroll_timer_id:
                    self.scroll_timer_id = GLib.timeout_add(16, self._on_scroll_tick)
        except Exception:
            pass

    def _on_scroll_tick(self):
        adj = self.scrolled.get_vadjustment()
        if not adj:
            self.scroll_timer_id = None
            return GLib.SOURCE_REMOVE

        current = adj.get_value()
        diff = self.scroll_target_y - current

        if abs(diff) < 0.8:
            adj.set_value(self.scroll_target_y)
            self.scroll_timer_id = None
            return GLib.SOURCE_REMOVE

        step = diff * 0.16
        adj.set_value(current + step)
        return GLib.SOURCE_CONTINUE

    def _cancel_smooth_scroll(self):
        if self.scroll_timer_id:
            GLib.source_remove(self.scroll_timer_id)
            self.scroll_timer_id = None
