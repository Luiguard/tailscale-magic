import asyncio
import websockets
import sys

async def test(url):
    headers = {
        "Host": "localhost:5180",
        "Origin": "http://localhost:5180"
    }
    print(f"Connecting to {url}...")
    try:
        async with websockets.connect(url, additional_headers=headers, open_timeout=5) as ws:
            print(f"SUCCESS: {url}")
            await ws.close()
    except Exception as e:
        print(f"FAILED {url}: {e}")

async def main():
    await test("ws://127.0.0.1:5180/schule-kopie/hmr")
    await test("ws://127.0.0.1:5180/hmr")
    await test("ws://127.0.0.1:5180/")

if __name__ == "__main__":
    asyncio.run(main())
