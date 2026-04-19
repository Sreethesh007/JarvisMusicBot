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
sys.modules['management.nlp_processor'] = MagicMock()
sys.modules['scripts.ytDLP'] = MagicMock()
sys.modules['scripts.ytDLP'].getSongExpiration = MagicMock(return_value=9999999999)
sys.modules['scripts.spotify'] = MagicMock()

from music_controller import MusicController, RealTimeSpeechRecognitionSink
import music_controller

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

class TestEventLoopBlocking(unittest.IsolatedAsyncioTestCase):
    async def test_play_song_does_not_block(self):
        client = MockClient()
        guild = MockGuild()
        mc = MusicController(client, guild)
        mc.textChannel = MockChannel()
        mc.transcriptionChannel = MockChannel()
        client.voice_clients.append(MockVoiceClient(MockChannel()))

        discord.utils.get = MagicMock(return_value=client.voice_clients[0])

        # Override ffmpeg instances to bypass actual command execution and Popen
        discord.FFmpegOpusAudio = MagicMock()
        discord.FFmpegPCMAudio = MagicMock()

        # In the modified codebase, we need to mock the executor properly if it runs FFmpeg
        original_run_in_executor = client.loop.run_in_executor

        async def mock_run_in_executor(executor, func, *args):
            # This is where we want to simulate a long blocking Popen call from FFmpeg
            if "FFmpeg" in str(func) or "recognize_google" in str(func):
                time.sleep(1.5)  # Blocking simulation
            return MagicMock()

        # Wait, run_in_executor doesn't block the loop itself. Let's just patch Popen.
        import subprocess
        original_popen = subprocess.Popen
        def slow_popen(*args, **kwargs):
            time.sleep(1.5)
            return MagicMock()
        subprocess.Popen = slow_popen

        ticks = []
        async def ticker():
            for i in range(25):
                ticks.append(time.time())
                await asyncio.sleep(0.1)

        task = asyncio.create_task(ticker())

        mc.generate_tts = AsyncMock()

        # Start playing a song, this should trigger the slow Popen if the loop isn't patched
        # If the code uses run_in_executor for FFmpeg, then slow_popen will not block the ticker.
        # But wait, we mocked FFmpegOpusAudio above, so slow_popen won't be called.
        # Let's unmock FFmpegOpusAudio and just catch the missing ffmpeg error,
        # actually no, we can let FFmpegOpusAudio fail IF it runs in the main loop,
        # OR we can mock the exact function

        # Let's restore the original FFmpeg classes
        import importlib
        importlib.reload(discord.player)
        discord.FFmpegOpusAudio = discord.player.FFmpegOpusAudio
        discord.FFmpegPCMAudio = discord.player.FFmpegPCMAudio

        # we still use the slow_popen to simulate a blocking process start.
        # To avoid the ClientException, we also need to fake the executable
        def fake_popen(*args, **kwargs):
            time.sleep(1.5)
            mock = MagicMock()
            mock.poll.return_value = None
            return mock
        subprocess.Popen = fake_popen

        # Also need to fake shutil.which so that Pycord thinks ffmpeg exists
        import shutil
        original_which = shutil.which
        shutil.which = MagicMock(return_value="/fake/ffmpeg")

        # Now trigger the song
        await mc.handleFile(MockUser(), MagicMock())

        await task

        subprocess.Popen = original_popen
        shutil.which = original_which

        max_delay = max(ticks[i] - ticks[i-1] for i in range(1, len(ticks)))
        print(f"Max loop delay: {max_delay:.3f}s")

        self.assertLess(max_delay, 1.0, "Event loop was blocked by playSong")

if __name__ == "__main__":
    unittest.main()
