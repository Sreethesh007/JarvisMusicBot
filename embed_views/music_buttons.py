import discord

class MusicButtons(discord.ui.View):
    def __init__(self, client):
        super().__init__(timeout=None)
        self.tree = client.tree

    @discord.ui.button(label="⏸", style=discord.ButtonStyle.secondary, row=0)
    async def PauseResume_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('pause').callback(interaction)

    @discord.ui.button(label="⏭", style=discord.ButtonStyle.secondary, row=0)
    async def Skip_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('skip').callback(interaction)

    @discord.ui.button(label="⏹", style=discord.ButtonStyle.secondary, row=0)
    async def Stop_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('stop').callback(interaction)

    @discord.ui.button(label="⟳", style=discord.ButtonStyle.secondary, row=0)
    async def Loop_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('loop').callback(interaction)

    @discord.ui.button(label="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def Shuffle_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('shuffle').callback(interaction)

    @discord.ui.button(label="⌛", style=discord.ButtonStyle.secondary, row=1)
    async def Time_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('time').callback(interaction)

    @discord.ui.button(label="☰", style=discord.ButtonStyle.secondary, row=1)
    async def Queue_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('queue').callback(interaction)

    @discord.ui.button(label="🛑", style=discord.ButtonStyle.secondary, row=1)
    async def Kick_Button(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.tree.get_command('dc').callback(interaction)