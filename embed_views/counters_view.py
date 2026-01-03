import discord
from management.vip_users import VIPUsers
from management.word_counter import WordCounter

class CountersView(discord.ui.View):
    def __init__(self, bot, timeout=60):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.counterMessage = None
        self.removeCounterMessage = None
        self.removeKeywordMessage = None
        self.selectCounterMessage = None
        self.counters = None

    async def send_page(self, interaction: discord.Interaction, first_response=False):
        embed = discord.Embed(
            title=f"Word Counters:",
            color=0xa600ff,
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)

        # get the word counters list
        self.counters = await WordCounter().loadWordCounters()

        if len(self.counters[1]) <= 0:
            embed.description = "There are no Word Counters. Please add one."
        else:
            for counter_name, count in self.counters[1].items():
                keywords = [f"- '{k}'" for k, v in self.counters[0].items() if v == counter_name]
                embed.add_field(
                    name=f"{counter_name}: {count}",
                    value="\n".join(keywords) if keywords else "No keywords assigned.",
                    inline=False
                )

        if first_response:
            self.counterMessage = await interaction.response.send_message(embed=embed, view=self, ephemeral=False)
        else:
            await self.counterMessage.resource.edit(embed=embed, view=self)

    @discord.ui.button(label="Remove Counter", style=discord.ButtonStyle.danger, row=0)
    async def remove_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        # check if user is an admin
        vipUsers = await VIPUsers().loadVIPUserIDs()
        if interaction.user.id not in vipUsers:
            await interaction.response.send_message("Admin only command.", ephemeral=True)
            return
        
        if len(self.counters[1]) <= 0:
            await interaction.response.send_message("No Word Counters to remove.", ephemeral=True)
            return

        options = [
            discord.SelectOption(label=counter, value=counter)
            for counter in self.counters[1].keys()
        ]

        class RemoveCounterDropdown(discord.ui.Select):
            def __init__(self, parent_view):
                self.parent_view = parent_view
                super().__init__(placeholder="Select a Counter to remove...", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                counter_name = self.values[0]
                # remove the counter from the word counter list
                await WordCounter().removeCounter(counter_name)

                await select_interaction.response.send_message(f"Removed Counter: {counter_name}", ephemeral=True)
                await self.parent_view.send_page(interaction)
                await self.parent_view.removeCounterMessage.resource.delete()

        view = discord.ui.View()
        view.add_item(RemoveCounterDropdown(self))
        self.removeCounterMessage = await interaction.response.send_message("Choose a counter to remove:", view=view, ephemeral=True)

    @discord.ui.button(label="Remove Keyword", style=discord.ButtonStyle.danger, row=0)
    async def remove_keyword(self, interaction: discord.Interaction, button: discord.ui.Button):
        # check if user is an admin
        vipUsers = await VIPUsers().loadVIPUserIDs()
        if interaction.user.id not in vipUsers:
            await interaction.response.send_message("Admin only command.", ephemeral=True)
            return
        
        if len(self.counters[1]) <= 0:
            await interaction.response.send_message("No Word Counters to remove keyword from.", ephemeral=True)
            return

        options = [
            discord.SelectOption(label=counter, value=counter)
            for counter in self.counters[1].keys()
        ]

        class SelectCounterDropdown(discord.ui.Select):
            def __init__(self, parent_view):
                self.parent_view = parent_view
                super().__init__(placeholder="Select a Counter...", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                counter_name = self.values[0]
                # Load keywords linked to this counter
                data = await WordCounter().loadWordCounters()
                keywords = [k for k, v in data[0].items() if v == counter_name]

                if not keywords:
                    await select_interaction.response.send_message(f"No keywords found for `{counter_name}`.", ephemeral=True)
                    return
                
                keyword_options = [
                    discord.SelectOption(label=kw, value=kw) for kw in keywords
                ]

                class RemoveKeywordDropdown(discord.ui.Select):
                    def __init__(self, parent_view):
                        self.parent_view = parent_view
                        super().__init__(placeholder="Select a Keyword to remove...", options=keyword_options)

                    async def callback(self, keyword_interaction: discord.Interaction):
                        keyword_to_remove = self.values[0]
                        await WordCounter().removeKeyword(keyword_to_remove)
                        await keyword_interaction.response.send_message(f"Removed keyword `{keyword_to_remove}` from `{counter_name}`.", ephemeral=True)
                        await self.parent_view.send_page(interaction)
                        await self.parent_view.selectCounterMessage.resource.delete()
                        await self.parent_view.removeKeywordMessage.resource.delete()

                # Show keyword selector
                keyword_view = discord.ui.View()
                keyword_view.add_item(RemoveKeywordDropdown(self.parent_view))
                self.parent_view.removeKeywordMessage = await select_interaction.response.send_message(f"Select a keyword to remove from `{counter_name}`:", view=keyword_view, ephemeral=True)

        view = discord.ui.View()
        view.add_item(SelectCounterDropdown(self))
        self.selectCounterMessage = await interaction.response.send_message("Select the counter you want to remove the keyword from:", view=view, ephemeral=True)

    @discord.ui.button(label="Add Keyword", style=discord.ButtonStyle.primary, row=0)
    async def add_keyword(self, interaction: discord.Interaction, button: discord.ui.Button):
        # check if user is an admin
        vipUsers = await VIPUsers().loadVIPUserIDs()
        if interaction.user.id not in vipUsers:
            await interaction.response.send_message("Admin only command.", ephemeral=True)
            return

        class KeywordModal(discord.ui.Modal, title="Add Keyword and Counter"):
            def __init__(self, parent_view):
                super().__init__()
                self.parent_view = parent_view

                self.keyword_input = discord.ui.TextInput(
                    label="Keyword",
                    style=discord.TextStyle.short,
                    required=True
                )
                self.counter_input = discord.ui.TextInput(
                    label="Counter name",
                    style=discord.TextStyle.short,
                    required=True
                )

                self.add_item(self.keyword_input)
                self.add_item(self.counter_input)

            async def on_submit(self, interaction: discord.Interaction):
                keyword = self.keyword_input.value.strip()
                counter = self.counter_input.value.strip()

                if not keyword or not counter:
                    await interaction.response.send_message("Keyword and counter cannot be empty.", ephemeral=True)
                    return

                await WordCounter().addKeyword(keyword, counter)
                await interaction.response.send_message(f"Added keyword `{keyword}` to counter `{counter}`.", ephemeral=True)
                await self.parent_view.send_page(interaction)

        await interaction.response.send_modal(KeywordModal(self))
