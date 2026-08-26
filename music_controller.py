import discord
import io
import os
import re
import asyncio
import time
import random
import threading
from discord import app_commands
from discord.ext import commands, voice_recv
from typing import Optional, Tuple
import speech_recognition as sr
import logging
import edge_tts
from management.banned_users import BannedUsers
from management.bot_keywords import BotKeywords
from management.vip_users import VIPUsers
from scripts.ytDLP import VideoSearcher, getSongExpiration
from embed_views.music_buttons import MusicButtons
from scripts.spotify import SpotifyController
from management.nlp_processor import NLPProcessor
            

class Song:
    def __init__(self, title: str, url: str = None, link: str = None, thumbnail: str = None, duration: int = 0, user: discord.User = None, isFile: bool = False, http_headers: dict = None, source_command: str = None, is_lazy: bool = False, query: str = None):
        self.title = title
        self.url = url
        self.link = link
        self.thumbnail = thumbnail
        self.duration = duration
        self.user = user
        self.isFile = isFile
        self.http_headers = http_headers or {}
        self.source_command = source_command or f"Requested by {user.display_name if user else 'Unknown'}"
        self.is_lazy = is_lazy
        self.query = query

class MusicController:
    # Constructor
    def __init__(self, client: discord.Client, guild: discord.Guild):
        logging.info(f"Created Music Controller for: {guild}")
        self.client = client
        self.guild = guild
        self.spotify = SpotifyController()
        # self.loop = asyncio.get_running_loop() # apparently not necessary, use self.client.loop
        self.voiceChannel = None
        self.textChannel = None
        self.transcriptionChannel = None
        self.songQueue = []
        self.isLooping = False
        self.isMajorityVote = False
        self.start_time = None
        self.pause_start = None
        self.pause_duration = 0
        self.isPlayingTTS = False
        self.cached_bot_keywords = None
        self.bot_keywords_last_mtime = 0
        self.nlp_processor = NLPProcessor()
        self.current_context = None
        self.previous_song = None

    async def _get_bot_keywords(self):
        botKeywordsClass = BotKeywords()
        try:
            current_mtime = botKeywordsClass.bot_keywords_file.stat().st_mtime
        except OSError:
            current_mtime = 0

        if self.cached_bot_keywords is None or self.bot_keywords_last_mtime != current_mtime:
            self.cached_bot_keywords = await botKeywordsClass.loadBotKeywords()
            self.bot_keywords_last_mtime = current_mtime

        return self.cached_bot_keywords

    async def generate_tts(self, text: str):
        communicate = edge_tts.Communicate(text, "en-IN-PrabhatNeural")
        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])
        audio_buffer.seek(0)
        return audio_buffer

    # function to check if the bot is currently connected to a voice channel
    def isConnectedToVC(self):
        voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
        if voice_client and voice_client.is_connected():
            logging.debug(f"{self.guild.name} Music Controller is connected to a voice channel.")
            return True
        else:
            logging.debug(f"{self.guild.name} Music Controller is not connected to any voice channel.")
            return False
        
    # function to get the voice and text channel
    def getVideoAndTextChannel(self) -> Tuple[discord.VoiceChannel, discord.TextChannel]:
        return self.voiceChannel, self.textChannel
    
    # function to get the song queue
    def getSongQueue(self) -> list:
        return self.songQueue
    
    # function to get isMajorityVote
    def getIsMajorityVote(self) -> bool:
        return self.isMajorityVote
    
    async def getCurrentDuration(self) -> str:
        def format_duration(seconds: int) -> str:
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            if hours > 0:
                return f"{hours:02}:{minutes:02}:{secs:02}"
            else:
                return f"{minutes:02}:{secs:02}"
            
        if self.songQueue:
            songDuration = self.songQueue[0].duration
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            if voice_client.is_paused():
                start = int(self.pause_start - self.start_time - self.pause_duration)
                if songDuration == 0:
                    return f"*{format_duration(start)}* into the stream."
                return f"*{format_duration(start)}* **/** *{format_duration(songDuration)}*"
            start = int(int(time.time()) - self.start_time - self.pause_duration)
            if songDuration == 0:
                return f"*{format_duration(start)}* into the stream."
            return f"*{format_duration(start)}* **/** *{format_duration(songDuration)}*"
        return "No song is currently being played."
        
    # function to set the transcription channel
    async def setTranscriptionChannel(self, transcriptionChannel: discord.TextChannel) -> discord.TextChannel:
        logging.debug("Starting /transcribe function")        
        self.transcriptionChannel = transcriptionChannel      
        return self.transcriptionChannel
    
    # function to set looping
    async def setLooping(self) -> bool:
        logging.debug("Starting /loop function")        
        self.isLooping = not self.isLooping
        return self.isLooping
    
    # function to set majority vote
    async def setMajorityVote(self) -> bool:
        logging.debug("Starting /majorvote function")        
        self.isMajorityVote = not self.isMajorityVote
        return self.isMajorityVote
    
    # function to skip current song
    async def shuffleQueue(self):
        logging.debug("Starting /shuffle function")   
        if self.isConnectedToVC():
            if len(self.songQueue) <= 1:
                return
            # Preserve the first song
            first_song = self.songQueue[0]
            rest = self.songQueue[1:]
            # Shuffle the remaining songs
            random.shuffle(rest)
            # Reassign the shuffled list back to the queue
            self.songQueue[:] = [first_song] + rest
        return
    
    async def searchSongs(self, query: str):
        logging.debug("Starting /search function")
        # get the video searcher class
        searcher = VideoSearcher()
        try:
            result = await searcher.getSearchResults(query)
        except Exception as e:
            logging.error(f"[yt-dlp] Search failed for query '{query}' [{self.current_context or 'Unknown context'}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to search for songs: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[yt-dlp] No search results returned for query '{query}' [{self.current_context or 'Unknown context'}]")
            await self.textChannel.send(f"No results found for '{query}'.")
            return
        return result

    
    # function to skip current song
    async def skipSong(self, message: discord.Message = None):
        logging.debug("Starting /skip function")   
        if self.isConnectedToVC():
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            if not self.isMajorityVote:
                self.isPlayingTTS = False
                voice_client.stop_playing()
                return
            
            if not message:
                message = await self.textChannel.send(f"Skip the Song?")
            
            await message.add_reaction("✅")
            await message.add_reaction("❌")

            def check(reaction, user):
                return (
                    reaction.message.id == message.id and
                    str(reaction.emoji) in ["✅", "❌"] and
                    user in voice_client.channel.members and not user.bot
                )

            eligible_users = [m for m in voice_client.channel.members if not m.bot]
            required_votes = (len(eligible_users) // 2) + 1
            logging.debug(f"required votes: {required_votes}")

            vote_counts = {"✅": 0, "❌": 0}
            voters = set()

            try:
                while True:
                    reaction, user = await self.client.wait_for("reaction_add", timeout=30, check=check)
                    if user.id in voters:
                        continue
                    vote_counts[str(reaction.emoji)] += 1
                    voters.add(user.id)

                    if vote_counts["✅"] >= required_votes:
                        await self.textChannel.send("Majority vote reached. Skipping song.")
                        self.isPlayingTTS = False
                        voice_client.stop_playing()
                        return
                    elif vote_counts["❌"] >= required_votes:
                        await self.textChannel.send("Majority vote reached. Song will continue playing.")
                        return
                    elif len(voters) == len(eligible_users):
                        await self.textChannel.send("No Majority was found. Song will continue playing.")
                        return
            except asyncio.TimeoutError:
                await self.textChannel.send("Vote timed out. Song will continue playing.")
            

    
    # function to play previous song
    async def playPrevious(self, user: discord.User):
        logging.debug("Starting playPrevious function")
        if not self.previous_song:
            await self.textChannel.send("There is no previous song to play.")
            return

        source_command = self.current_context or f"Previous song requested by {user.display_name}"
        prev = self.previous_song
        song_to_queue = Song(
            title=prev.title,
            url=prev.url,
            link=None if not prev.isFile else prev.link,
            thumbnail=prev.thumbnail,
            duration=prev.duration,
            user=user,
            isFile=prev.isFile,
            http_headers=prev.http_headers if prev.isFile else {},
            source_command=source_command,
            is_lazy=not prev.isFile,
            query=prev.query
        )
        await self.queueSong(song_to_queue)

    # function to pause current song
    async def pauseSong(self):
        logging.debug("Starting /pause function")   
        if self.isConnectedToVC():
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            if not voice_client.is_paused():
                voice_client.pause()
                self.pause_start = int(time.time())
                return True
            else:
                voice_client.resume()
                self.pause_duration += int(time.time()) - self.pause_start
                return False
    
    # function to resume current song
    async def resumeSong(self):
        logging.debug("Starting /resume function")   
        if self.isConnectedToVC():
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            if voice_client.is_paused():
                voice_client.resume()
                self.pause_duration += int(time.time()) - self.pause_start
        return
    
    # function to stop all songs
    async def stopAllSongs(self, message: discord.Message = None):
        logging.debug("Starting /stop function")   
        if self.isConnectedToVC():
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            if not self.isMajorityVote:
                self.songQueue = []
                self.isLooping = False
                self.isPlayingTTS = False
                voice_client.stop_playing()
                return
            
            if not message:
                message = await self.textChannel.send(f"Stop current song and clear the queue? ***Needs all votes***")
            
            await message.add_reaction("✅")
            await message.add_reaction("❌")

            def check(reaction, user):
                return (
                    reaction.message.id == message.id and
                    str(reaction.emoji) in ["✅", "❌"] and
                    user in voice_client.channel.members and not user.bot
                )

            eligible_users = [m for m in voice_client.channel.members if not m.bot]
            required_votes = (len(eligible_users))
            logging.debug(f"required votes: {required_votes}")

            vote_counts = {"✅": 0, "❌": 0}
            voters = set()

            try:
                while True:
                    reaction, user = await self.client.wait_for("reaction_add", timeout=45, check=check)
                    if user.id in voters:
                        continue
                    vote_counts[str(reaction.emoji)] += 1
                    voters.add(user.id)

                    if vote_counts["✅"] >= required_votes:
                        await self.textChannel.send("Majority vote reached. Stopping song and clearing queue.")
                        self.isPlayingTTS = False
                        voice_client.stop_playing()
                        return
                    elif vote_counts["❌"] >= required_votes:
                        await self.textChannel.send("Majority vote reached. Song will continue playing.")
                        return
                    elif len(voters) == len(eligible_users):
                        await self.textChannel.send("No Majority was found. Song will continue playing.")
                        return
            except asyncio.TimeoutError:
                await self.textChannel.send("Vote timed out. Song will continue playing.")
    
    # function to soft disconnect the bot. This is used when a bot is the only one left in a voice channel and should leave, being able to reconnect later
    async def softDisconnect(self):
        if self.isConnectedToVC() is True:
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            self.songQueue = []
            self.isLooping = False
            await voice_client.disconnect(force=False)
            logging.debug(f"{self.guild.name} Music Controller has been soft disconnected.")

    # function to hard disconnect the bot.
    async def hardDisconnect(self):
        if self.isConnectedToVC() is True:
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            self.songQueue = []
            self.isLooping = False
            await voice_client.disconnect(force=True)
            logging.debug(f"{self.guild.name} Music Controller has been hard disconnected.")

    # function to join the channel and start listening
    async def two_four_seven(self, voiceChannel: discord.VoiceChannel, textChannel: discord.TextChannel) -> discord.VoiceClient:
        logging.debug("Starting /247 function")
        if self.isConnectedToVC() is not True:
            logging.debug("Bot is not in channel, connecting...")
            await voiceChannel.connect(cls=voice_recv.VoiceRecvClient)
            logging.info(f"Bot succesfully connected to {voiceChannel.name}")
            self.voiceChannel = voiceChannel
            self.textChannel = textChannel
            await self.startVoiceRecording()
            return None
        else:
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            logging.debug(f"Bot is already in channel: {voice_client.channel.name}")
            # If already listening, do not start again to prevent websocket loop 4006
            if not getattr(voice_client, 'is_listening', lambda: False)():
                await self.startVoiceRecording()
            return voice_client    
        
    # function to start the voice listening
    async def startVoiceRecording(self):
        # Monkey-patch router methods to prevent event loop blocking on join/leave
        import discord.ext.voice_recv.router as vr_router
        original_set_user_id = vr_router.PacketRouter.set_user_id
        original_destroy_decoder = vr_router.PacketRouter.destroy_decoder

        def patched_set_user_id(self_router, ssrc, user_id):
            def run():
                try:
                    original_set_user_id(self_router, ssrc, user_id)
                except Exception as e:
                    logging.error(f"set_user_id error: {e}")
            threading.Thread(target=run, daemon=True).start()

        def patched_destroy_decoder(self_router, ssrc):
            def run():
                try:
                    original_destroy_decoder(self_router, ssrc)
                except Exception as e:
                    logging.error(f"destroy_decoder error: {e}")
            threading.Thread(target=run, daemon=True).start()

        vr_router.PacketRouter.set_user_id = patched_set_user_id
        vr_router.PacketRouter.destroy_decoder = patched_destroy_decoder

        def process_wit(recognizer: sr.Recognizer, audio: sr.AudioData, user: Optional[str]) -> Optional[str]:
            def background_recognize():
                try:
                    text = recognizer.recognize_google(audio, language="en-IN")
                    if text:
                        asyncio.run_coroutine_threadsafe(self.handleTranscribedAudio(user, text), self.client.loop)
                except sr.UnknownValueError:
                    pass
                except Exception as e:
                    user_name = getattr(user, 'display_name', str(user))
                    logging.error(f"[SpeechRecognition] Error recognizing speech from {user_name}: {e}", exc_info=True)
            threading.Thread(target=background_recognize, daemon=True).start()
            return None

        voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
        if not voice_client:
            return

        try:
            if getattr(voice_client, 'is_listening', lambda: False)():
                voice_client.stop_listening()
            voice_client.listen(voice_recv.extras.speechrecognition.SpeechRecognitionSink(
                process_cb=process_wit,
                default_recognizer="google"
            ))
            self.client.loop.create_task(self._voice_recv_watchdog(voice_client))
        except Exception as e:
            logging.error(f"[voice_recv] Failed to start voice listening: {e}", exc_info=True)
            
    async def _voice_recv_watchdog(self, voice_client):
        await asyncio.sleep(10)
        while True:
            await asyncio.sleep(15)
            try:
                if not voice_client.is_connected():
                    logging.debug("Watchdog: voice client disconnected, stopping watchdog.")
                    return
                if not getattr(voice_client, 'is_listening', lambda: False)():
                    logging.warning("Watchdog: voice_recv stopped listening, fully reconnecting...")
                    voiceChannel = self.voiceChannel
                    textChannel = self.textChannel
                    # disconnect fully
                    try:
                        voice_client.stop_listening()
                    except Exception:
                        pass
                    try:
                        await voice_client.disconnect(force=True)
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                    # reconnect from scratch
                    if voiceChannel and textChannel:
                        await self.two_four_seven(voiceChannel, textChannel)
                        logging.info(f"Watchdog: reconnected to {voiceChannel.name}")
                    return  # new watchdog spawned by two_four_seven → startVoiceRecording
            except Exception as e:
                logging.error(f"[Watchdog] Error in voice_recv watchdog: {e}", exc_info=True)
                return

    # function to handle the transcribed audio for actual commands
    async def handleTranscribedAudio(self, user, text):
        self.current_context = f"Voice Command: '{text}' by {user.display_name} (ID: {user.id})"
        logging.info(f"{user.display_name}: {text}")
        if self.transcriptionChannel:
            try:
                await self.transcriptionChannel.send(f"**{user.display_name}**: {text}")
            except Exception as e:
                logging.error(f"Failed to send transcription message [{self.current_context}]: {e}", exc_info=True)

        if not text.strip():
            logging.debug(f"text is empty. Doing nothing")
            return

        try:
            # Clean up punctuation from the transcribed text
            clean_text = re.sub(r'[^\w\s]', '', text)
            
            botKeywords = await self._get_bot_keywords()

            # Check if the bot was mentioned
            if not any(word in clean_text.lower() for word in botKeywords):
                return

            # capture the remainder after the bot name
            match = re.search(r"(?:{})\s+(.+)".format("|".join(re.escape(k) for k in botKeywords)), clean_text, re.IGNORECASE)
            if not match:
                logging.debug("No command keyword found after bot name")
                return

            raw_command = match.group(1).lower().strip()

            bannedUsersClass = BannedUsers()
            bannedUsers = await bannedUsersClass.loadBannedUserIDs()
            if user.id in bannedUsers:
                await self.textChannel.send(f"User **{user.display_name}** is banned from the bot.")
                return

            intent, query = await self.nlp_processor.determine_intent(raw_command)

            logging.info(f"NLP determined intent: {intent}, query: {query}")

            if intent == 'play':
                if not query:
                    # If no query is found, assume they meant to just resume
                    await self.textChannel.send(f"Voice Activated - Resuming Song")
                    await self.resumeSong()
                else:
                    await self.textChannel.send(f"Voice Activated - Searching for song: {query}")
                    await self.handleYoutubeSearch(user, query)
            elif intent == 'pause':
                if self.isConnectedToVC():
                    voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
                    if voice_client and not voice_client.is_paused():
                        await self.textChannel.send(f"Voice Activated - Pausing Song")
                    else:
                        await self.textChannel.send(f"Voice Activated - Resuming Song")
                    await self.pauseSong()
            elif intent == 'resume':
                if self.isConnectedToVC():
                    await self.textChannel.send(f"Voice Activated - Resuming Song")
                    await self.resumeSong()
            elif intent == 'skip':
                if self.isConnectedToVC():
                    if not self.isMajorityVote:
                        await self.textChannel.send(f"Voice Activated - Skipping Song")
                    await self.skipSong()
            elif intent == 'stop':
                if self.isConnectedToVC():
                    if not self.isMajorityVote:
                        await self.textChannel.send(f"Voice Activated - Stopping Song and clearing queue")
                    await self.stopAllSongs()
            elif intent == 'loop':
                if self.isConnectedToVC():
                    if await self.setLooping():
                        await self.textChannel.send(f"Voice Activated - Looping Enabled")
                    else:
                        await self.textChannel.send(f"Voice Activated - Looping Disabled")
            elif intent == 'previous':
                if self.isConnectedToVC():
                    await self.textChannel.send(f"Voice Activated - Playing Previous Song")
                    await self.playPrevious(user)
            elif intent == 'disconnect':
                # Only VIP users (including OWNER) can disconnect via voice keyword
                vipUsersClass = VIPUsers()
                vipUsers = await vipUsersClass.loadVIPUserIDs()
                if user.id not in vipUsers:
                    if self.textChannel:
                        await self.textChannel.send(f"Only admins can disconnect the bot.")
                    return

                if self.isConnectedToVC():
                    await self.textChannel.send(f"Voice Activated - Disconnecting from voice channel")
                    await self.hardDisconnect()
            else:
                await self.textChannel.send("Sorry, I don't understand.")
                # optionally add TTS to say sorry
                voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
                if voice_client and not voice_client.is_playing() and not voice_client.is_paused():
                    try:
                        tts_buffer = await self.generate_tts("Sorry, I don't understand.")
                        tts_player = await self.client.loop.run_in_executor(
                            None,
                            lambda: discord.FFmpegPCMAudio(tts_buffer, pipe=True)
                        )
                        def after_tts(error):
                            if error:
                                logging.error(f"[TTS] Error during apology TTS playback [{self.current_context}]: {error}", exc_info=True)

                        voice_client.play(tts_player, after=after_tts)
                    except Exception as e:
                        logging.error(f"[TTS] Failed to play error TTS [{self.current_context}]: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Error processing voice command '{text}' from {user.display_name} [{self.current_context}]: {e}", exc_info=True)
            if self.textChannel:
                await self.textChannel.send(f"An error occurred while processing voice command: '{text}'")

        return


    
    async def handleFile(self, user: discord.User, file: discord.Attachment):
        logging.debug(f"In handleFile")
        source_command = self.current_context or f"File upload '{file.filename}' by {user.display_name}"
        # create a song object
        fileSong = Song(file.filename, file.url, file.url, self.client.user.avatar.url, 0, user, isFile=True, source_command=source_command)
        # queue the song
        await self.queueSong(fileSong)
        return
    
    async def determineSongSource(self, user: discord.User, query: str):
        logging.debug(f"In Determine Song Source")
        if not self.current_context:
            self.current_context = f"Command by {user.display_name} (ID: {user.id}) query: '{query}'"
        query_lower = query.lower()

        # Regex patterns
        youtube_pattern = re.compile(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/')
        youtube_playlist_pattern = re.compile(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/playlist\?list=[\w-]+')
        spotify_pattern = re.compile(r'(https?://)?(open\.)?spotify\.com/')
        spotify_playlist_pattern = re.compile(r'(https?://)?(open\.)?spotify\.com/(playlist|album)/[a-zA-Z0-9]+')
        soundcloud_pattern = re.compile(r'(https?://)?(www\.)?soundcloud\.com/')
        soundcloud_playlist_pattern = re.compile(r'^(https?://)?(www\.)?soundcloud\.com/[^/]+/sets/[^/]+/?')

        # Determine source
        if youtube_pattern.search(query_lower):
            logging.debug("Detected YouTube link")
            if youtube_playlist_pattern.search(query_lower):
                logging.debug("Detected YouTube playlist")
                return await self.handleYoutubePlaylist(user, query)
            return await self.handleYoutubeLink(user, query)
        elif spotify_pattern.search(query_lower):
            logging.debug("Detected Spotify link")
            if spotify_playlist_pattern.search(query_lower):
                logging.debug("Detected spotify playlist/album")
                return await self.handleSpotifyPlaylist(user, query)
            return await self.handleSpotifyLink(user, query)
        elif soundcloud_pattern.search(query_lower):
            logging.debug("Detected SoundCloud link")
            if soundcloud_playlist_pattern.search(query_lower):
                logging.debug("Detected SoundCloud playlist")
                return await self.handleSoundCloudPlaylist(user, query)
            return await self.handleSoundCloudLink(user, query)
        else:
            logging.debug("Detected search query - assuming YouTube search")
            return await self.handleYoutubeSearch(user, query)
        
    async def handleYoutubeLink(self, user, url):
        logging.debug("In handleYoutubeLink")
        # get the song info from the youtube link
        searcher = VideoSearcher()
        try:
            result = await searcher.getVideoInfoFromURL(url)
        except Exception as e:
            logging.error(f"[yt-dlp] Error extracting YouTube URL '{url}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[yt-dlp] No video info found for YouTube URL '{url}' [{self.current_context}]")
            await self.textChannel.send(f"Unable to find song.")
            return
        source_command = self.current_context or f"YouTube URL '{url}' by {user.display_name}"
        # create a song object
        youtubeSong = Song(result['title'], url, result['link'], result['thumbnail'], result['duration'], user, isFile=False, http_headers=result.get('http_headers'), source_command=source_command)
        # queue the song
        await self.queueSong(youtubeSong)
        return
    
    async def handleYoutubePlaylist(self, user, url):
        logging.debug("In handleYoutubePlaylist")
        # get the playlist info from the youtube link
        searcher = VideoSearcher()
        try:
            result = await searcher.getPlaylistInfo(url)
        except Exception as e:
            logging.error(f"[yt-dlp] Error extracting YouTube playlist '{url}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to find playlist: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[yt-dlp] No playlist info returned for YouTube playlist '{url}' [{self.current_context}]")
            await self.textChannel.send(f"Unable to find playlist.")
            return
        # get the playlist metadata
        metadata = result.pop(0)
        playlist_name = metadata.get('playlist_name', 'YouTube Playlist')
        thumbnail = metadata.get('thumbnail') or self.client.user.avatar.url
        source_command = self.current_context or f"YouTube Playlist '{url}' by {user.display_name}"

        was_idle = (len(self.songQueue) == 0)

        # Batch append all lazy songs instantly
        for entry in result:
            lazy_song = Song(
                title=entry['title'],
                url=entry['url'],
                link=None,
                thumbnail=entry.get('thumbnail') or thumbnail,
                duration=entry.get('duration', 0),
                user=user,
                isFile=False,
                http_headers=None,
                source_command=source_command,
                is_lazy=True
            )
            self.songQueue.append(lazy_song)

        # send single summary embed
        embed = discord.Embed(
            title="Added Playlist to Queue:",
            color=0xa600ff,
            )
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Playlist Name", value=playlist_name, inline=False)
        embed.add_field(name="# of Songs", value=f"{len(result)} tracks", inline=False)
        await self.textChannel.send(embed=embed)

        if was_idle and self.songQueue:
            await self.playSong()
        return

    async def handleSpotifyLink(self, user, url):
        logging.debug("In handleSpotifyLink")
        # get the name and artist of song from spotify API
        try:
            spotifySongInfo = await self.spotify.getSpotifySongInfo(url)
        except Exception as e:
            logging.error(f"[Spotify] Failed to fetch Spotify track info for '{url}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to add Spotify song: {e}")
            return
        query = f"{spotifySongInfo['title']} by {spotifySongInfo['artist']}"
        logging.debug(f"searching for spotify song: {query}")
        # get the song info from the youtube search query
        searcher = VideoSearcher()
        try:
            result = await searcher.getVideoInfoFromQuery(query)
        except Exception as e:
            logging.error(f"[yt-dlp] Failed to search YouTube for Spotify track '{query}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[yt-dlp] No YouTube video found for Spotify track '{query}' [{self.current_context}]")
            await self.textChannel.send(f"Unable to find song.")
            return
        source_command = self.current_context or f"Spotify Track '{url}' by {user.display_name}"
        # create a song object
        youtubeSong = Song(result['title'], result['url'], result['link'], result['thumbnail'], result['duration'], user, isFile=False, http_headers=result.get('http_headers'), source_command=source_command)
        # queue the song
        await self.queueSong(youtubeSong)
        return
    
    async def handleSpotifyPlaylist(self, user, playlist):
        logging.debug("In handleSpotifyPlaylist")
        # get the playlist info from spotify API
        try:
            result = await self.spotify.getSpotifyPlaylistInfo(playlist)
        except Exception as e:
            logging.error(f"[Spotify] Failed to fetch Spotify playlist/album '{playlist}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to find spotify playlist/album: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[Spotify] No tracks found in Spotify playlist/album '{playlist}' [{self.current_context}]")
            await self.textChannel.send(f"Unable to find spotify playlist/album.")
            return
        # get the playlist name, number of songs, and thumbnail
        playlist_info = result.pop(0)
        playlist_name = playlist_info.get('title', 'Spotify Playlist')
        thumbnail = playlist_info.get('thumbnail') or self.client.user.avatar.url
        source_command = self.current_context or f"Spotify Playlist '{playlist}' by {user.display_name}"

        was_idle = (len(self.songQueue) == 0)

        # Batch append all lazy songs instantly
        for song in result:
            query = f"{song['title']} by {song['artist']}"
            lazy_song = Song(
                title=f"{song['title']} - {song['artist']}",
                url=None,
                link=None,
                thumbnail=thumbnail,
                duration=0,
                user=user,
                isFile=False,
                http_headers=None,
                source_command=source_command,
                is_lazy=True,
                query=query
            )
            self.songQueue.append(lazy_song)

        # send single summary embed
        embed = discord.Embed(
            title="Added Playlist to Queue:",
            color=0xa600ff,
            )
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Playlist Name", value=playlist_name, inline=False)
        embed.add_field(name="# of Songs", value=f"{len(result)} tracks", inline=False)
        await self.textChannel.send(embed=embed)

        if was_idle and self.songQueue:
            await self.playSong()
        return

    async def handleSoundCloudLink(self, user, url):
        logging.debug("In handleSoundCloudLink")
        # get the song info from the soundcloud link
        searcher = VideoSearcher()
        try:
            result = await searcher.getVideoInfoFromURL(url)
        except Exception as e:
            logging.error(f"[SoundCloud] Failed to extract SoundCloud track '{url}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[SoundCloud] No info returned for SoundCloud track '{url}' [{self.current_context}]")
            await self.textChannel.send(f"Unable to find song.")
            return
        source_command = self.current_context or f"SoundCloud URL '{url}' by {user.display_name}"
        # create a song object
        soundcloudSong = Song(result['title'], url, result['link'], result['thumbnail'], result['duration'], user, isFile=False, http_headers=result.get('http_headers'), source_command=source_command)
        # queue the song
        await self.queueSong(soundcloudSong)
        return
    
    async def handleSoundCloudPlaylist(self, user, url):
        logging.debug("In handleSoundCloudPlaylist")
        # get the playlist info from the soundcloud link
        searcher = VideoSearcher()
        try:
            result = await searcher.getPlaylistInfo(url)
        except Exception as e:
            logging.error(f"[SoundCloud] Failed to extract SoundCloud playlist '{url}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to find playlist: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[SoundCloud] No info returned for SoundCloud playlist '{url}' [{self.current_context}]")
            await self.textChannel.send(f"Unable to find playlist.")
            return
        # get the playlist name and the number of songs
        metadata = result.pop(0)
        playlist_name = metadata.get('playlist_name', 'SoundCloud Playlist')
        thumbnail = metadata.get('thumbnail') or self.client.user.avatar.url
        source_command = self.current_context or f"SoundCloud Playlist '{url}' by {user.display_name}"

        was_idle = (len(self.songQueue) == 0)

        # Batch append all lazy songs instantly
        for entry in result:
            lazy_song = Song(
                title=entry['title'],
                url=entry['url'],
                link=None,
                thumbnail=entry.get('thumbnail') or thumbnail,
                duration=entry.get('duration', 0),
                user=user,
                isFile=False,
                http_headers=None,
                source_command=source_command,
                is_lazy=True
            )
            self.songQueue.append(lazy_song)

        # send single summary embed
        embed = discord.Embed(
            title="Added Playlist to Queue:",
            color=0xa600ff,
            )
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Playlist Name", value=playlist_name, inline=False)
        embed.add_field(name="# of Songs", value=f"{len(result)} tracks", inline=False)
        await self.textChannel.send(embed=embed)

        if was_idle and self.songQueue:
            await self.playSong()
        return

    async def handleYoutubeSearch(self, user, query):
        logging.debug("In handleYoutubeSearch")
        # get the song info from the youtube search query
        searcher = VideoSearcher()
        try:
            result = await searcher.getVideoInfoFromQuery(query)
        except Exception as e:
            logging.error(f"[yt-dlp] Search failed for query '{query}' [{self.current_context}]: {e}", exc_info=True)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            logging.error(f"[yt-dlp] No video info found for search query '{query}' [{self.current_context}]")
            await self.textChannel.send(f"Unable to find song.")
            return
        source_command = self.current_context or f"YouTube Search '{query}' by {user.display_name}"
        # create a song object
        youtubeSong = Song(result['title'], result['url'], result['link'], result['thumbnail'], result['duration'], user, isFile=False, http_headers=result.get('http_headers'), source_command=source_command)
        # queue the song
        await self.queueSong(youtubeSong)
        return

    async def queueSong(self, song: Song):
        logging.debug("In queueSong")
        # check if song should play right away or go into the queue
        if not self.songQueue:
            logging.debug("Queue is empty, playing song right away.")
            self.songQueue.append(song)
            print("songQueue: ", self.songQueue)
            await self.playSong()
            return
        else:
            logging.debug("Adding song to queue.")
            self.songQueue.append(song)
            print("songQueue: ", self.songQueue)
            # send the "Added to Queue" discord embed
            embed = discord.Embed(
                title="Added to Queue:",
                description=song.title,
                color=0xa600ff,
                )
            embed.set_thumbnail(url=song.thumbnail)
            await self.textChannel.send(embed=embed)
            return
        
    async def queuePlaylist(self, playlist: list):
        logging.debug("In queuePlaylist")
        if not playlist:
            return
        thumbnail = playlist.pop(0) if isinstance(playlist[0], str) else (self.client.user.avatar.url if self.client.user else None)
        was_idle = (len(self.songQueue) == 0)
        for song in playlist:
            self.songQueue.append(song)

        # send single summary embed
        embed = discord.Embed(
            title="Playlist Added to Queue:",
            color=0xa600ff,
            )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="# of Songs", value=f"{len(playlist)} tracks", inline=False)
        await self.textChannel.send(embed=embed)

        if was_idle and self.songQueue:
            await self.playSong()
        return
        
    async def _prefetch_next_song(self):
        """Asynchronously pre-resolves stream URL for the next track in queue to make track transition instant."""
        if len(self.songQueue) > 1:
            next_song = self.songQueue[1]
            if next_song.is_lazy or (not next_song.isFile and not next_song.link):
                try:
                    logging.debug(f"[JIT Pre-fetch] Pre-fetching stream URL for: {next_song.title}")
                    searcher = VideoSearcher()
                    if next_song.url:
                        result = await searcher.getVideoInfoFromURL(next_song.url)
                    elif next_song.query:
                        result = await searcher.getVideoInfoFromQuery(next_song.query)
                    else:
                        return

                    if result and result.get('link'):
                        next_song.title = result.get('title') or next_song.title
                        next_song.link = result['link']
                        next_song.url = result.get('url') or next_song.url
                        next_song.thumbnail = result.get('thumbnail') or next_song.thumbnail
                        next_song.duration = result.get('duration') or next_song.duration
                        next_song.http_headers = result.get('http_headers', {})
                        next_song.is_lazy = False
                        logging.debug(f"[JIT Pre-fetch] Successfully pre-fetched: {next_song.title}")
                except Exception as e:
                    logging.debug(f"[JIT Pre-fetch] Pre-fetch skipped for '{next_song.title}': {e}")

    async def playSong(self):
        logging.debug("In playSong.")

        # check to make sure there is a song in queue
        if not self.songQueue:
            await self.textChannel.send("No more songs to play.")
            self.start_time = None
            self.pause_duration = 0
            self.pause_start = None
            return

        # get the next song to play
        song = self.songQueue[0]

        # Resolve lazy song just-in-time
        if song.is_lazy or (not song.isFile and not song.link):
            logging.info(f"[JIT] Resolving stream for lazy song: {song.title} [Source: {song.source_command}]")
            searcher = VideoSearcher()
            try:
                if song.url:
                    result = await searcher.getVideoInfoFromURL(song.url)
                elif song.query:
                    result = await searcher.getVideoInfoFromQuery(song.query)
                else:
                    raise ValueError(f"Song '{song.title}' has neither URL nor search query to resolve.")

                if not result or not result.get('link'):
                    raise ValueError(f"No audio stream link found for '{song.title}'.")

                song.title = result.get('title') or song.title
                song.link = result['link']
                song.url = result.get('url') or song.url
                song.thumbnail = result.get('thumbnail') or song.thumbnail
                song.duration = result.get('duration') or song.duration
                song.http_headers = result.get('http_headers', {})
                song.is_lazy = False
                logging.info(f"[JIT] Successfully resolved stream for: {song.title}")
            except Exception as e:
                logging.error(f"[JIT] Failed to resolve lazy song '{song.title}' [{song.source_command}]: {e}", exc_info=True)
                await self.textChannel.send(f"⚠️ Unable to load track **{song.title}**, skipping to next...")
                if self.songQueue:
                    self.songQueue.pop(0)
                fut = asyncio.run_coroutine_threadsafe(self.playSong(), self.client.loop)
                return

        if not song.isFile:
            expiration = getSongExpiration(song.link)
            now = int(time.time())
            logging.info(f"[FFmpeg] Preparing to play: {song.title} [Source: {song.source_command}]")
            logging.info(f"[FFmpeg] Stream URL expiration: {expiration}, current time: {now}, expires in: {expiration - now if expiration else 'N/A'}s")
            logging.debug(f"[FFmpeg] Stream URL: {song.link[:120]}...")

            if expiration and expiration <= now:
                logging.warning(f"[FFmpeg] Stream URL is expired (by {now - expiration}s). Fetching new one for '{song.title}' [Source: {song.source_command}]")
                # get the song info from the link
                searcher = VideoSearcher()
                try:
                    result = await searcher.getVideoInfoFromURL(song.url)
                except Exception as e:
                    logging.error(f"[FFmpeg] Failed to refresh stream URL for '{song.title}' [Source: {song.source_command}]: {e}", exc_info=True)
                    await self.textChannel.send(f"Unable to play song: {e}")
                    return
                # update the current songs stream link
                song.link = result['link']
                song.http_headers = result.get('http_headers', {})
                new_exp = getSongExpiration(song.link)
                logging.info(f"[FFmpeg] New stream URL obtained for '{song.title}', expires in: {new_exp - now if new_exp else 'N/A'}s")

        # Build FFmpeg headers from yt-dlp's http_headers to avoid YouTube blocking
        header_str = ''
        if not song.isFile and song.http_headers:
            header_lines = ''.join(f'{k}: {v}\r\n' for k, v in song.http_headers.items())
            header_str = f' -headers "{header_lines}"'

        ffmpeg_options = {
            'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel warning{header_str}',
            'options': '-vn -filter:a "volume=0.7"'
        }

        # create the discord player for current song
        # Offload synchronous Popen calls to prevent blocking event loop
        logging.info(f"[FFmpeg] Creating FFmpegOpusAudio player for: {song.title} [Source: {song.source_command}]")
        try:
            player = await self.client.loop.run_in_executor(None, lambda: discord.FFmpegOpusAudio(song.link, **ffmpeg_options))
        except Exception as e:
            logging.error(f"[FFmpeg] Failed to create FFmpegOpusAudio player for '{song.title}' [Source: {song.source_command}]: {e}", exc_info=True)
            await self.textChannel.send(f"Error starting audio playback for **{song.title}**.")
            if self.songQueue:
                self.songQueue.pop(0)
            fut = asyncio.run_coroutine_threadsafe(self.playSong(), self.client.loop)
            return

        # Start prefetching next song in queue in background
        self.client.loop.create_task(self._prefetch_next_song())

        # function to call after a song is done playing
        def after_playing(error):
            if error:
                error_str = str(error)
                logging.error(f"[FFmpeg] Playback error for '{song.title}' [Source: {song.source_command}]: {error_str}", exc_info=True)
                # Try to extract and interpret the exit code
                import re as _re
                code_match = _re.search(r'code (\d+)', error_str)
                if code_match:
                    code = int(code_match.group(1))
                    # Interpret as signed 32-bit for Windows
                    if code > 0x7FFFFFFF:
                        signed = code - 0x100000000
                        logging.error(f"[FFmpeg] Exit code {code} (signed: {signed}, hex: 0x{code:08X}) [Source: {song.source_command}]")
                    else:
                        logging.error(f"[FFmpeg] Exit code {code} (hex: 0x{code:08X}) [Source: {song.source_command}]")
                logging.error(f"[FFmpeg] Song URL: {song.url}, isFile: {song.isFile}, Stream Link: {song.link[:100]}...")
                if not self.isLooping and self.songQueue:
                    self.previous_song = self.songQueue.pop(0)
                fut = asyncio.run_coroutine_threadsafe(self.playSong(), self.client.loop)
                fut.add_done_callback(lambda f: f.exception())
            else:
                if self.isLooping:
                    logging.debug("Song finished, replaying previous song.")
                else:
                    logging.debug("Song finished, popping from queue and checking next")
                    if self.songQueue:
                        self.previous_song = self.songQueue.pop(0)
                fut = asyncio.run_coroutine_threadsafe(self.playSong(), self.client.loop)
                fut.add_done_callback(lambda f: f.exception())

        def after_tts(error):
            if error:
                logging.error(f"[TTS] Error during TTS playback for '{song.title}' [Source: {song.source_command}]: {error}", exc_info=True)

            if not self.isPlayingTTS: # if aborted
                return
            self.isPlayingTTS = False

            # Start actual song
            self.start_time = int(time.time())
            self.pause_duration = 0
            self.pause_start = None

            def play_actual_song():
                if self.isConnectedToVC():
                    voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
                    if voice_client and voice_client.is_connected():
                        voice_client.play(player, after=after_playing)

            self.client.loop.call_soon_threadsafe(play_actual_song)


        # generate and play TTS first
        voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
        try:
            tts_title = ' '.join(song.title.split()[:6])
            tts_buffer = await self.generate_tts(f"Playing {tts_title}")
            tts_player = await self.client.loop.run_in_executor(
                None,
                lambda: discord.FFmpegPCMAudio(tts_buffer, pipe=True)
            )
            self.isPlayingTTS = True
            voice_client.play(tts_player, after=after_tts)
        except Exception as e:
            logging.error(f"[TTS] Failed to play TTS for '{song.title}' [Source: {song.source_command}]: {e}", exc_info=True)
            # fallback to direct play
            self.start_time = int(time.time())
            self.pause_duration = 0
            self.pause_start = None
            voice_client.play(player, after=after_playing)


        # send the "Now Playing" discord embed
        embed = discord.Embed(
            title="Now Playing:",
            description=song.title,
            color=0xa600ff,
            )
        embed.set_thumbnail(url=song.thumbnail)
        await self.textChannel.send(embed=embed, view=MusicButtons(client= self.client))