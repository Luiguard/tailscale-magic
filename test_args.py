import asyncio
import websockets
import sys
import inspect

async def main():
    print("websockets version:", websockets.__version__)
    # Try with extra_headers
    try:
        async with websockets.connect("ws://127.0.0.1:9999", extra_headers={"X": "Y"}, open_timeout=1):
            pass
    except Exception as e:
        print("extra_headers error:", e)

    # Try with additional_headers
    try:
        async with websockets.connect("ws://127.0.0.1:9999", additional_headers={"X": "Y"}, open_timeout=1):
            pass
    except Exception as e:
        print("additional_headers error:", e)

if __name__ == "__main__":
    asyncio.run(main())
