"""
Preferences Manager for Spotline Lyrics.
Persists background opacity, font size, and visual preferences to ~/.config/spotline/preferences.json.
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / '.config' / 'spotline'
CONFIG_FILE = CONFIG_DIR / 'preferences.json'

DEFAULT_PREFS = {
    'bg_opacity': 0.32,           # Background ambient glow / glass opacity (0.0 to 0.75)
    'lyrics_font_size': 24,       # Active lyric font size in px (16 to 36)
}


class Preferences:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.data = dict(DEFAULT_PREFS)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        # Migrate old glass_opacity if present
                        if 'glass_opacity' in saved and 'bg_opacity' not in saved:
                            saved['bg_opacity'] = saved['glass_opacity']
                        self.data.update(saved)
            except Exception as e:
                print(f"[Preferences] Failed to load config: {e}")

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Preferences] Failed to save config: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default if default is not None else DEFAULT_PREFS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()
