import asyncio
import websockets
import json
import socket

async def test_websocket_connection():
    uri = "ws://127.0.0.1:8000/ws/notifications/"
    print(f"Attempting to connect to {uri} without token (expecting rejection)...")
    
    # Check if port is open first
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 8000))
    if result != 0:
        print("Error: Port 8000 is not open. Is the Django server running?")
        return

    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Waiting for message...")
            # We expect the server to close the connection or send a rejection if we aren't authenticated
            # But our middleware allows connection to proceed to consumer, which then closes it.
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received message: {message}")
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed by server (Expected for unauthenticated user).")
            except asyncio.TimeoutError:
                print("Timeout waiting for message. Connection remained open (Unexpected for unauthenticated user?)")
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"Connection rejected with status code: {e.status_code} (Expected if handshake fails)")
    except Exception as e:
        print(f"An error occurred: {type(e).__name__}: {e}")

if __name__ == "__main__":
    print("Pre-requisite: Ensure 'pip install websockets' is run.")
    try:
        asyncio.run(test_websocket_connection())
    except ImportError:
        print("Please install websockets library: pip install websockets")
