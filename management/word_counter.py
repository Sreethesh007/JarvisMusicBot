import json
from pathlib import Path
import logging
import aiofiles
import asyncio

class WordCounter:
    def __init__(self):
        root_dir = Path(__file__).resolve().parent
        self.word_counters_file = root_dir / "word_counters.json"

        if not self.word_counters_file.exists():
            default_data = [
                {"unreal": "unreal", "unruh": "unreal"},
                {"unreal": 0}
            ]
            self.word_counters_file.write_text(json.dumps(default_data, indent=2))

    async def loadWordCounters(self):
        async with aiofiles.open(self.word_counters_file, "r") as f:
            content = await f.read()
            return json.loads(content)

    async def saveWordCounters(self, data):
        async with aiofiles.open(self.word_counters_file, "w") as f:
            await f.write(json.dumps(data, indent=2))

    async def addKeyword(self, keyword: str, counter_name: str):
        data = await self.loadWordCounters()
        mapping = data[0]
        if keyword not in mapping:
            mapping[keyword] = counter_name
            if counter_name not in data[1]:
                data[1][counter_name] = 0
            await self.saveWordCounters(data)

    async def removeKeyword(self, keyword: str):
        data = await self.loadWordCounters()
        mapping = data[0]
        if keyword in mapping:
            del mapping[keyword]
            await self.saveWordCounters(data)

    async def removeCounter(self, counter_name: str):
        data = await self.loadWordCounters()
        mapping = data[0]
        counters = data[1]
        mapping = {k: v for k, v in mapping.items() if v != counter_name}
        if counter_name in counters:
            del counters[counter_name]
        await self.saveWordCounters([mapping, counters])

    async def incrementCounterForKeyword(self, keyword: str):
        data = await self.loadWordCounters()
        mapping = data[0]
        counters = data[1]

        if keyword in mapping:
            counter_name = mapping[keyword]
            if counter_name in counters:
                counters[counter_name] += 1
            else:
                counters[counter_name] = 1
            await self.saveWordCounters(data)

    async def getCount(self, counter_name: str) -> int:
        data = await self.loadWordCounters()
        return data[1].get(counter_name, 0)

    async def getAllCounts(self):
        data = await self.loadWordCounters()
        return data[1]