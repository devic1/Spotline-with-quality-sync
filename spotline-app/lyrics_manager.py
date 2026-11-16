"""
Lyrics Manager using LRCLIB v2 (Beta) API.
Handles track searching, duration-matched candidate selection,
individual lyrics retrieval via /api/get/{id}, deduplication of identical lyrics,
and script/language detection.
"""

import os
import re
import json
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


USER_AGENT = 'SpotlineLyrics/2.0 (Ubuntu; Linux; +https://github.com/devic1/Spotline-with-quality-sync)'
BASE_URL = 'https://lrclib.net'
CACHE_DIR = Path.home() / '.cache' / 'spotline' / 'lyrics'


def format_duration_seconds(seconds):
    if not seconds or seconds <= 0:
        return "--:--"
    total_sec = round(seconds)
    m = total_sec // 60
    s = total_sec % 60
    return f"{m}:{s:02d}"


def clean_title(title):
    if not title:
        return ""
    t = re.sub(r'\s*-\s*(Remastered|Remaster|Live|Mono|Stereo|Radio Edit|Single Version|Bonus Track|Male|Female).*$', '', title, flags=re.IGNORECASE)
    t = re.sub(r'\s*\(feat\..*?\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*\[feat\..*?\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*\(From \".*?\"\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*\(.*?\)', '', t)
    return t.strip()


def detect_language(text):
    """
    Detects major writing system / language used in lyrics.
    Returns: 'Tamil', 'Hindi', 'Telugu', 'Malayalam', 'Kannada', 'English', etc.
    """
    if not text:
        return 'Unknown'

    counts = {
        'Tamil': len(re.findall(r'[\u0B80-\u0BFF]', text)),
        'Hindi': len(re.findall(r'[\u0900-\u097F]', text)),
        'Telugu': len(re.findall(r'[\u0C00-\u0C7F]', text)),
        'Malayalam': len(re.findall(r'[\u0D00-\u0D7F]', text)),
        'Kannada': len(re.findall(r'[\u0C80-\u0CFF]', text)),
        'Bengali': len(re.findall(r'[\u0980-\u09FF]', text)),
        'Japanese': len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF]', text)),
        'Korean': len(re.findall(r'[\uAC00-\uD7AF]', text)),
        'Chinese': len(re.findall(r'[\u4E00-\u9FFF]', text)),
        'Arabic': len(re.findall(r'[\u0600-\u06FF]', text)),
        'English': len(re.findall(r'[a-zA-Z]', text)),
    }

    top_lang, top_count = max(counts.items(), key=lambda x: x[1])
    if top_count < 8:
        return 'English' if counts['English'] > 0 else 'Unknown'
    return top_lang


def parse_lrc(lrc_text):
    """
    Parses LRC format: [mm:ss.xx] lyric text
    Returns sorted list of dicts: [{'time_ms': int, 'text': str}]
    """
    if not lrc_text:
        return []

    lines = []
    pattern = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')

    for raw_line in lrc_text.splitlines():
        match = pattern.match(raw_line.strip())
        if match:
            minutes = int(match.group(1))
            seconds = float(match.group(2))
            text = match.group(3).strip()

            time_ms = int((minutes * 60 + seconds) * 1000)
            lines.append({'time_ms': time_ms, 'text': text})

    lines.sort(key=lambda x: x['time_ms'])
    return lines


