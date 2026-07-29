import asyncio
import re
import os
import shutil
import tempfile
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse, parse_qs

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
        """Return a temporary copy of the cookies file so yt-dlp doesn't overwrite the original."""
        source = None
        if self.cookies_path.exists():
            source = self.cookies_path
        elif self.data_cookies_path.exists():
            source = self.data_cookies_path

        if source is None:
            return str(self.cookies_path)

        # Copy to a temp file that yt-dlp can freely modify
        tmp = tempfile.NamedTemporaryFile(
            suffix='.txt', prefix='cookies_', delete=False
        )
        tmp.close()
        shutil.copy2(str(source), tmp.name)
        return tmp.name

    async def getVideoInfoFromURL(self, video_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            cookie_tmp = self._cookiefile()
            try:
                yt_dlp_options = {
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'noplaylist': True,
                    'cookiefile': cookie_tmp,
                    'cachedir': False,
                    'extractor_args': {'youtube': {'player_client': ['android']}},
                }
                with YoutubeDL(yt_dlp_options) as ytdlp:
                    info = ytdlp.extract_info(video_url, download=False)
                    return {
                        'title': re.sub(r'[^\w\s\-]', '', info.get('title', '')),
                        'duration': int(info.get('duration') or 0),  # in seconds
                        'thumbnail': info.get('thumbnail'),
                        'link': info.get('url'),
                    }
            finally:
                try:
                    os.unlink(cookie_tmp)
                except OSError:
                    pass

        return await loop.run_in_executor(None, extract_info)
    
    async def getVideoInfoFromQuery(self, video_query):
        loop = asyncio.get_running_loop()

        def extract_info():
            cookie_tmp = self._cookiefile()
            try:
                yt_dlp_options = {
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'noplaylist': True,
                    'cookiefile': cookie_tmp,
                    'cachedir': False,
                    'default_search': 'ytsearch',
                    'max_downloads': 1,
                    'extractor_args': {'youtube': {'player_client': ['android']}},
                }
                with YoutubeDL(yt_dlp_options) as ytdlp:
                    info = ytdlp.extract_info(f"{video_query} lyrics", download=False)
                    video = info['entries'][0] if 'entries' in info else info
                    return {
                        'title': re.sub(r'[^\w\s\-]', '', video.get('title', '')),
                        'duration': int(video.get('duration') or 0),
                        'thumbnail': video.get('thumbnail'),
                        'link': video.get('url'),
                        'url': video.get('webpage_url')
                    }
            finally:
                try:
                    os.unlink(cookie_tmp)
                except OSError:
                    pass

        return await loop.run_in_executor(None, extract_info)
    
    async def getSearchResults(self, video_query):
        loop = asyncio.get_running_loop()

        def extract_info():
            cookie_tmp = self._cookiefile()
            try:
                yt_dlp_options = {
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'noplaylist': True,
                    'cookiefile': cookie_tmp,
                    'cachedir': False,
                    'default_search': 'ytsearch10',
                    'ignoreerrors': True,
                    'extract_flat': 'in_playlist',
                    'extractor_args': {'youtube': {'player_client': ['android']}},
                }
                with YoutubeDL(yt_dlp_options) as ytdlp:
                    info = ytdlp.extract_info(f"{video_query} lyrics", download=False)
                    entries = info['entries'] if 'entries' in info else [info]

                    return [
                        {
                            'title': re.sub(r'[^\w\s\-]', '', entry.get('title', '')),
                            'link': entry.get('url'),
                        }
                        for entry in entries
                    ]
            finally:
                try:
                    os.unlink(cookie_tmp)
                except OSError:
                    pass

        return await loop.run_in_executor(None, extract_info)
    
    async def getPlaylistInfo(self, playlist_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            cookie_tmp = self._cookiefile()
            try:
                yt_dlp_options = {
                    'format': 'bestaudio/best',
                    'quiet': False,
                    'extract_flat': 'in_playlist',
                    'cookiefile': cookie_tmp,
                    'cachedir': False,
                    'extractor_args': {'youtube': {'player_client': ['android']}},
                }
                with YoutubeDL(yt_dlp_options) as ytdlp:
                    playlist = ytdlp.extract_info(playlist_url, download=False)
                    metadata = {
                        'playlist_name': re.sub(r'[^\w\s\-]', '', playlist.get('title', 'Unknown Playlist')),
                        'song_count': len(playlist.get('entries', [])),
                        'thumbnail': playlist.get('thumbnail') or (playlist.get('thumbnails', [{}])[0].get('url') if 'thumbnails' in playlist else None)
                    }
                    song_urls = [{'url': entry.get('url')} for entry in playlist.get('entries', []) if entry.get('url')]
                    return [metadata] + song_urls
            finally:
                try:
                    os.unlink(cookie_tmp)
                except OSError:
                    pass

        return await loop.run_in_executor(None, extract_info)
    
    async def getVideoInfoFromPlaylist(self, playlist_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            cookie_tmp = self._cookiefile()
            try:
                yt_dlp_options = {
                    'format': 'bestaudio/best',
                    'quiet': False,
                    # 'extract_flat': 'in_playlist',
                    'cookiefile': cookie_tmp,
                    'cachedir': False,
                    'ignoreerrors': True,
                    'extractor_args': {'youtube': {'player_client': ['android']}},
                }
                with YoutubeDL(yt_dlp_options) as ytdlp:
                    playlist = ytdlp.extract_info(playlist_url, download=False)
                    return [{
                        'title': re.sub(r'[^\w\s\-]', '', entry.get('title', '')),
                        'duration': int(entry.get('duration') or 0),
                        'thumbnail': entry.get('thumbnail'),
                        'link': entry.get('url'),
                        'url': entry.get('webpage_url')
                    } for entry in playlist.get('entries', [])
                      if entry
                    ]
            finally:
                try:
                    os.unlink(cookie_tmp)
                except OSError:
                    pass
                

        return await loop.run_in_executor(None, extract_info)
