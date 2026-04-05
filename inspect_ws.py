import websockets
import inspect

print("websockets version:", websockets.__version__)
print("websockets.connect signature:", inspect.signature(websockets.connect))
