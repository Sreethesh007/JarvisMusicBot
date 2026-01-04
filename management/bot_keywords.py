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
            self.bot_keywords_file.write_text(json.dumps(["jarvis"]))  # start with default keyword

    # Load keywords
    async def loadBotKeywords(self):
        async with aiofiles.open(self.bot_keywords_file, "r") as f:
            content = await f.read()
            # Normalize keywords to lowercase to ensure case-insensitive matching
            return [k.lower() for k in json.loads(content)]

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
        key_lower = keyword.lower()
        if key_lower in keywords:
            keywords.remove(key_lower)
            await self.saveBotKeywords(keywords)