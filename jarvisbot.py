import discord
import sys
import os
import asyncio
import logging
from pathlib import Path
from discord import app_commands
from dotenv import load_dotenv
from typing import Optional
from music_controller import MusicController
from management.banned_users import BannedUsers
from management.vip_users import VIPUsers
from embed_views.queue_view import QueueView
from embed_views.search_view import SearchView
from embed_views.keywords_view import KeywordsView
from embed_views.counters_view import CountersView

# set up logging
logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{Path(__file__).resolve().parent / 'bot_log.log'}", mode='w'),
        logging.StreamHandler()
    ]
)

# block discords logging
logging.getLogger("discord").setLevel(logging.WARNING)

class JarvisBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        # Load environment variables
        load_dotenv()
        self.token = os.getenv('DISCORD_TOKEN')

        self.musicControllers = {}

    # function to get the music controller for the specificied guild
    async def getGuildMusicController(self, guild: discord.Guild):
        if guild.id not in self.musicControllers:
            self.musicControllers[guild.id] = MusicController(client= self, guild= guild)
        return self.musicControllers[guild.id]
    
    # function to pop the music controller for the specificied guild
    async def popGuildMusicController(self, guild: discord.Guild):
        if guild.id in self.musicControllers:
            self.musicControllers.pop(guild.id)

    def restart_bot(self):
        os.execv(sys.executable, ['python'] + sys.argv)

    async def on_ready(self):
        logging.info(f"{self.user} is now running.")
        await bot.tree.sync()
        logging.info("commands synced")

    async def on_connect(self):
        logging.info(f"{self.user} has connected.")

    async def start_bot(self):
        await self.start(self.token)

bot = JarvisBot()

# event to disconnect or reconnect the bot from a voice channel based on number of members
@bot.event
async def on_voice_state_update(member, before, after):
    # make sure the bot itself doesn't trigger the event
    if member == bot.user:
        return
    
    # grab the musicController
    musicController = await bot.getGuildMusicController(member.guild)
    # grab the voice and text channel
    voiceChannel, textChannel = musicController.getVideoAndTextChannel()
    # check if bot is set to a channel
    if not voiceChannel or not textChannel:
        return
    
    # When a user joins a voice channel
    if before.channel is None and after.channel is not None:
        # if there is 1 member after joining, and the connected channel is the same as the /247 bot channel
        if len(after.channel.members) == 1 and after.channel == voiceChannel:
            await musicController.two_four_seven(voiceChannel, textChannel)

    # When a user leaves a voice channel
    elif before.channel is not None and after.channel is None:
        # if there is only the bot after leaving, and the connected channel is the same as the /247 bot channel
        if len(before.channel.members) == 1 and before.channel == voiceChannel:
            await musicController.softDisconnect()

    # When a user switches voice channels
    elif before.channel != after.channel:
        # if there is only the bot after leaving, and the connected channel is the same as the /247 bot channel
        if len(before.channel.members) == 1 and before.channel == voiceChannel:
            await musicController.softDisconnect()

        # if there is only 1 member at the after channel, and the connected channel is the same as the /247 bot channel
        if len(after.channel.members) == 1 and after.channel == voiceChannel:
            await musicController.two_four_seven(voiceChannel, textChannel)