class LyricsManager:
    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.memory_cache = {}

    def _http_get(self, url, timeout=8):
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': USER_AGENT,
                'Accept': 'application/json'
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
        return None

    def search_v2(self, track_name, artist_name=None, album_name=None):
        """
        Query /api/v2/search with structured or general query.
        Returns list of summary objects.
        """
        params = {}
        if track_name:
            params['track_name'] = track_name
        if artist_name and artist_name != 'Unknown Artist':
            params['artist_name'] = artist_name
        if album_name and album_name != 'Unknown Album':
            params['album_name'] = album_name

        query_str = urllib.parse.urlencode(params)
        url = f"{BASE_URL}/api/v2/search?{query_str}"

        try:
            results = self._http_get(url)
            if results and isinstance(results, list) and len(results) > 0:
                return results
        except Exception as e:
            print(f"[LyricsManager] Structured search failed: {e}")

        # Fallback to general keyword search 'q'
        try:
            q_term = f"{track_name} {artist_name or ''}".strip()
            q_url = f"{BASE_URL}/api/v2/search?q={urllib.parse.quote(q_term)}"
            results = self._http_get(q_url)
            if results and isinstance(results, list) and len(results) > 0:
                return results
        except Exception as e:
            print(f"[LyricsManager] General 'q' search failed: {e}")

        # Fallback to cleaned track title
        cleaned = clean_title(track_name)
        if cleaned and cleaned != track_name:
            try:
                q_url = f"{BASE_URL}/api/v2/search?q={urllib.parse.quote(cleaned)}"
                results = self._http_get(q_url)
                if results and isinstance(results, list) and len(results) > 0:
                    return results
            except Exception as e:
                print(f"[LyricsManager] Cleaned title search failed: {e}")

        return []

    def get_lyrics_by_id(self, track_id):
        """
        Fetch full lyrics record by ID from /api/get/{id}.
        """
        cache_file = CACHE_DIR / f"{track_id}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

        url = f"{BASE_URL}/api/get/{track_id}"
        try:
            data = self._http_get(url)
            if data and isinstance(data, dict):
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f)
                except Exception:
                    pass
                return data
        except Exception as e:
            print(f"[LyricsManager] Failed to get lyrics for id {track_id}: {e}")

        return None

    def find_best_lyrics(self, track_name, artist_name=None, duration_seconds=None):
        """
        Full v2 workflow:
        1. Search /api/v2/search
        2. Filter ±5s duration drift & sort by closest duration match
        3. Prioritize hasSyncedLyrics == True
        4. Call /api/get/{id} to retrieve full lyrics
        5. Return parsed lyrics dict
        """
        cache_key = f"{track_name}___{artist_name}___{duration_seconds}"
        if cache_key in self.memory_cache:
            return self.memory_cache[cache_key]

        records = self.search_v2(track_name, artist_name)
        if not records:
            return None

        candidates = records
        if duration_seconds and duration_seconds > 0:
            drifted = [
                r for r in records
                if isinstance(r.get('duration'), (int, float)) and abs(r['duration'] - duration_seconds) <= 5
            ]
            if drifted:
                drifted.sort(key=lambda r: abs(r['duration'] - duration_seconds))
                candidates = drifted

        # Pick candidate with hasSyncedLyrics first
        selected_id = None
        for cand in candidates:
            if cand.get('hasSyncedLyrics'):
                selected_id = cand['id']
                break

        # Fallback to plain lyrics or first result if no synced
        if not selected_id and candidates:
            for cand in candidates:
                if cand.get('hasPlainLyrics'):
                    selected_id = cand['id']
                    break
            if not selected_id:
                selected_id = candidates[0].get('id')

        if not selected_id:
            return None

        full_record = self.get_lyrics_by_id(selected_id)
        if not full_record:
            return None

        result = self._process_record(full_record)
        self.memory_cache[cache_key] = result
        return result

    def _process_record(self, record):
        synced_raw = record.get('syncedLyrics') or ''
        plain_raw = record.get('plainLyrics') or ''
        parsed_synced = parse_lrc(synced_raw)
        detected_lang = detect_language(synced_raw or plain_raw)

        return {
            'id': record.get('id'),
            'track_name': record.get('trackName') or record.get('name'),
            'artist_name': record.get('artistName'),
            'album_name': record.get('albumName'),
            'duration': record.get('duration'),
            'instrumental': record.get('instrumental', False),
            'has_synced': bool(synced_raw and len(parsed_synced) > 0),
            'has_plain': bool(plain_raw and len(plain_raw.strip()) > 0),
            'synced_lines': parsed_synced,
            'plain_text': plain_raw,
            'language': detected_lang,
        }

    def search_top_candidates(self, query_or_title, artist=None, limit=10):
        """
        Returns unique, deduplicated candidates for 'Change Lyrics'.
        Skips results whose lyrics content inside is identical.
        Also detects the major language of each unique version.
        """
        records = []
        if artist:
            records = self.search_v2(query_or_title, artist)
        if not records:
            # Try raw query or cleaned title
            clean_q = clean_title(query_or_title)
            for q_try in [query_or_title, clean_q]:
                if not q_try:
                    continue
                try:
                    url = f"{BASE_URL}/api/v2/search?q={urllib.parse.quote(q_try)}"
                    res = self._http_get(url)
                    if res and isinstance(res, list) and len(res) > 0:
                        records = res
                        break
                except Exception:
                    pass

        if not records:
            return []

        # Fetch candidate content concurrently to deduplicate identical lyrics
        raw_candidates = records[:20]

        def fetch_full(item):
            try:
                full_rec = self.get_lyrics_by_id(item['id'])
                if full_rec:
                    content = full_rec.get('syncedLyrics') or full_rec.get('plainLyrics') or ''
                    # Normalize text: strip timestamps and whitespace for content fingerprinting
                    norm_content = re.sub(r'\[.*?\]|\s+|[^\w]', '', content).lower()
                    h = hashlib.md5(norm_content.encode('utf-8')).hexdigest() if norm_content else None
                    item['full_data'] = full_rec
                    item['content_hash'] = h
                    item['lyrics_text'] = content
                    item['lang'] = detect_language(content)
                else:
                    item['full_data'] = None
                    item['content_hash'] = None
                    item['lyrics_text'] = ''
                    item['lang'] = 'Unknown'
            except Exception:
                item['full_data'] = None
                item['content_hash'] = None
                item['lyrics_text'] = ''
                item['lang'] = 'Unknown'
            return item

        with ThreadPoolExecutor(max_workers=8) as executor:
            fetched_items = list(executor.map(fetch_full, raw_candidates))

        seen_hashes = set()
        deduped = []

        for item in fetched_items:
            h = item.get('content_hash')
            if h:
                # If lyrics content is exactly the same, skip duplicate
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

            dur_s = item.get('duration', 0)
            lang = item.get('lang', 'English')
            if lang == 'Unknown':
                lang = 'English'

            deduped.append({
                'id': item.get('id'),
                'track_name': item.get('trackName', 'Unknown'),
                'artist_name': item.get('artistName', 'Unknown'),
                'album_name': item.get('albumName', ''),
                'duration_str': format_duration_seconds(dur_s),
                'duration': dur_s,
                'has_synced': bool(item.get('hasSyncedLyrics')),
                'has_plain': bool(item.get('hasPlainLyrics')),
                'instrumental': bool(item.get('instrumental')),
                'language': lang,
                'full_data': item.get('full_data'),
            })

            if len(deduped) >= limit:
                break

        return deduped
