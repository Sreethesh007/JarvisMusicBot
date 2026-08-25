import os
import aiohttp
import asyncio
import re
from dotenv import load_dotenv
from pathlib import Path
import logging

class SpotifyController:
    def __init__(self):
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
        self.__client_id = os.getenv('SPOTIFY_CLIENT_ID')
        self.__client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        self.__refresh_token = os.getenv('SPOTIFY_CLIENT_REFRESH_TOKEN')
        self.__token_url = 'https://accounts.spotify.com/api/token'
        self.__access_token = None

    def __get_payload(self):
        return {
            'grant_type': 'refresh_token',
            'refresh_token': self.__refresh_token,
            'client_id': self.__client_id,
            'client_secret': self.__client_secret,
        }

    async def refresh_token(self):
        payload = self.__get_payload()
        async with aiohttp.ClientSession() as session:
            async with session.post(self.__token_url, data=payload) as response:
                if response.status == 200:
                    logging.debug("Successfully refreshed spotify token.")
                    data = await response.json()
                    self.__access_token = data['access_token']
                    return self.__access_token
                else:
                    text = await response.text()
                    logging.debug(f"Failed to refresh token: {response.status} - {text}")
                    return None

    async def get_access_token(self):
        if self.__access_token is None:
            return await self.refresh_token()
        return self.__access_token

    def extract_track_id(self, spotify_url: str) -> str:
        match = re.search(r"spotify\.com/track/([a-zA-Z0-9]+)", spotify_url)
        if match:
            return match.group(1)
        else:
            raise ValueError("Invalid Spotify track URL")

    async def getSpotifySongInfo(self, spotify_url: str) -> dict:
        track_id = self.extract_track_id(spotify_url)
        api_url = f"https://api.spotify.com/v1/tracks/{track_id}"

        async with aiohttp.ClientSession() as session:
            access_token = await self.get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            logging.debug(f"access token: {self.__access_token}")

            async def fetch_track() -> dict:
                async with session.get(api_url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            'title': data['name'],
                            'artist': data['artists'][0]['name']
                        }
                    return None

            result = await fetch_track()
            if result is not None:
                return result

            # If first attempt fails, try to refresh token
            access_token = await self.refresh_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            result = await fetch_track()

            if result is not None:
                return result
            else:
                raise Exception("Failed to fetch track info.")
            
    async def getSpotifyPlaylistInfo(self, spotify_url: str) -> list:
        playlist_match = re.search(r"spotify\.com/playlist/([a-zA-Z0-9]+)", spotify_url)
        album_match = re.search(r"spotify\.com/album/([a-zA-Z0-9]+)", spotify_url)

        if playlist_match:
            endpoint = f"https://api.spotify.com/v1/playlists/{playlist_match.group(1)}"
        elif album_match:
            endpoint = f"https://api.spotify.com/v1/albums/{album_match.group(1)}"
        else:
            raise ValueError("Invalid Spotify playlist or album URL")

        async with aiohttp.ClientSession() as session:
            access_token = await self.get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}

            async def fetch_all():
                nonlocal headers
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

                title = data.get('name', 'Unknown Playlist')
                thumbnail = data['images'][0]['url'] if data.get('images') else None
                tracks_data = data.get('tracks', {})
                items = list(tracks_data.get('items', []))
                next_url = tracks_data.get('next')

                # Paginate through remaining tracks
                while next_url:
                    async with session.get(next_url, headers=headers) as resp:
                        if resp.status == 200:
                            page_data = await resp.json()
                            items.extend(page_data.get('items', []))
                            next_url = page_data.get('next')
                        elif resp.status == 401:
                            token = await self.refresh_token()
                            headers = {"Authorization": f"Bearer {token}"}
                            continue
                        else:
                            break

                track_list = []
                is_playlist = 'playlist' in endpoint
                for item in items:
                    if not item:
                        continue
                    track_obj = item.get('track') if is_playlist else item
                    if not track_obj or not track_obj.get('name'):
                        continue
                    
                    artists = track_obj.get('artists', [])
                    artist_name = artists[0].get('name', 'Unknown Artist') if artists else 'Unknown Artist'
                    track_list.append({
                        'title': track_obj.get('name'),
                        'artist': artist_name
                    })

                return [{'title': title, 'thumbnail': thumbnail}] + track_list

            result = await fetch_all()
            if result is not None:
                return result

            # If first attempt fails, try to refresh token once
            access_token = await self.refresh_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            result = await fetch_all()

            if result is not None:
                return result
            else:
                raise Exception("Failed to fetch playlist/album info.")
