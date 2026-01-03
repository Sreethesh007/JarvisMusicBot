import discord
import math
from management.vip_users import VIPUsers

class QueueView(discord.ui.View):
    def __init__(self, queue, bot, author, timeout=60):
        super().__init__(timeout=timeout)
        self.queue = queue
        self.bot = bot
        self.author = author
        self.page = 0
        self.max_pages = math.ceil((len(self.queue) - 1) / 25)
        self.selected_song_index = None
        self.queueMessage = None
        self.removeMessage = None
        self.moveMessage = None

    async def send_page(self, interaction: discord.Interaction, first_response=False):
        start = self.page * 25 + 1
        end = start + 25
        songs = self.queue[start:end]

        embed = discord.Embed(
            title=f"Queue (Page {self.page + 1}/{self.max_pages})",
            color=0xa600ff,
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        for i, song in enumerate(songs, start=start):
            embed.add_field(name=f"{i}", value=song.title, inline=False)

        if first_response:
            self.queueMessage = await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
        else:
            if len(self.queue) <= 1:
                embed = discord.Embed(
                    title="Queue",
                    description="No songs in the queue.",
                    color=0xa600ff,
                )
                embed.set_thumbnail(url=self.bot.user.avatar.url)
                await self.queueMessage.resource.edit(embed=embed, view=None)
            else:
                await self.queueMessage.resource.edit(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You can't control this queue.", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            await interaction.response.send_message(f"Now viewing Page {self.page + 1}.", ephemeral=True, delete_after=2)
            await self.send_page(interaction)
        else:
            await interaction.response.send_message("Already on the first page.", ephemeral=True)

    @discord.ui.button(label="Remove From Queue", style=discord.ButtonStyle.danger, row=0)
    async def remove_from_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You can't control this queue.", ephemeral=True)
            return

        start = self.page * 25 + 1
        end = start + 25
        options = [
            discord.SelectOption(label=song.title, value=str(i))
            for i, song in enumerate(self.queue[start:end], start=start)
        ]

        class RemoveDropdown(discord.ui.Select):
            def __init__(self, parent_view):
                self.parent_view = parent_view
                super().__init__(placeholder="Select a song to remove...", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                index = int(self.values[0])
                songUser = self.parent_view.queue[index].user

                # check if user is an admin
                vipUsersClass = VIPUsers()
                vipUsers = await vipUsersClass.loadVIPUserIDs()
                if select_interaction.user.id in vipUsers or select_interaction.user.id == songUser.id:
                    removed_song = self.parent_view.queue.pop(index)
                    await self.parent_view.removeMessage.resource.delete()
                    await select_interaction.response.send_message(f"Removed: {removed_song.title}", ephemeral=True)
                    await self.parent_view.send_page(interaction)
                else:
                    await select_interaction.response.send_message(f"Can't remove a song that you didn't queue. Song was queued by: {songUser.display_name}", ephemeral=True)

        view = discord.ui.View()
        view.add_item(RemoveDropdown(self))
        self.removeMessage = await interaction.response.send_message("Choose a song to remove:", view=view, ephemeral=True)

    @discord.ui.button(label="Move Song", style=discord.ButtonStyle.primary, row=0)
    async def move_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You can't control this queue.", ephemeral=True)
            return

        start = self.page * 25 + 1
        end = start + 25
        current_songs = self.queue[start:end]

        options = [
            discord.SelectOption(label=song.title, value=str(i))
            for i, song in enumerate(current_songs, start=start)
        ]

        class SelectSongToMove(discord.ui.Select):
            def __init__(self, parent_view):
                self.parent_view = parent_view
                super().__init__(placeholder="Select a song to move...", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                self.parent_view.selected_song_index = int(self.values[0])

                class MoveToModal(discord.ui.Modal, title="Move Song To Position"):
                    def __init__(self, parent_view):
                        super().__init__()
                        self.parent_view = parent_view
                        self.position_input = discord.ui.TextInput(
                            label="Enter the new position:",
                            style=discord.TextStyle.short,
                            required=True,
                            max_length=3
                        )
                        self.add_item(self.position_input)

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        try:
                            new_index = int(self.position_input.value)
                            if new_index < 1 or new_index >= len(self.parent_view.queue):
                                raise ValueError("Invalid position: out of bounds or cannot move to index 0.")
                            from_index = self.parent_view.selected_song_index
                            songUser = self.parent_view.queue[from_index].user

                            # check if user is an admin
                            vipUsersClass = VIPUsers()
                            vipUsers = await vipUsersClass.loadVIPUserIDs()
                            if modal_interaction.user.id in vipUsers or modal_interaction.user.id == songUser.id:
                                song = self.parent_view.queue.pop(from_index)
                                self.parent_view.queue.insert(new_index, song)
                                await modal_interaction.response.send_message(f"Moved song to position {new_index}.", ephemeral=True)
                                await self.parent_view.send_page(interaction)
                                await self.parent_view.moveMessage.resource.delete()
                            else:
                                await modal_interaction.response.send_message(f"Can't move a song that you didn't queue. Song was queued by: {songUser.display_name}", ephemeral=True)
                        except Exception as e:
                            await modal_interaction.response.send_message(f"Error: {e}", ephemeral=True)

                await select_interaction.response.send_modal(MoveToModal(self.parent_view))

        view = discord.ui.View()
        view.add_item(SelectSongToMove(self))
        self.moveMessage = await interaction.response.send_message("Select a song to move:", view=view, ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You can't control this queue. Please use /queue yourself.", ephemeral=True)
            return
        if self.page < self.max_pages - 1:
            self.page += 1
            await interaction.response.send_message(f"Now viewing Page {self.page + 1}.", ephemeral=True, delete_after=2)
            await self.send_page(interaction)
        else:
            await interaction.response.send_message("No more pages left.", ephemeral=True)
