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

# Instead of overwriting NLPProcessor globally via sys.modules, patch it directly on MusicController instance
sys.modules['scripts.ytDLP'] = MagicMock()
sys.modules['scripts.ytDLP'].getSongExpiration = MagicMock(return_value=9999999999)
sys.modules['scripts.spotify'] = MagicMock()

from music_controller import MusicController

logging.basicConfig(level=logging.DEBUG)

class MockClient:
    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.voice_clients = []
        self.tree = MagicMock()

    async def wait_for(self, *args, **kwargs):
        pass

    @property
    def user(self):
        user = MagicMock()
        user.avatar.url = "http://fake.url"
        return user

class MockGuild:
    def __init__(self):
        self.id = 1234
        self.name = "Test Guild"

class MockUser:
    def __init__(self):
        self.id = 5678
        self.display_name = "TestUser"

class MockChannel:
    async def send(self, *args, **kwargs):
        pass

class MockVoiceClient:
    def __init__(self, channel):
        self.channel = channel
        self.recording = False

    def start_recording(self, sink, callback, *args):
        self.sink = sink

    def play(self, *args, **kwargs):
        pass
    def is_connected(self):
        return True

class TestHandleTranscribedAudio(unittest.IsolatedAsyncioTestCase):
    async def test_handle_transcribed_audio(self):
        client = MockClient()
        guild = MockGuild()
        mc = MusicController(client, guild)
        mc.textChannel = MockChannel()
        mc.transcriptionChannel = MockChannel()
        client.voice_clients.append(MockVoiceClient(MockChannel()))

        discord.utils.get = MagicMock(return_value=client.voice_clients[0])
        discord.FFmpegOpusAudio = MagicMock()
        discord.FFmpegPCMAudio = MagicMock()

        mc._get_bot_keywords = AsyncMock(return_value=['jarvis'])
        mc.generate_tts = AsyncMock()

        # safely mock the instance method
        mc.nlp_processor = MagicMock()
        mc.nlp_processor.determine_intent = AsyncMock(return_value=("play", "test song"))
        mc.handleYoutubeSearch = AsyncMock()

        ticks = []
        async def ticker():
            for i in range(25):
                ticks.append(time.time())
                await asyncio.sleep(0.1)

        task = asyncio.create_task(ticker())

        await mc.handleTranscribedAudio(MockUser(), "Jarvis play test song")

        await task

        max_delay = max(ticks[i] - ticks[i-1] for i in range(1, len(ticks)))
        print(f"Max loop delay: {max_delay:.3f}s")

        self.assertLess(max_delay, 1.0, "Event loop was blocked by handleTranscribedAudio")

if __name__ == "__main__":
    unittest.main()
