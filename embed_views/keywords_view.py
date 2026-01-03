import discord
from management.vip_users import VIPUsers
from management.bot_keywords import BotKeywords

class KeywordsView(discord.ui.View):
    def __init__(self, bot, timeout=60):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.keywordMessage = None
        self.removeMessage = None
        self.keywords = None

    async def send_page(self, interaction: discord.Interaction, first_response=False):
        embed = discord.Embed(
            title=f"Available Keywords:",
            color=0xa600ff,
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)

        # get the bot keywords list
        self.keywords = await BotKeywords().loadBotKeywords()

        if len(self.keywords) <= 0:
            embed.description = "There are no available keywords. Please add one."
        else:
            for keyword in self.keywords:
                embed.add_field(name=f"", value=f"'{keyword}'", inline=False)

        if first_response:
            self.keywordMessage = await interaction.response.send_message(embed=embed, view=self, ephemeral=False)
        else:
            await self.keywordMessage.resource.edit(embed=embed, view=self)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, row=0)
    async def remove_from_keywords(self, interaction: discord.Interaction, button: discord.ui.Button):
        # check if user is an admin
        vipUsers = await VIPUsers().loadVIPUserIDs()
        if interaction.user.id not in vipUsers:
            await interaction.response.send_message("Admin only command.", ephemeral=True)
            return
        
        if len(self.keywords) <= 0:
            await interaction.response.send_message("No keywords to remove.", ephemeral=True)
            return

        options = [
            discord.SelectOption(label=keyword, value=str(i))
            for i, keyword in enumerate(self.keywords, start=1)
        ]

        class RemoveDropdown(discord.ui.Select):
            def __init__(self, parent_view):
                self.parent_view = parent_view
                super().__init__(placeholder="Select a keyword to remove...", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                index = (int(self.values[0]) - 1)
                removed_keyword = self.parent_view.keywords.pop(index)
                # remove the keyword from the bot keywords list
                await BotKeywords().removeBotKeyword(removed_keyword)

                await select_interaction.response.send_message(f"Removed keyword: {removed_keyword}", ephemeral=True)
                await self.parent_view.send_page(interaction)
                await self.parent_view.removeMessage.resource.delete()

        view = discord.ui.View()
        view.add_item(RemoveDropdown(self))
        self.removeMessage = await interaction.response.send_message("Choose a keyword to remove:", view=view, ephemeral=True)

    @discord.ui.button(label="Add", style=discord.ButtonStyle.primary, row=0)
    async def add_to_keywords(self, interaction: discord.Interaction, button: discord.ui.Button):
        # check if user is an admin
        vipUsers = await VIPUsers().loadVIPUserIDs()
        if interaction.user.id not in vipUsers:
            await interaction.response.send_message("Admin only command.", ephemeral=True)
            return

        class MoveToModal(discord.ui.Modal, title="Add A Keyword"):
            def __init__(self, parent_view):
                super().__init__()
                self.parent_view = parent_view
                self.keyword_input = discord.ui.TextInput(
                    label="Enter the new keyword:",
                    style=discord.TextStyle.short,
                    required=True,
                )
                self.add_item(self.keyword_input)

            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    new_keyword = str(self.keyword_input.value)
                    if len(new_keyword) <= 0:
                        raise ValueError("Keyword can't be empty.")

                    self.parent_view.keywords.append(new_keyword)
                    # add the keyword from the bot keywords list
                    await BotKeywords().addBotKeyword(new_keyword)
                    await modal_interaction.response.send_message(f"Added new keyword: '{new_keyword}'.", ephemeral=True)
                    await self.parent_view.send_page(interaction)
                except Exception as e:
                    await modal_interaction.response.send_message(f"Error: {e}", ephemeral=True)

        await interaction.response.send_modal(MoveToModal(self))
