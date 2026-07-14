import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import _raw_db
from domains.channel_manager.providers.hotelrunner_pull_worker import run_hotelrunner_pull_once

async def main():
    print("Triggering HR Pull manually...")
    try:
        await run_hotelrunner_pull_once()
        print("Pull complete.")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
