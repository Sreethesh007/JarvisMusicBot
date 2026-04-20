import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import asyncio
import time
from management.nlp_processor import NLPProcessor
import os

os.environ["USE_AI_INTENT"] = "True"
os.environ["GEMINI_API_KEY"] = "dummy"

async def test_init():
    ticks = []
    async def ticker():
        for i in range(25):
            ticks.append(time.time())
            await asyncio.sleep(0.1)

    t = asyncio.create_task(ticker())

    t0 = time.time()
    nlp = NLPProcessor()
    print("Init time:", time.time() - t0)

    await t
    max_delay = max(ticks[i] - ticks[i-1] for i in range(1, len(ticks)))
    print(f"Max loop delay: {max_delay:.3f}s")

asyncio.run(test_init())
