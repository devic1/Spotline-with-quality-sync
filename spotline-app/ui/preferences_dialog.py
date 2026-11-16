"""
Preferences Dialog for Spotline Lyrics.
Allows adjusting background ambient opacity, lyrics font size, and fullscreen mode in real-time.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib


class PreferencesDialog(Gtk.Window):
    def __init__(self, parent_window, preferences, on_changed_callback, on_toggle_fullscreen=None):
        super().__init__(transient_for=parent_window, modal=True)
        self.parent_window = parent_window
        self.set_title("Display Settings")
        self.set_default_size(440, 360)
        self.add_css_class("minimal-search-dialog")

        self.prefs = preferences
        self.on_changed_callback = on_changed_callback
        self.on_toggle_fullscreen = on_toggle_fullscreen
        self._build_ui()

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        root_box.set_margin_top(24)
        root_box.set_margin_bottom(24)
        root_box.set_margin_start(28)
        root_box.set_margin_end(28)
        self.set_child(root_box)

        # Header Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        dlg_title = Gtk.Label(label="Display Settings")
        dlg_title.add_css_class("dialog-heading")
        dlg_title.set_halign(Gtk.Align.START)
        dlg_title.set_hexpand(True)
        title_box.append(dlg_title)

        btn_close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        btn_close.add_css_class("btn-icon-minimal")
        btn_close.connect("clicked", lambda _: self.close())
        title_box.append(btn_close)
        root_box.append(title_box)

        # 1. Background Opacity Slider (Ambient gradient intensity)
        bg_op = self.prefs.get('bg_opacity', 0.32)
        bg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        bg_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bg_lbl = Gtk.Label(label="Background Glow Opacity")
        bg_lbl.add_css_class("result-title-minimal")
        bg_lbl.set_halign(Gtk.Align.START)
        bg_lbl.set_hexpand(True)

        self.bg_val_lbl = Gtk.Label(label=f"{int(bg_op * 100)}%")
        self.bg_val_lbl.add_css_class("meta-subtle")
        bg_header.append(bg_lbl)
        bg_header.append(self.bg_val_lbl)
        bg_box.append(bg_header)

        self.bg_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 0.75, 0.02)
        self.bg_scale.set_value(bg_op)
        self.bg_scale.connect("value-changed", self._on_bg_opacity_changed)
        bg_box.append(self.bg_scale)
        root_box.append(bg_box)

        # 2. Lyrics Font Size Slider
        font_val = self.prefs.get('lyrics_font_size', 24)
        font_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        font_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        font_lbl = Gtk.Label(label="Lyrics Font Size")
        font_lbl.add_css_class("result-title-minimal")
        font_lbl.set_halign(Gtk.Align.START)
        font_lbl.set_hexpand(True)

        self.font_val_lbl = Gtk.Label(label=f"{int(font_val)}px")
        self.font_val_lbl.add_css_class("meta-subtle")
        font_header.append(font_lbl)
        font_header.append(self.font_val_lbl)
        font_box.append(font_header)

        self.font_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 16.0, 36.0, 2.0)
        self.font_scale.set_value(font_val)
        self.font_scale.connect("value-changed", self._on_font_changed)
        font_box.append(self.font_scale)
        root_box.append(font_box)

        # 3. Fullscreen Mode Switch Row
        fs_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        fs_box.set_margin_top(6)

        fs_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        fs_text_box.set_hexpand(True)

        fs_lbl = Gtk.Label(label="Full Screen Mode")
        fs_lbl.add_css_class("result-title-minimal")
        fs_lbl.set_halign(Gtk.Align.START)
        fs_text_box.append(fs_lbl)

        fs_sub = Gtk.Label(label="Cover entire screen (F11 or Esc to exit)")
        fs_sub.add_css_class("meta-subtle")
        fs_sub.set_halign(Gtk.Align.START)
        fs_text_box.append(fs_sub)

        fs_box.append(fs_text_box)

        self.fs_switch = Gtk.Switch()
        self.fs_switch.set_valign(Gtk.Align.CENTER)
        is_fs = self.parent_window.is_fullscreen() if self.parent_window else False
        self.fs_switch.set_active(is_fs)
        self.fs_switch.connect("state-set", self._on_fs_switch_toggled)
        fs_box.append(self.fs_switch)
        root_box.append(fs_box)

    def _on_bg_opacity_changed(self, scale):
        val = round(scale.get_value(), 2)
        self.bg_val_lbl.set_text(f"{int(val * 100)}%")
        self.prefs.set('bg_opacity', val)
        if self.on_changed_callback:
            self.on_changed_callback()

    def _on_font_changed(self, scale):
        val = int(scale.get_value())
        self.font_val_lbl.set_text(f"{val}px")
        self.prefs.set('lyrics_font_size', val)
        if self.on_changed_callback:
            self.on_changed_callback()

    def _on_fs_switch_toggled(self, switch, state):
        if self.on_toggle_fullscreen:
            self.on_toggle_fullscreen()
        return False
