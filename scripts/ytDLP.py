import asyncio
import re
import os
import time
import logging
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

def getSongExpiration(url: str) -> int | None:
    parsed = urlparse(url)

    # Case 1: Normal query string (normal video URL)
    if parsed.query:
        params = parse_qs(parsed.query)
        expire = params.get('expire') or params.get('expires')
        if expire:
            return int(expire[0])

    # Case 2: Path-based (stream URL)
    match = re.search(r'/expire/(\d+)', parsed.path)
    if match:
        return int(match.group(1))

    return None

class VideoSearcher():
    def __init__(self):
        root_dir = Path(__file__).resolve().parent.parent
        self.cookies_path = root_dir / "cookies.txt"
        self.data_cookies_path = root_dir / "data" / "cookies.txt"

    def _cookiefile(self):
        """Return the path to the cookies file, or None if no file exists."""
        if self.cookies_path.exists():
            return str(self.cookies_path)
        if self.data_cookies_path.exists():
            return str(self.data_cookies_path)
        return None

    def _has_valid_cookies(self):
        """Check if a cookies file exists and has non-expired SIDCC cookies."""
        cookie_path = self._cookiefile()
        if not cookie_path or not Path(cookie_path).exists():
            return False
        try:
            with open(cookie_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Check SIDCC expiry as a health indicator (most short-lived cookie)
            for line in content.splitlines():
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.split('\t')
                if len(parts) >= 7 and parts[5] in ('SIDCC', '__Secure-1PSIDCC', '__Secure-3PSIDCC'):
                    expiry = int(parts[4])
                    if expiry > 0 and expiry <= int(time.time()):
                        logger.warning(
                            "⚠️  YouTube cookies appear EXPIRED (SIDCC expiry: %s). "
                            "Re-export cookies using the incognito + robots.txt method.",
                            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry))
                        )
                        return False
            return True
        except Exception as e:
            logger.warning("Could not validate cookies file: %s", e)
            return False

    def _base_options(self, **extra):
        """Build base yt-dlp options without cookies."""
        opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'cachedir': False,
            'js_runtimes': {'deno': {}},
            'sleep_interval_requests': 1,  # rate-limit to reduce bot detection
        }
        opts.update(extra)
        return opts

    def _options_with_cookies(self, base_opts: dict) -> dict:
        """Clone options and add cookiefile if available."""
        opts = dict(base_opts)
        cookie_path = self._cookiefile()
        if cookie_path:
            opts['cookiefile'] = cookie_path
        return opts

    def _extract_with_fallback(self, query: str, base_opts: dict, process_fn):
        """
        Extraction strategy:
          - If cookies.txt exists → always use cookies (stream URLs require auth
            to be playable by FFmpeg). Raise on failure so the error is visible.
          - If no cookies.txt → try without cookies (works for some public videos).
        
        process_fn: callable that takes the raw yt-dlp info dict and returns
                     the desired result structure.
        """
        cookie_path = self._cookiefile()
        has_cookies = cookie_path is not None

        if has_cookies:
            # --- Use cookies (original behavior) ---
            if not self._has_valid_cookies():
                logger.warning(
                    "⚠️  Cookies may be expired. Consider re-exporting cookies "
                    "(incognito + robots.txt method)."
                )

            opts_with_cookies = self._options_with_cookies(base_opts)
            with YoutubeDL(opts_with_cookies) as ytdlp:
                info = ytdlp.extract_info(query, download=False)
                result = process_fn(info)
                logger.debug("Extraction succeeded with cookies.")
                return result
        else:
            # --- No cookies file at all, try without ---
            logger.info("No cookies.txt found — attempting cookieless extraction.")
            with YoutubeDL(base_opts) as ytdlp:
                info = ytdlp.extract_info(query, download=False)
                result = process_fn(info)
                logger.info("Cookieless extraction succeeded.")
                return result

    async def getVideoInfoFromURL(self, video_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            base_opts = self._base_options(noplaylist=True)

            def process(info):
                return {
                    'title': re.sub(r'[^\w\s\-]', '', info.get('title', '')),
                    'duration': int(info.get('duration') or 0),  # in seconds
                    'thumbnail': info.get('thumbnail'),
                    'link': info.get('url'),
                }

            return self._extract_with_fallback(video_url, base_opts, process)

        return await loop.run_in_executor(None, extract_info)
    
    async def getVideoInfoFromQuery(self, video_query):
        loop = asyncio.get_running_loop()

        def extract_info():
            base_opts = self._base_options(
                noplaylist=True,
                default_search='ytsearch',
                max_downloads=1,
            )

            def process(info):
                video = info['entries'][0] if 'entries' in info else info
                return {
                    'title': re.sub(r'[^\w\s\-]', '', video.get('title', '')),
                    'duration': int(video.get('duration') or 0),
                    'thumbnail': video.get('thumbnail'),
                    'link': video.get('url'),
                    'url': video.get('webpage_url')
                }

            return self._extract_with_fallback(f"{video_query} lyrics", base_opts, process)

        return await loop.run_in_executor(None, extract_info)
    
    async def getSearchResults(self, video_query):
        loop = asyncio.get_running_loop()

        def extract_info():
            base_opts = self._base_options(
                noplaylist=True,
                default_search='ytsearch10',
                ignoreerrors=True,
                extract_flat='in_playlist',
            )

            def process(info):
                entries = info['entries'] if 'entries' in info else [info]
                return [
                    {
                        'title': re.sub(r'[^\w\s\-]', '', entry.get('title', '')),
                        'link': entry.get('url'),
                    }
                    for entry in entries
                ]

            return self._extract_with_fallback(f"{video_query} lyrics", base_opts, process)

        return await loop.run_in_executor(None, extract_info)
    
    async def getPlaylistInfo(self, playlist_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            base_opts = self._base_options(
                quiet=False,
                extract_flat='in_playlist',
            )

            def process(playlist):
                metadata = {
                    'playlist_name': re.sub(r'[^\w\s\-]', '', playlist.get('title', 'Unknown Playlist')),
                    'song_count': len(playlist.get('entries', [])),
                    'thumbnail': playlist.get('thumbnail') or (playlist.get('thumbnails', [{}])[0].get('url') if 'thumbnails' in playlist else None)
                }
                song_urls = [{'url': entry.get('url')} for entry in playlist.get('entries', []) if entry.get('url')]
                return [metadata] + song_urls

            return self._extract_with_fallback(playlist_url, base_opts, process)

        return await loop.run_in_executor(None, extract_info)
    
    async def getVideoInfoFromPlaylist(self, playlist_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            base_opts = self._base_options(
                quiet=False,
                # 'extract_flat': 'in_playlist',
                ignoreerrors=True,
            )

            def process(playlist):
                return [{
                    'title': re.sub(r'[^\w\s\-]', '', entry.get('title', '')),
                    'duration': int(entry.get('duration') or 0),
                    'thumbnail': entry.get('thumbnail'),
                    'link': entry.get('url'),
                    'url': entry.get('webpage_url')
                } for entry in playlist.get('entries', [])
                  if entry
                ]

            return self._extract_with_fallback(playlist_url, base_opts, process)

        return await loop.run_in_executor(None, extract_info)
