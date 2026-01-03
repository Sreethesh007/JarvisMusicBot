import discord

class SearchView(discord.ui.View):
    def __init__(self, songs, musicController, bot):
        super().__init__(timeout=None)
        self.songs = songs
        self.musicController = musicController
        self.bot = bot

    async def send_page(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"Search Results:",
            color=0xa600ff,
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        for i, song in enumerate(self.songs, start=1):
            embed.add_field(name=f"{i}", value=song['title'], inline=False)
        
        class SongDropdown(discord.ui.Select):
            def __init__(self, parent_view):
                self.parent_view = parent_view
                options = [
                    discord.SelectOption(label=f"{i+1}. {s['title']}", value=str(i))
                    for i, s in enumerate(parent_view.songs)
                ]
                super().__init__(placeholder="Select a song to queue...", options=options)

            async def callback(self, interaction: discord.Interaction):
                index = int(self.values[0])
                song = self.parent_view.songs[index]

                # check if bot is connected to a voice channel
                if not self.parent_view.musicController.isConnectedToVC():
                    # check if user is in a voice channel
                    if not interaction.user.voice or not interaction.user.voice.channel:
                        await interaction.response.send_message("You or the Bot must be in a voice channel to use this command.")
                        return
                    else:
                        await self.parent_view.musicController.two_four_seven(interaction.user.voice.channel, interaction.channel)

                await interaction.response.send_message(f"Adding **{song['title']}**", delete_after=5)
                await self.parent_view.musicController.determineSongSource(interaction.user, song['link'])          

        dropdown_view = discord.ui.View()
        dropdown_view.add_item(SongDropdown(self))

        await interaction.channel.send(embed=embed, view=dropdown_view)