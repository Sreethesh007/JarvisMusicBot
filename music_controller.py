import discord
import os
import re
import asyncio
import time
import random
from discord import app_commands
from discord.ext import commands, voice_recv
from typing import Optional, Tuple
import speech_recognition as sr
import logging
from management.banned_users import BannedUsers
from management.word_counter import WordCounter
from management.bot_keywords import BotKeywords
from scripts.ytDLP import VideoSearcher, getSongExpiration
from embed_views.music_buttons import MusicButtons
from scripts.spotify import SpotifyController

class Song:
    def __init__(self, title: str, url: str, link: str, thumbnail: str, duration: int, user: discord.User, isFile: bool):
        self.title = title
        self.url = url
        self.link = link
        self.thumbnail = thumbnail
        self.duration = duration
        self.user = user
        self.isFile = isFile

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
            logging.error(e)
            await self.textChannel.send(f"Unable to search for songs: {e}")
            return
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to search for songs: {e}")
            return
        return result

    
    # function to skip current song
    async def skipSong(self, message: discord.Message = None):
        logging.debug("Starting /skip function")   
        if self.isConnectedToVC():
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            if not self.isMajorityVote:
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
            await self.startVoiceRecording()
            return voice_client    
        
    # function to start the voice listening
    async def startVoiceRecording(self):
        logging.debug("in voice recording")

        # override the speech recognition to use google
        def process_wit(recognizer: sr.Recognizer, audio: sr.AudioData, user: Optional[str]) -> Optional[str]:
            text: Optional[str] = None
            try:
                func = getattr(recognizer, 'recognize_google', recognizer.recognize_google)
                text = func(audio)
                # send the transcribed audio to an async event
                asyncio.run_coroutine_threadsafe(self.handleTranscribedAudio(user, text), self.client.loop)
            except sr.UnknownValueError:
                pass
            return text
        
        voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
        try:
            voice_client.listen(voice_recv.extras.speechrecognition.SpeechRecognitionSink(process_cb=process_wit, default_recognizer="google"))
        except Exception as e:
            logging.exception(e)

    # function to handle the transcribed audio for actual commands
    async def handleTranscribedAudio(self, user, text):
        logging.info(f"{user.display_name}: {text}")
        if self.transcriptionChannel:
            await self.transcriptionChannel.send(f"**{user.display_name}**: {text}")

        if not text.strip():
            logging.debug(f"text is empty. Doing nothing")
            return
        
        commands = {
            "play": "handle_play_keyword",
            "gana rok de": "handle_pause_keyword",
            "gana skip": "handle_skip_keyword",
            "next": "handle_skip_keyword",
            "loop": "handle_loop_keyword",
            "stop": "handle_stop_keyword"
        }

        keywords = (await WordCounter().loadWordCounters())[0]
        if any(word in text.lower() for word in keywords):
            await self.handle_word_counter_keyword(user, text.lower())

        botKeywordsClass = BotKeywords()
        botKeywords = await botKeywordsClass.loadBotKeywords()

        if not any(word in text.lower() for word in botKeywords):
            return

        # capture the remainder after the bot name so multi-word commands like "rok de" work
        match = re.search(r"(?:{})\s+(.+)".format("|".join(re.escape(k) for k in botKeywords)), text, re.IGNORECASE)
        if not match:
            logging.debug("No command keyword found after bot name")
            return

        raw_keyword = match.group(1).lower().strip()
        # prefer exact multi-word matches (e.g. "rok de"), else fall back to the first word
        if raw_keyword in commands:
            keyword = raw_keyword
        else:
            keyword = raw_keyword.split()[0]

        if keyword not in commands:
            logging.debug(f"'{keyword}' is not a valid command keyword")
            return

        bannedUsersClass = BannedUsers()
        bannedUsers = await bannedUsersClass.loadBannedUserIDs()
        if user.id in bannedUsers:
            await self.textChannel.send(f"User **{user.display_name}** is banned from the bot.")
            return

        method_name = commands[keyword]
        handler = getattr(self, method_name, None)
        if handler:
            await handler(user, text)
        return

    async def handle_word_counter_keyword(self, user, text):
        logging.debug(f"in handle_word_counter_keyword")
        wordCounterClass = WordCounter()
        mapping = (await wordCounterClass.loadWordCounters())[0]

        counter_hits = {}

        for keyword, counter_name in mapping.items():
            count = text.count(keyword)
            if count > 0:
                counter_hits[counter_name] = counter_hits.get(counter_name, 0) + count
                for _ in range(count):
                    await wordCounterClass.incrementCounterForKeyword(keyword)
                    new_count = await wordCounterClass.getCount(counter_name)
                    embed = discord.Embed(
                        title=f"{counter_name.capitalize()} Counter:",
                        description=f"{new_count} - {user.display_name}",
                        color=0xa600ff,
                    )
                    embed.set_thumbnail(url=self.client.user.avatar.url)
                    await self.textChannel.send(embed=embed)

        logging.info(f"{user.display_name} triggered updates for: {counter_hits}")
        return


    async def handle_play_keyword(self, user, text):
        logging.debug(f"In handle_play_keyword")
        botKeywordsClass = BotKeywords()
        botKeywords = await botKeywordsClass.loadBotKeywords()
        match = re.search(r"(?:{})\s+play\s+(.*)".format("|".join(re.escape(k) for k in botKeywords)), text, re.IGNORECASE)
        if not match:
            logging.debug("No query found after 'keyword play', assume user wants to resume")
            await self.textChannel.send(f"Voice Activated - Resuming Song")
            await self.resumeSong()
            return
        query = match.group(1).strip()
        await self.textChannel.send(f"Voice Activated - Searching for song: {query}")
        await self.handleYoutubeSearch(user, query)
        return
    
    async def handle_pause_keyword(self, user, text):
        logging.debug(f"In handle_pause_keyword")
        if self.isConnectedToVC():
            voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
            if not voice_client.is_paused():
                await self.textChannel.send(f"Voice Activated - Pausing Song")
            else:
                await self.textChannel.send(f"Voice Activated - Resuming Song")
            await self.pauseSong()
            return
    
    async def handle_skip_keyword(self, user, text):
        logging.debug(f"In handle_skip_keyword")
        if self.isConnectedToVC():
            if not self.isMajorityVote:
                await self.textChannel.send(f"Voice Activated - Skipping Song")
            await self.skipSong()
            return
        
    async def handle_stop_keyword(self, user, text):
        logging.debug(f"In handle_stop_keyword")
        if self.isConnectedToVC():
            if not self.isMajorityVote:
                await self.textChannel.send(f"Voice Activated - Stopping Song and clearing queue")
            await self.stopAllSongs()
            return
        
    async def handle_loop_keyword(self, user, text):
        logging.debug(f"In handle_loop_keyword")
        if self.isConnectedToVC():
            if await self.setLooping():
                await self.textChannel.send(f"Voice Activated - Looping Enabled")
            else:
                await self.textChannel.send(f"Voice Activated - Looping Disabled")
            return
    
    async def handleFile(self, user: discord.User, file: discord.Attachment):
        logging.debug(f"In handleFile")
        # create a song object
        fileSong = Song(file.filename, file.url, file.url, self.client.user.avatar.url, 0, user, isFile=True)
        # queue the song
        await self.queueSong(fileSong)
        return
    
    async def determineSongSource(self, user: discord.User, query: str):
        logging.debug(f"In Determine Song Source")
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
            logging.error(e)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to find song.")
            return
        # create a song object
        youtubeSong = Song(result['title'], url, result['link'], result['thumbnail'], result['duration'], user, isFile=False)
        # queue the song
        await self.queueSong(youtubeSong)
        return
    
    async def handleYoutubePlaylist(self, user, url):
        logging.debug("In handleYoutubePlaylist")
        # get the playlist info from the youtube link
        searcher = VideoSearcher()
        result = await searcher.getPlaylistInfo(url)
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to find playlist.")
            return
        # get the playlist name and the number of songs
        metadata = result.pop(0)
        thumbnail = metadata.get('thumbnail') or self.client.user.avatar.url
        # send the "Adding Playlist" discord embed
        embed = discord.Embed(
            title="Adding Playlist:",
            color=0xa600ff,
            )
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Playlist Name", value=metadata['playlist_name'], inline=False)
        embed.add_field(name="# of Songs", value=metadata['song_count'], inline=False)
        await self.textChannel.send(embed=embed)
        for song in result:
            logging.debug(f"Searching for {song['url']}")
            try:
                # grab the video info for each song in the playlist
                songInfo = await searcher.getVideoInfoFromURL(song['url'])
            except Exception as e:
                logging.error(e)
                await self.textChannel.send(f"Unable to add song: {e}")
                continue
            # create a song object and append it to the playlist
            youtubeSong = Song(songInfo['title'], song['url'], songInfo['link'], songInfo['thumbnail'], songInfo['duration'], user, isFile=False)
            # queue the song
            await self.queueSong(youtubeSong)
        return

    async def handleSpotifyLink(self, user, url):
        logging.debug("In handleSpotifyLink")
        # get the name and artist of song from spotify API
        spotifySongInfo = await self.spotify.getSpotifySongInfo(url)
        query = f"{spotifySongInfo['title']} by {spotifySongInfo['artist']}"
        logging.debug(f"searching for spotify song: {query}")
        # get the song info from the youtube search query
        searcher = VideoSearcher()
        try:
            result = await searcher.getVideoInfoFromQuery(query)
        except Exception as e:
            logging.error(e)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to find song.")
            return
        # create a song object
        youtubeSong = Song(result['title'], result['url'], result['link'], result['thumbnail'], result['duration'], user, isFile=False)
        # queue the song
        await self.queueSong(youtubeSong)
        return
    
    async def handleSpotifyPlaylist(self, user, playlist):
        logging.debug("In handleSpotifyPlaylist")
        # get the playlist info from spotify API
        result = await self.spotify.getSpotifyPlaylistInfo(playlist)
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to find spotify playlist/album.")
            return
        # get the playlist name, number of songs, and thumbnail
        playlist_info = result.pop(0)
        thumbnail = playlist_info.get('thumbnail') or self.client.user.avatar.url
        # send the "Adding Playlist" discord embed
        embed = discord.Embed(
            title="Adding Playlist:",
            color=0xa600ff,
            )
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Playlist Name", value=playlist_info['title'], inline=False)
        embed.add_field(name="# of Songs", value=len(result), inline=False)
        await self.textChannel.send(embed=embed)
        searcher = VideoSearcher()
        for song in result:
            query = f"{song['title']} by {song['artist']}"
            logging.debug(f"Searching for {query}")
            try:
                # grab the video info for each song in the playlist
                songInfo = await searcher.getVideoInfoFromQuery(query)
            except Exception as e:
                logging.error(e)
                await self.textChannel.send(f"Unable to add song: {e}")
                continue
            # create a song object
            youtubeSong = Song(songInfo['title'], songInfo['url'], songInfo['link'], songInfo['thumbnail'], songInfo['duration'], user, isFile=False)
            # queue the song
            await self.queueSong(youtubeSong)
        return

    async def handleSoundCloudLink(self, user, url):
        logging.debug("In handleSoundCloudLink")
        # get the song info from the soundcloud link
        searcher = VideoSearcher()
        try:
            result = await searcher.getVideoInfoFromURL(url)
        except Exception as e:
            logging.error(e)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to find song.")
            return
        # create a song object
        soundcloudSong = Song(result['title'], url, result['link'], result['thumbnail'], result['duration'], user, isFile=False)
        # queue the song
        await self.queueSong(soundcloudSong)
        return
    
    async def handleSoundCloudPlaylist(self, user, url):
        logging.debug("In handleSoundCloudPlaylist")
        # get the playlist info from the soundcloud link
        searcher = VideoSearcher()
        result = await searcher.getPlaylistInfo(url)
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to find playlist.")
            return
        # get the playlist name and the number of songs
        metadata = result.pop(0)
        thumbnail = metadata.get('thumbnail') or self.client.user.avatar.url
        # send the "Adding Playlist" discord embed
        embed = discord.Embed(
            title="Adding Playlist:",
            color=0xa600ff,
            )
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Playlist Name", value=metadata['playlist_name'], inline=False)
        embed.add_field(name="# of Songs", value=metadata['song_count'], inline=False)
        await self.textChannel.send(embed=embed)
        for song in result:
            logging.debug(f"Searching for {song['url']}")
            try:
                # grab the video info for each song in the playlist
                songInfo = await searcher.getVideoInfoFromURL(song['url'])
            except Exception as e:
                logging.error(e)
                await self.textChannel.send(f"Unable to add song: {e}")
                continue
            # create a song object and append it to the playlist
            soundcloudSong = Song(songInfo['title'], song['url'], songInfo['link'], songInfo['thumbnail'], songInfo['duration'], user, isFile=False)
            # queue the song
            await self.queueSong(soundcloudSong)
        return

    async def handleYoutubeSearch(self, user, query):
        logging.debug("In handleYoutubeSearch")
        # get the song info from the youtube search query
        searcher = VideoSearcher()
        try:
            result = await searcher.getVideoInfoFromQuery(query)
        except Exception as e:
            logging.error(e)
            await self.textChannel.send(f"Unable to add song: {e}")
            return
        # check if result came back successfully
        if not result:
            await self.textChannel.send(f"Unable to find song.")
            return
        # create a song object
        youtubeSong = Song(result['title'], result['url'], result['link'], result['thumbnail'], result['duration'], user, isFile=False)
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
        # pop the thumbnail from the playlist
        thumbnail = playlist.pop(0)
        # check if playlist should play right away or go into the queue
        if not self.songQueue:
            logging.debug("Queue is empty, playing playlist right away.")
            for song in playlist:
                self.songQueue.append(song)
            print("songQueue: ", self.songQueue)
            await self.playSong()
        else:
            logging.debug("Adding playlist to queue.")
            for song in playlist:
                self.songQueue.append(song)
            print("songQueue: ", self.songQueue)

        # send the "Added to Queue" discord embed
        embed = discord.Embed(
            title="Playlist Added to Queue:",
            color=0xa600ff,
            )
        embed.set_thumbnail(url=thumbnail)
        for i, song in enumerate(playlist, start=1):
            embed.add_field(name=f"{i}", value=song.title, inline=False)
        await self.textChannel.send(embed=embed)
        return
        
    async def playSong(self):
        logging.debug("In playSong.")

        # check to make sure there is a song in queue
        if not self.songQueue:
            await self.textChannel.send("No more songs to play.")
            self.start_time = None
            self.pause_duration = 0
            self.pause_start = None
            return

        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -filter:a "volume=0.7"'
        }

        # get the next song to play
        song = self.songQueue[0]

        if not song.isFile:
            if getSongExpiration(song.link) <= int(time.time()):
                logging.debug(f"Stream URL is expired. Fetching new one")
                # get the song info from the link
                searcher = VideoSearcher()
                try:
                    result = await searcher.getVideoInfoFromURL(song.url)
                except Exception as e:
                    logging.error(e)
                    await self.textChannel.send(f"Unable to add song: {e}")
                    return
                # update the current songs stream link
                song.link = result['link']

        # create the discord player for current song
        player = discord.FFmpegOpusAudio(song.link, **ffmpeg_options)

        # function to call after a song is done playing
        def after_playing(error):
            if error:
                logging.error(f"Error during playback: {error}")
            else:
                if self.isLooping:
                    logging.debug("Song finished, replaying previous song.")
                else:
                    logging.debug("Song finished, popping from queue and checking next")
                    if self.songQueue:
                        self.songQueue.pop(0)
                fut = asyncio.run_coroutine_threadsafe(self.playSong(), self.client.loop)
                fut.add_done_callback(lambda f: f.exception())

        # get the voice client and play the song
        voice_client = discord.utils.get(self.client.voice_clients, guild=self.guild)
        voice_client.play(player, after=after_playing)

        # start the duration timer
        self.start_time = int(time.time())
        self.pause_duration = 0
        self.pause_start = None

        # send the "Now Playing" discord embed
        embed = discord.Embed(
            title="Now Playing:",
            description=song.title,
            color=0xa600ff,
            )
        embed.set_thumbnail(url=song.thumbnail)
        await self.textChannel.send(embed=embed, view=MusicButtons(client= self.client))