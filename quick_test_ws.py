import asyncio
import websockets
import sys

async def test():
    urls = [
        "ws://127.0.0.1:5180/schule-kopie/",
        "ws://localhost:5180/schule-kopie/",
        "ws://127.0.0.1:5180/",
        "ws://localhost:5180/"
    ]
    for url in urls:
        print(f"Trying {url}...")
        try:
            async with websockets.connect(url, open_timeout=2) as ws:
                print(f"SUCCESS: {url}")
                await ws.close()
        except asyncio.TimeoutError:
            print(f"TIMEOUT: {url}")
        except Exception as e:
            print(f"ERROR: {url} -> {e}")

if __name__ == "__main__":
    asyncio.run(test())
