import asyncio
import re
import os
import logging
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger('ytdlp')

class YtDlpLogger:
    """Routes yt-dlp's internal messages through Python logging."""
    def debug(self, msg):
        # yt-dlp sends download progress and verbose info as debug
        if msg.startswith('[debug] '):
            logger.debug(msg)
        else:
            logger.info(msg)

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)

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
        if self.cookies_path.exists():
            return str(self.cookies_path)
        if self.data_cookies_path.exists():
            return str(self.data_cookies_path)
        return str(self.cookies_path)

    async def getVideoInfoFromURL(self, video_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            yt_dlp_options = {
                'format': 'bestaudio/best',
                'quiet': False,
                'verbose': True,
                'noplaylist': True,
                'cookiefile': self._cookiefile(),
                'cachedir': False,
                'js_runtimes': {'deno': {}},
                'logger': YtDlpLogger(),
            }
            with YoutubeDL(yt_dlp_options) as ytdlp:
                info = ytdlp.extract_info(video_url, download=False)
                raw_title = info.get('title') or 'Unknown Track'
                clean_title = re.sub(r'[^\w\s\-]', '', raw_title).strip() or 'Unknown Track'
                return {
                    'title': clean_title,
                    'duration': int(info.get('duration') or 0),  # in seconds
                    'thumbnail': info.get('thumbnail'),
                    'link': info.get('url'),
                    'http_headers': info.get('http_headers', {}),
                }

        return await loop.run_in_executor(None, extract_info)
    
    async def getVideoInfoFromQuery(self, video_query):
        loop = asyncio.get_running_loop()

        def extract_info():
            yt_dlp_options = {
                'format': 'bestaudio/best',
                'quiet': False,
                'verbose': True,
                'noplaylist': True,
                'cookiefile': self._cookiefile(),
                'cachedir': False,
                'default_search': 'ytsearch',
                'max_downloads': 1,
                'js_runtimes': {'deno': {}},
                'logger': YtDlpLogger(),
            }
            with YoutubeDL(yt_dlp_options) as ytdlp:
                info = ytdlp.extract_info(f"{video_query} lyrics", download=False)
                video = info['entries'][0] if 'entries' in info else info
                raw_title = video.get('title') or 'Unknown Track'
                clean_title = re.sub(r'[^\w\s\-]', '', raw_title).strip() or 'Unknown Track'
                return {
                    'title': clean_title,
                    'duration': int(video.get('duration') or 0),
                    'thumbnail': video.get('thumbnail'),
                    'link': video.get('url'),
                    'url': video.get('webpage_url'),
                    'http_headers': video.get('http_headers', {}),
                }

        return await loop.run_in_executor(None, extract_info)
    
    async def getSearchResults(self, video_query):
        loop = asyncio.get_running_loop()

        def extract_info():
            yt_dlp_options = {
                'format': 'bestaudio/best',
                'quiet': False,
                'verbose': True,
                'noplaylist': True,
                'cookiefile': self._cookiefile(),
                'cachedir': False,
                'default_search': 'ytsearch10',
                'ignoreerrors': True,
                'extract_flat': 'in_playlist',
                'js_runtimes': {'deno': {}},
                'logger': YtDlpLogger(),
            }
            with YoutubeDL(yt_dlp_options) as ytdlp:
                info = ytdlp.extract_info(f"{video_query} lyrics", download=False)
                entries = info['entries'] if 'entries' in info else [info]

                return [
                    {
                        'title': re.sub(r'[^\w\s\-]', '', entry.get('title') or '').strip() or 'Unknown Track',
                        'link': entry.get('url'),
                    }
                    for entry in entries if entry
                ]

        return await loop.run_in_executor(None, extract_info)
    
    async def getPlaylistInfo(self, playlist_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            yt_dlp_options = {
                'format': 'bestaudio/best',
                'quiet': False,
                'verbose': True,
                'extract_flat': 'in_playlist',
                'cookiefile': self._cookiefile(),
                'cachedir': False,
                'js_runtimes': {'deno': {}},
                'logger': YtDlpLogger(),
            }
            with YoutubeDL(yt_dlp_options) as ytdlp:
                playlist = ytdlp.extract_info(playlist_url, download=False)
                entries = playlist.get('entries', []) or []
                raw_playlist_name = playlist.get('title') or 'Unknown Playlist'
                clean_playlist_name = re.sub(r'[^\w\s\-]', '', raw_playlist_name).strip() or 'Unknown Playlist'
                metadata = {
                    'playlist_name': clean_playlist_name,
                    'song_count': len(entries),
                    'thumbnail': playlist.get('thumbnail') or (playlist.get('thumbnails', [{}])[0].get('url') if playlist.get('thumbnails') else None)
                }

                song_entries = []
                for entry in entries:
                    if not entry:
                        continue
                    url = entry.get('url') or entry.get('webpage_url')
                    if url and not url.startswith('http'):
                        url = f"https://www.youtube.com/watch?v={url}"
                    elif not url and entry.get('id'):
                        url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                    
                    if not url:
                        continue

                    raw_title = entry.get('title') or 'Unknown Track'
                    clean_title = re.sub(r'[^\w\s\-]', '', raw_title).strip() or 'Unknown Track'
                    thumb = entry.get('thumbnail') or (entry.get('thumbnails', [{}])[0].get('url') if entry.get('thumbnails') else None)
                    song_entries.append({
                        'title': clean_title,
                        'url': url,
                        'duration': int(entry.get('duration') or 0),
                        'thumbnail': thumb or metadata['thumbnail']
                    })

                return [metadata] + song_entries

        return await loop.run_in_executor(None, extract_info)
    
    async def getVideoInfoFromPlaylist(self, playlist_url):
        loop = asyncio.get_running_loop()

        def extract_info():
            yt_dlp_options = {
                'format': 'bestaudio/best',
                'quiet': False,
                'verbose': True,
                # 'extract_flat': 'in_playlist',
                'cookiefile': self._cookiefile(),
                'cachedir': False,
                'ignoreerrors': True,
                'js_runtimes': {'deno': {}},
                'logger': YtDlpLogger(),
            }
            with YoutubeDL(yt_dlp_options) as ytdlp:
                playlist = ytdlp.extract_info(playlist_url, download=False)
                return [{
                    'title': re.sub(r'[^\w\s\-]', '', entry.get('title') or '').strip() or 'Unknown Track',
                    'duration': int(entry.get('duration') or 0),
                    'thumbnail': entry.get('thumbnail'),
                    'link': entry.get('url'),
                    'url': entry.get('webpage_url'),
                    'http_headers': entry.get('http_headers', {}),
                } for entry in playlist.get('entries', [])
                  if entry
                ]
                

        return await loop.run_in_executor(None, extract_info)