@bot.tree.command(name='transcribe', description='Prints the voice chat. If no channel is selected, turns it off.')
async def transcribe(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    logging.info(f"{interaction.user.name} has activated /transcribe")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /transcribe function
    response = await musicController.setTranscriptionChannel(channel)
    if response:
        await interaction.response.send_message(f"Transcription Enabled in {response.name}.")
    else:
        await interaction.response.send_message(f"Transcription Disabled.")
    logging.debug(f"/transcribe from {interaction.user.name} has ended")
    return

@bot.tree.command(name='majorvote', description='Admin Only - Enables/Disables Majority Vote on Skipping or Stopping a Song.')
async def majorVote(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /majorvote")

    # check if user is an admin
    vipUsersClass = VIPUsers()
    vipUsers = await vipUsersClass.loadVIPUserIDs()
    if interaction.user.id not in vipUsers:
        await interaction.response.send_message(f"Admin only command.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /majorvote function
    response = await musicController.setMajorityVote()
    if response:
        await interaction.response.send_message(f"Majority Vote Enabled.")
    else:
        await interaction.response.send_message(f"Majority Vote Disabled.")
    logging.debug(f"/majorvote from {interaction.user.name} has ended")
    return

@bot.tree.command(name='ban', description='Admin Only - Ban a user from the bot.')
async def ban(interaction: discord.Interaction, user: discord.User):
    logging.info(f"{interaction.user.name} has activated /ban")

    # check if user is an admin
    vipUsersClass = VIPUsers()
    vipUsers = await vipUsersClass.loadVIPUserIDs()
    if interaction.user.id not in vipUsers:
        await interaction.response.send_message(f"Admin only command.")
        return
    
    logging.info(f"user to ban: {user.display_name} {user.id}")
    # get the banned user list
    bannedUsers = BannedUsers()
    # add to banned users
    await bannedUsers.addBannedUserID(user.id)
    await interaction.response.send_message(f"{user.display_name} has been banned.")
    logging.info(f"{user.display_name} has been banned")
    logging.debug(f"/ban from {interaction.user.name} has ended")
    return

@bot.tree.command(name='unban', description='Admin Only - UnBans a user from the bot.')
async def unban(interaction: discord.Interaction, user: discord.User):
    logging.info(f"{interaction.user.name} has activated /unban")

    # check if user is an admin
    vipUsersClass = VIPUsers()
    vipUsers = await vipUsersClass.loadVIPUserIDs()
    if interaction.user.id not in vipUsers:
        await interaction.response.send_message(f"Admin only command.")
        return
    
    logging.info(f"user to un-ban: {user.display_name} {user.id}")
    # get the banned user list
    bannedUsers = BannedUsers()
    # remove banned user
    await bannedUsers.removeBannedUserID(user.id)
    await interaction.response.send_message(f"{user.display_name} has been un-banned.")
    logging.info(f"{user.display_name} has been un-banned")
    logging.debug(f"/unban from {interaction.user.name} has ended")
    return

@bot.tree.command(name='keywords', description='Shows the available keywords to start voice commands.')
async def keywords(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /keywords")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the keywordsView Class
    view = KeywordsView(bot)
    # send the discord embed for the queue
    await view.send_page(interaction, first_response=True)
    logging.debug(f"/keywords from {interaction.user.name} has ended")
    return

# @bot.tree.command(name='counters', description='Shows all of the Word Counters, including their keywords and the amount.')
# async def counters(interaction: discord.Interaction):
#     logging.info(f"{interaction.user.name} has activated /counters")

#     # check if user is banned
#     bannedUsersClass = BannedUsers()
#     bannedUsers = await bannedUsersClass.loadBannedUserIDs()
#     if interaction.user.id in bannedUsers:
#         await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
#         return
    
#     # grab the countersView Class
#     view = CountersView(bot)
#     # send the discord embed for the queue
#     await view.send_page(interaction, first_response=True)
#     logging.debug(f"/counters from {interaction.user.name} has ended")
#     return

@bot.tree.command(name='addadmin', description='Admin Only - Adds a user as an admin.')
async def addAdmin(interaction: discord.Interaction, user: discord.User):
    logging.info(f"{interaction.user.name} has activated /addAdmin")

    # check if user is an admin
    vipUsersClass = VIPUsers()
    vipUsers = await vipUsersClass.loadVIPUserIDs()
    if interaction.user.id not in vipUsers:
        await interaction.response.send_message(f"Admin only command.")
        return
    
    logging.info(f"user to add as admin: {user.display_name} {user.id}")
    # add to vip users
    await vipUsersClass.addVIPUserID(user.id)
    await interaction.response.send_message(f"{user.display_name} has been added as an admin.")
    logging.info(f"{user.display_name} has been added as an admin.")
    logging.debug(f"/addAdmin from {interaction.user.name} has ended")
    return

@bot.tree.command(name='removeadmin', description='Admin Only - Removes user as an admin.')
async def removeAdmin(interaction: discord.Interaction, user: discord.User):
    logging.info(f"{interaction.user.name} has activated /removeAdmin")

    # check if user is an admin
    vipUsersClass = VIPUsers()
    vipUsers = await vipUsersClass.loadVIPUserIDs()
    if interaction.user.id not in vipUsers:
        await interaction.response.send_message(f"Admin only command.")
        return
    
    logging.info(f"user to remove as admin: {user.display_name} {user.id}")
    # remove admin user
    await vipUsersClass.removeVIPUserID(user.id)
    await interaction.response.send_message(f"{user.display_name} has been removed as an admin.")
    logging.info(f"{user.display_name} has been removed as an admin.")
    logging.debug(f"/removeAdmin from {interaction.user.name} has ended")
    return

@bot.tree.command(name='play', description='Play a Youtube, Spotify, or Soundcloud Song')
async def play(interaction: discord.Interaction, query: str):
    logging.info(f"{interaction.user.name} has activated /play")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return

    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # check if bot is connected to a voice channel
    if not musicController.isConnectedToVC():
        # check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You or the Bot must be in a voice channel to use this command.")
            return
        else:
            await musicController.two_four_seven(interaction.user.voice.channel, interaction.channel)

    # send initial response
    await interaction.response.send_message(f"Searching For Song...", delete_after= 5)

    # send the query to determine where the song comes from
    await musicController.determineSongSource(interaction.user, query)
    
    logging.debug(f"/play from {interaction.user.name} has ended")
    return

@bot.tree.command(name='playfile', description='Plays an Audio File.')
async def playfile(interaction: discord.Interaction, file: discord.Attachment):
    logging.info(f"{interaction.user.name} has activated /playfile")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return

    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # check if bot is connected to a voice channel
    if not musicController.isConnectedToVC():
        # check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You or the Bot must be in a voice channel to use this command.")
            return
        else:
            await musicController.two_four_seven(interaction.user.voice.channel, interaction.channel)

    # send initial response
    await interaction.response.send_message(f"Downloading Audio File: {file.filename}", delete_after= 3)

    # send the attachment to the music controller
    await musicController.handleFile(interaction.user, file)
    
    logging.debug(f"/playfile from {interaction.user.name} has ended")
    return

@bot.tree.command(name='247', description='Enables 24/7 Mode.')
async def two_four_seven(interaction: discord.Interaction, channel: discord.VoiceChannel):
    logging.info(f"{interaction.user.name} has activated /247")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return

    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # activate the /247 function
    response = await musicController.two_four_seven(channel, interaction.channel)
    if response:
        await interaction.response.send_message(f"Bot is currently in {response.channel.name}")
    else:
        await interaction.response.send_message(f"Enabling 24/7 Mode in {channel.name}")
    logging.debug(f"/247 from {interaction.user.name} has ended")
    return

@bot.tree.command(name='lofi', description='Plays a 24/7 Lofi Radio.')
async def lofi(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /lofi")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return

    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # check if bot is connected to a voice channel
    if not musicController.isConnectedToVC():
        # check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You or the Bot must be in a voice channel to use this command.")
            return
        else:
            await musicController.two_four_seven(interaction.user.voice.channel, interaction.channel)

    # send initial response
    await interaction.response.send_message(f"Searching For Song...", delete_after= 5)

    # stream link
    url = "https://www.youtube.com/watch?v=jfKfPfyJRdk"

    # send the query to determine where the song comes from
    await musicController.determineSongSource(interaction.user, url)
    
    logging.debug(f"/lofi from {interaction.user.name} has ended")
    return

@bot.tree.command(name='lofijazz', description='Plays a 24/7 Lofi Jazz Radio.')
async def lofijazz(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /lofijazz")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return

    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # check if bot is connected to a voice channel
    if not musicController.isConnectedToVC():
        # check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You or the Bot must be in a voice channel to use this command.")
            return
        else:
            await musicController.two_four_seven(interaction.user.voice.channel, interaction.channel)

    # send initial response
    await interaction.response.send_message(f"Searching For Song...", delete_after= 5)

    # stream link
    url = "https://www.youtube.com/watch?v=HuFYqnbVbzY"

    # send the query to determine where the song comes from
    await musicController.determineSongSource(interaction.user, url)
    
    logging.debug(f"/lofijazz from {interaction.user.name} has ended")
    return

@bot.tree.command(name='synthwave', description='Plays a 24/7 SynthWave Radio.')
async def synthwave(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /synthwave")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return

    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # check if bot is connected to a voice channel
    if not musicController.isConnectedToVC():
        # check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You or the Bot must be in a voice channel to use this command.")
            return
        else:
            await musicController.two_four_seven(interaction.user.voice.channel, interaction.channel)

    # send initial response
    await interaction.response.send_message(f"Searching For Song...", delete_after= 5)

    # stream link
    url = "https://www.youtube.com/watch?v=4xDzrJKXOOY"

    # send the query to determine where the song comes from
    await musicController.determineSongSource(interaction.user, url)
    
    logging.debug(f"/synthwave from {interaction.user.name} has ended")
    return
    
@bot.tree.command(name='pause', description='Pause the current song. Will resume the song if already paused.')
async def pause(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /pause")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /pause function
    response = await musicController.pauseSong()
    if response:
        await interaction.response.send_message(f"Pausing the song.")
    else:
        await interaction.response.send_message(f"Resuming Playback.")
    logging.debug(f"/pause from {interaction.user.name} has ended")
    return
    
@bot.tree.command(name='resume', description='Resume playback')
async def resume(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /resume")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /resume function
    await musicController.resumeSong()
    await interaction.response.send_message(f"Resuming Playback.")
    logging.debug(f"/resume from {interaction.user.name} has ended")
    return

@bot.tree.command(name='shuffle', description='Shuffles the queue.')
async def shuffle(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /shuffle")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /shuffle function
    await musicController.shuffleQueue()
    await interaction.response.send_message(f"Queue has been shuffled.")
    logging.debug(f"/shuffle from {interaction.user.name} has ended")
    return

@bot.tree.command(name='time', description='Get the duration of the current song.')
async def time(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /time")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /time function
    response = await musicController.getCurrentDuration()
    await interaction.response.send_message(f"{response}", ephemeral=True, delete_after=5)
    logging.debug(f"/time from {interaction.user.name} has ended")
    return

@bot.tree.command(name='stop', description='Stop playback and clear queue')
async def stop(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /stop")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    if not musicController.getIsMajorityVote():
        await interaction.response.send_message(f"Stopping playback and clearing queue.")
        # call the /stop function
        await musicController.stopAllSongs()
    else:
        message = await interaction.response.send_message(f"Stop current song and clear the queue? ***Needs all votes***")
        # call the /stop function
        await musicController.stopAllSongs(message=message.resource)
    logging.debug(f"/stop from {interaction.user.name} has ended")
    return

@bot.tree.command(name='dc', description='Kicks the bot from the voice channel, and turns off 24/7.')
async def kick(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /dc")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /dc function
    await musicController.hardDisconnect()
    # pop the music Controller
    await bot.popGuildMusicController(guild= interaction.guild)
    await interaction.response.send_message(f"Bot has been disconnected from the voice channel, and 24/7 has been disabled.")
    logging.debug(f"/dc from {interaction.user.name} has ended")
    return

@bot.tree.command(name='skip', description='Skip the current song')
async def skip(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /skip")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    if not musicController.getIsMajorityVote():
        await interaction.response.send_message(f"Skipping song.")
        # call the /skip function
        await musicController.skipSong()
    else:
        message = await interaction.response.send_message(f"Skip the Song?")
        # call the /skip function
        await musicController.skipSong(message=message.resource)
    logging.debug(f"/skip from {interaction.user.name} has ended")
    return

@bot.tree.command(name='loop', description='Loops the currently playing song.')
async def loop(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /loop")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # call the /loop function
    response = await musicController.setLooping()
    if response:
        await interaction.response.send_message(f"Looping Enabled.")
    else:
        await interaction.response.send_message(f"Looping Disabled.")
    logging.debug(f"/loop from {interaction.user.name} has ended")
    return

@bot.tree.command(name='queue', description='Display the queue')
async def queue(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /queue")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # get songQueue from the music controller
    queue = musicController.getSongQueue()
    # if no songs in queue
    if len(queue) <= 1:
        embed = discord.Embed(
            title="Queue",
            description="No songs in the queue.",
            color=0xa600ff,
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # grab the QueueView Class
    view = QueueView(queue, bot, interaction.user)
    # send the discord embed for the queue
    await view.send_page(interaction, first_response=True)
    logging.debug(f"/queue from {interaction.user.name} has ended")
    return

@bot.tree.command(name='search', description='Search for the top 10 results.')
async def search(interaction: discord.Interaction, query: str):
    logging.info(f"{interaction.user.name} has activated /search")

    # check if user is banned
    bannedUsersClass = BannedUsers()
    bannedUsers = await bannedUsersClass.loadBannedUserIDs()
    if interaction.user.id in bannedUsers:
        await interaction.response.send_message(f"User **{interaction.user.display_name}** is banned from the bot.")
        return
    
    # send the initial discord message
    await interaction.response.send_message(f"Searching Youtube: {query}", delete_after=3)
    # grab the music controller for designated guild
    musicController = await bot.getGuildMusicController(guild= interaction.guild)
    # search for the query
    result = await musicController.searchSongs(query)
    if not result:
        await interaction.channel.send(f"Failed to search youtube.")
        return
    # grab the SearchView Class
    view = SearchView(result, musicController, bot)
    # send the discord embed for the search
    await view.send_page(interaction)
    logging.debug(f"/search from {interaction.user.name} has ended")
    return

@bot.tree.command(name='sync', description='Admin only - Syncs the command tree.')
async def sync(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /sync")

    # check if user is an admin
    vipUsersClass = VIPUsers()
    vipUsers = await vipUsersClass.loadVIPUserIDs()
    if interaction.user.id not in vipUsers:
        await interaction.response.send_message(f"Admin only command.")
        return

    await bot.tree.sync()
    await interaction.response.send_message('Command tree synced.', delete_after=5)
    logging.info('Command tree synced.')

@bot.tree.command(name='restart', description='Admin only - Completely restart the bot.')
async def restart(interaction: discord.Interaction):
    logging.info(f"{interaction.user.name} has activated /restart")

    # check if user is an admin
    vipUsersClass = VIPUsers()
    vipUsers = await vipUsersClass.loadVIPUserIDs()
    if interaction.user.id not in vipUsers:
        await interaction.response.send_message(f"Admin only command.")
        return
    
    await interaction.response.send_message('Restarting Bot. If Bot is still in VC, disconnect them before doing a command.')
    logging.info('Restarting Bot')
    bot.restart_bot()

@bot.tree.command(name='help', description='List of all commands.')
async def help(interaction: discord.Interaction):
    
    embed = discord.Embed(
        title="All Commands",
        color=0xa600ff,
    )
    embed.add_field(name="/Play", value="Enter a URL or the name of the song, will play or queue the song. Youtube, Spotify, and SoundCloud only.", inline=True)
    embed.add_field(name="/PlayFile", value="Plays or queues an audio file.", inline=False)
    embed.add_field(name="/247", value="Enables 24/7 Mode in a channel.", inline=False)
    embed.add_field(name="/DC", value="Kicks the bot from the voice channel, and turns off 24/7.", inline=False)
    embed.add_field(name="/Transcribe", value="Prints the voice chat. If no channel is selected, turns it off.", inline=False)
    embed.add_field(name="/Lofi", value="Plays a 24/7 Lofi Radio.", inline=False)
    embed.add_field(name="/LofiJazz", value="Plays a 24/7 Lofi Jazz Radio.", inline=False)
    embed.add_field(name="/SynthWave", value="Plays a 24/7 SynthWave Radio.", inline=False)
    embed.add_field(name="/Shuffle", value="Shuffles the queue.", inline=False)
    embed.add_field(name="/Loop", value="Enables/Disables Looping on the current song.", inline=False)
    embed.add_field(name="/Time", value="Get the duration of the current song.", inline=False)
    embed.add_field(name="/Stop", value="Stops playing the current song, and removes all songs from queue.", inline=False)
    embed.add_field(name="/Skip", value="Skips the current song.", inline=False)
    embed.add_field(name="/Pause", value="Pauses the current song.", inline=False)
    embed.add_field(name="/Resume", value="Resumes the current song from where it left off.", inline=False)
    embed.add_field(name="/Queue", value="Shows the queue of songs, can move or remove songs from queue here.", inline=False)
    embed.add_field(name="/Search", value="Searches for top 10 results of a song. Use this in case you can't find what you want.", inline=False)
    embed.add_field(name="/MajorVote", value="Admin Only - Enables/Disables Majority Vote on Skipping or Stopping a Song.", inline=False)
    embed.add_field(name="/Restart", value="Admin Only - Restarts the bot.", inline=False)
    embed.add_field(name="/Ban", value="Admin Only - Bans a user from using the bot.", inline=False)
    embed.add_field(name="/Unban", value="Admin Only - Un bans a user from the bot.", inline=False)
    embed.add_field(name="/AddAdmin", value="Admin Only - Makes the user an admin.", inline=False)
    embed.add_field(name="/RemoveAdmin", value="Admin Only - Removes admin from user.", inline=False)
    embed.add_field(name="Available Voice Commands:", value="'Jarvis play', 'Jarvis skip', 'Jarvis next', 'Jarvis loop', 'Jarvis pause', 'Jarvis stop'", inline=False)
    embed.set_thumbnail(url=bot.user.avatar.url)
    await interaction.response.send_message(embed=embed)
    

if __name__ == "__main__":
    asyncio.run(bot.start_bot())