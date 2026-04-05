import asyncio
import websockets
import sys

async def test_ws(url, headers):
    print(f"Testing {url} with headers {headers}...")
    try:
        async with websockets.connect(url, extra_headers=headers, open_timeout=5) as ws:
            print(f"SUCCESS: Connected to {url}")
            await ws.close()
    except Exception as e:
        print(f"FAILED: {e}")

async def main():
    # Pass host header
    headers = {
        "Host": "localhost:5180",
        "Origin": "http://localhost:5180"
    }
    await test_ws("ws://127.0.0.1:5180/schule-kopie/", headers)
    await test_ws("ws://127.0.0.1:5180/hmr", headers)

if __name__ == "__main__":
    asyncio.run(main())
