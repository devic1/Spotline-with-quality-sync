"""
Spotify MPRIS DBus Client
Handles metadata tracking, playback state, and playback controls.
"""

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib


SPOTIFY_BUS_NAME = 'org.mpris.MediaPlayer2.spotify'
MPRIS_PLAYER_PATH = '/org/mpris/MediaPlayer2'
MPRIS_PLAYER_INTERFACE = 'org.mpris.MediaPlayer2.Player'
DBUS_PROPERTIES_INTERFACE = 'org.freedesktop.DBus.Properties'


class SpotifyClient:
    def __init__(self, on_track_changed=None, on_status_changed=None, on_running_changed=None):
        self.on_track_changed = on_track_changed
        self.on_status_changed = on_status_changed
        self.on_running_changed = on_running_changed

        self.bus = None
        self.player_proxy = None
        self.props_proxy = None
        self.prop_changed_id = None
        self.watcher_id = None
        self.is_running = False
        self.current_metadata = {}
        self.current_status = 'Stopped'

        self._setup_bus()

    def _setup_bus(self):
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

            # Check if Spotify is already running
            reply = self.bus.call_sync(
                'org.freedesktop.DBus',
                '/org/freedesktop/DBus',
                'org.freedesktop.DBus',
                'NameHasOwner',
                GLib.Variant('(s)', (SPOTIFY_BUS_NAME,)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            has_owner = reply.get_child_value(0).get_boolean()
            if has_owner:
                self.is_running = True
                self._connect_proxies()
                if self.on_running_changed:
                    self.on_running_changed(True)
                self._update_all()

            self.watcher_id = Gio.bus_watch_name(
                Gio.BusType.SESSION,
                SPOTIFY_BUS_NAME,
                Gio.BusNameWatcherFlags.NONE,
                self._on_name_appeared,
                self._on_name_vanished
            )
        except Exception as e:
            print(f"[SpotifyClient] Failed to setup bus: {e}")

    def _on_name_appeared(self, connection, name, name_owner):
        self.is_running = True
        self._connect_proxies()
        if self.on_running_changed:
            self.on_running_changed(True)
        self._update_all()

    def _on_name_vanished(self, connection, name):
        self.is_running = False
        self._disconnect_proxies()
        self.current_metadata = {}
        self.current_status = 'Stopped'
        if self.on_running_changed:
            self.on_running_changed(False)
        if self.on_track_changed:
            self.on_track_changed(None)
        if self.on_status_changed:
            self.on_status_changed('Stopped')

    def _connect_proxies(self):
        try:
            self.player_proxy = Gio.DBusProxy.new_sync(
                self.bus,
                Gio.DBusProxyFlags.NONE,
                None,
                SPOTIFY_BUS_NAME,
                MPRIS_PLAYER_PATH,
                MPRIS_PLAYER_INTERFACE,
                None
            )
            self.props_proxy = Gio.DBusProxy.new_sync(
                self.bus,
                Gio.DBusProxyFlags.NONE,
                None,
                SPOTIFY_BUS_NAME,
                MPRIS_PLAYER_PATH,
                DBUS_PROPERTIES_INTERFACE,
                None
            )
            self.prop_changed_id = self.player_proxy.connect(
                'g-properties-changed',
                self._on_properties_changed
            )
        except Exception as e:
            print(f"[SpotifyClient] Error connecting proxies: {e}")

    def _disconnect_proxies(self):
        if self.player_proxy and self.prop_changed_id:
            try:
                self.player_proxy.disconnect(self.prop_changed_id)
            except Exception:
                pass
            self.prop_changed_id = None
        self.player_proxy = None
        self.props_proxy = None

    def _on_properties_changed(self, proxy, changed_properties, invalidated_properties):
        changed = changed_properties.unpack()
        if 'Metadata' in changed:
            self._update_metadata(changed['Metadata'])
        if 'PlaybackStatus' in changed:
            status = changed['PlaybackStatus']
            self.current_status = status
            if self.on_status_changed:
                self.on_status_changed(status)

    def _update_all(self):
        if not self.player_proxy:
            return
        try:
            meta_prop = self.player_proxy.get_cached_property('Metadata')
            if meta_prop:
                self._update_metadata(meta_prop.unpack())

            status_prop = self.player_proxy.get_cached_property('PlaybackStatus')
            if status_prop:
                status = status_prop.unpack()
                self.current_status = status
                if self.on_status_changed:
                    self.on_status_changed(status)
        except Exception as e:
            print(f"[SpotifyClient] Failed to read initial properties: {e}")

    def _update_metadata(self, meta_dict):
        if not meta_dict:
            self.current_metadata = {}
            if self.on_track_changed:
                self.on_track_changed(None)
            return

        title = meta_dict.get('xesam:title', 'Unknown Title')
        artists = meta_dict.get('xesam:artist', [])
        artist = artists[0] if artists else 'Unknown Artist'
        album = meta_dict.get('xesam:album', 'Unknown Album')
        art_url = meta_dict.get('mpris:artUrl', '')
        track_id = meta_dict.get('mpris:trackid', '')
        length_us = meta_dict.get('mpris:length', 0)
        length_s = round(length_us / 1000000) if length_us else 0

        new_meta = {
            'title': title,
            'artist': artist,
            'album': album,
            'art_url': art_url,
            'track_id': track_id,
            'length_us': length_us,
            'length_s': length_s,
        }

        # Check if title or artist changed
        prev_title = self.current_metadata.get('title')
        prev_artist = self.current_metadata.get('artist')
        self.current_metadata = new_meta

        if self.on_track_changed:
            self.on_track_changed(new_meta)

    def get_position_ms(self):
        if not self.props_proxy:
            return 0
        try:
            pos_var = self.props_proxy.call_sync(
                'Get',
                GLib.Variant('(ss)', (MPRIS_PLAYER_INTERFACE, 'Position')),
                Gio.DBusCallFlags.NONE,
                250,
                None
            )
            pos_us = pos_var.get_child_value(0).get_variant().get_int64()
            return pos_us / 1000.0
        except Exception:
            return 0

    def play_pause(self):
        if self.player_proxy:
            try:
                self.player_proxy.call('PlayPause', None, Gio.DBusCallFlags.NONE, -1, None, None)
            except Exception as e:
                print(f"[SpotifyClient] PlayPause error: {e}")

    def previous(self):
        if self.player_proxy:
            try:
                self.player_proxy.call('Previous', None, Gio.DBusCallFlags.NONE, -1, None, None)
            except Exception as e:
                print(f"[SpotifyClient] Previous error: {e}")

    def next(self):
        if self.player_proxy:
            try:
                self.player_proxy.call('Next', None, Gio.DBusCallFlags.NONE, -1, None, None)
            except Exception as e:
                print(f"[SpotifyClient] Next error: {e}")

    def set_position(self, position_ms):
        track_id = self.current_metadata.get('track_id')
        if self.player_proxy and track_id:
            try:
                position_us = int(position_ms * 1000)
                self.player_proxy.call(
                    'SetPosition',
                    GLib.Variant('(ox)', (track_id, position_us)),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                    None
                )
            except Exception as e:
                print(f"[SpotifyClient] SetPosition error: {e}")
