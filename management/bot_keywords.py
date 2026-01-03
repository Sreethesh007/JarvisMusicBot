import json
import os
from pathlib import Path
import logging
import aiofiles
import asyncio

class BotKeywords:
    def __init__(self):
        # Get root directory of script
        root_dir = Path(__file__).resolve().parent
        self.bot_keywords_file = root_dir / "bot_keywords.json"
        # Ensure file exists
        if not self.bot_keywords_file.exists():
            self.bot_keywords_file.write_text(json.dumps(["Jarvis"]))  # start with empty list

    # Load keywords
    async def loadBotKeywords(self):
        async with aiofiles.open(self.bot_keywords_file, "r") as f:
            content = await f.read()
            return json.loads(content)

    # Save keywords
    async def saveBotKeywords(self, keyword):
        async with aiofiles.open(self.bot_keywords_file, "w") as f:
            await f.write(json.dumps(keyword, indent=2))

    # Add keyword if not already present
    async def addBotKeyword(self, keyword: str):
        keywords = await self.loadBotKeywords()
        if keyword not in keywords:
            keywords.append(keyword.lower())
            await self.saveBotKeywords(keywords)

    # Remove keyword if present
    async def removeBotKeyword(self, keyword: str):
        keywords = await self.loadBotKeywords()
        if keyword in keywords:
            keywords.remove(keyword)
            await self.saveBotKeywords(keywords)