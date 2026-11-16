"""
Minimal Lyrics Search & Selection Dialog.
Deduplicates identical lyrics, displays major language (e.g. Tamil, English),
minimal green/red sync status dots, and radio-style one-click selection.
"""

import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, Adw, GLib, Pango


class LyricsSearchDialog(Gtk.Window):
    def __init__(self, parent_window, lyrics_manager, initial_track, initial_artist, on_lyrics_selected):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title("Select Lyrics")
        self.set_default_size(520, 580)
        self.add_css_class("minimal-search-dialog")

        self.lyrics_manager = lyrics_manager
        self.initial_track = initial_track or ""
        self.initial_artist = initial_artist or ""
        self.on_lyrics_selected = on_lyrics_selected
        self.selected_id = None

        self._build_ui()
        self._start_search(self.initial_track, self.initial_artist)

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root_box.set_margin_top(22)
        root_box.set_margin_bottom(20)
        root_box.set_margin_start(24)
        root_box.set_margin_end(24)
        self.set_child(root_box)

        # Header Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        dlg_title = Gtk.Label(label="Lyrics Versions")
        dlg_title.add_css_class("dialog-heading")
        dlg_title.set_halign(Gtk.Align.START)
        dlg_title.set_hexpand(True)
        title_box.append(dlg_title)

        # Close button
        btn_close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        btn_close.add_css_class("btn-icon-minimal")
        btn_close.connect("clicked", lambda _: self.close())
        title_box.append(btn_close)
        root_box.append(title_box)

        # Minimal Search Bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.add_css_class("minimal-search-entry")
        self.search_entry.set_placeholder_text("Search track name or artist...")
        initial_q = f"{self.initial_track} {self.initial_artist}".strip()
        self.search_entry.set_text(initial_q)
        self.search_entry.connect("activate", self._on_search_clicked)
        search_box.append(self.search_entry)

        search_btn = Gtk.Button.new_from_icon_name("system-search-symbolic")
        search_btn.add_css_class("btn-icon-minimal")
        search_btn.set_tooltip_text("Search")
        search_btn.connect("clicked", self._on_search_clicked)
        search_box.append(search_btn)
        root_box.append(search_box)

        # Loading Spinner
        self.spinner = Gtk.Spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_size_request(24, 24)
        root_box.append(self.spinner)

        # Scrolled Results List
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.results_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.results_container.set_hexpand(True)
        scrolled.set_child(self.results_container)
        root_box.append(scrolled)

    def _on_search_clicked(self, *args):
        query = self.search_entry.get_text().strip()
        if query:
            self._start_search(query)

    def _start_search(self, query_or_title, artist=None):
        self.spinner.start()
        self.spinner.set_visible(True)

        while True:
            child = self.results_container.get_first_child()
            if not child:
                break
            self.results_container.remove(child)

        def worker():
            results = self.lyrics_manager.search_top_candidates(query_or_title, artist, limit=10)
            GLib.idle_add(self._render_results, results)

        threading.Thread(target=worker, daemon=True).start()

    def _render_results(self, results):
        self.spinner.stop()
        self.spinner.set_visible(False)

        if not results:
            lbl = Gtk.Label(label="No distinct lyrics found.")
            lbl.add_css_class("meta-subtle")
            lbl.set_margin_top(40)
            self.results_container.append(lbl)
            return GLib.SOURCE_REMOVE

        for item in results:
            # Whole row is a clickable card
            btn_row = Gtk.Button()
            btn_row.add_css_class("minimal-result-row")
            btn_row.set_hexpand(True)

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row_box.set_hexpand(True)

            # 1. Radio button / selection dot indicator
            radio_lbl = Gtk.Label(label="○")
            radio_lbl.add_css_class("radio-indicator")
            row_box.append(radio_lbl)

            # 2. Minimal Green / Red dot for synced status
            # Green dot = synced, Red dot = non-synced
            dot_color = "#1ed760" if item.get('has_synced') else "#ff4b4b"
            dot_lbl = Gtk.Label()
            dot_lbl.set_markup(f'<span color="{dot_color}" font_size="13pt">●</span>')
            dot_lbl.set_tooltip_text("Synced Lyrics" if item.get('has_synced') else "Unsynced Plain Text")
            row_box.append(dot_lbl)

            # 3. Track Details Box
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info_box.set_hexpand(True)

            title_lbl = Gtk.Label(label=item['track_name'])
            title_lbl.add_css_class("result-title-minimal")
            title_lbl.set_halign(Gtk.Align.START)
            title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            info_box.append(title_lbl)

            sub_text = f"{item['artist_name']}  •  {item['duration_str']}"
            sub_lbl = Gtk.Label(label=sub_text)
            sub_lbl.add_css_class("meta-subtle")
            sub_lbl.set_halign(Gtk.Align.START)
            sub_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            info_box.append(sub_lbl)

            row_box.append(info_box)

            # 4. Major Language Badge (e.g. Tamil, English, etc.)
            lang = item.get('language', 'English')
            lang_badge = Gtk.Label(label=lang)
            lang_badge.add_css_class("lang-pill")
            lang_badge.set_valign(Gtk.Align.CENTER)
            row_box.append(lang_badge)

            btn_row.set_child(row_box)

            # Clicking the row immediately selects this lyrics candidate
            btn_row.connect("clicked", lambda _, candidate=item: self._select_candidate(candidate))
            self.results_container.append(btn_row)

        return GLib.SOURCE_REMOVE

    def _select_candidate(self, candidate):
        full_rec = candidate.get('full_data')
        if not full_rec:
            self.spinner.start()
            self.spinner.set_visible(True)

            def worker():
                rec = self.lyrics_manager.get_lyrics_by_id(candidate['id'])
                if rec:
                    processed = self.lyrics_manager._process_record(rec)
                    GLib.idle_add(self._finish_selection, processed)

            threading.Thread(target=worker, daemon=True).start()
        else:
            processed = self.lyrics_manager._process_record(full_rec)
            self._finish_selection(processed)

    def _finish_selection(self, lyrics_data):
        self.spinner.stop()
        if self.on_lyrics_selected:
            self.on_lyrics_selected(lyrics_data)
        self.close()
        return GLib.SOURCE_REMOVE
