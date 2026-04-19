import sys
import asyncio
import time
import logging
import unittest
from unittest.mock import MagicMock, AsyncMock

try:
    import discord
except ImportError:
    pass

import sys
# Mock the heavier modules to prevent import errors and speed up tests
sys.modules['speech_recognition'] = MagicMock()
sys.modules['webrtcvad'] = MagicMock()
sys.modules['edge_tts'] = MagicMock()

# Mock out complex things
class MockBannedUsers:
    async def loadBannedUserIDs(self):
        return []
sys.modules['management.banned_users'] = MagicMock()
sys.modules['management.banned_users'].BannedUsers = MockBannedUsers

sys.modules['management.bot_keywords'] = MagicMock()
sys.modules['management.vip_users'] = MagicMock()
sys.modules['scripts.ytDLP'] = MagicMock()
sys.modules['scripts.ytDLP'].getSongExpiration = MagicMock(return_value=9999999999)
sys.modules['scripts.spotify'] = MagicMock()

from management.nlp_processor import NLPProcessor

logging.basicConfig(level=logging.DEBUG)

class TestEventLoopBlocking(unittest.IsolatedAsyncioTestCase):
    async def test_intent_nlp_processor(self):
        ticks = []
        async def ticker():
            for i in range(25):
                ticks.append(time.time())
                await asyncio.sleep(0.1)

        task = asyncio.create_task(ticker())

        processor = NLPProcessor()
        processor.use_ai = False # Local testing is fast

        t0 = time.time()

        intent, query = await processor.determine_intent("play some song")

        await task

        max_delay = max(ticks[i] - ticks[i-1] for i in range(1, len(ticks)))
        print(f"Max loop delay: {max_delay:.3f}s")

        self.assertLess(max_delay, 1.0, "Event loop was blocked by NLP Processor")

if __name__ == "__main__":
    unittest.main()
