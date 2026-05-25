#!/usr/bin/env python3
"""
Local bridge: connects to the cloud server and routes messages through claude -p.
Run this on your local machine after deploying the server.
"""
import asyncio
import json
import os
import subprocess
import sys

import websockets
from websockets.exceptions import ConnectionClosed

SERVER_URL = os.environ.get("SERVER_URL", "")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "")

# Per-client session IDs and auth state
sessions: dict[str, str] = {}
authenticated: set[str] = {}


def run_claude(message: str, session_id: str | None) -> tuple[str, str | None]:
    cmd = ["claude", "-p", message, "--output-format", "json"]
    if session_id:
        cmd.extend(["--resume", session_id])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "Request timed out after 120 seconds.", session_id
    except FileNotFoundError:
        return "Error: 'claude' command not found. Make sure Claude Code is installed.", session_id

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        return f"Claude error: {err}", session_id

    try:
        data = json.loads(result.stdout)
        if data.get("is_error"):
            return f"Claude error: {data.get('result', 'Unknown error')}", session_id
        return data.get("result", ""), data.get("session_id", session_id)
    except json.JSONDecodeError:
        return result.stdout.strip(), session_id


async def handle_message(ws, raw: str):
    msg = json.loads(raw)
    client_id = msg.get("client_id", "default")

    # Auth: first message from each client is the password
    if client_id not in authenticated:
        if msg.get("password") == USER_PASSWORD:
            authenticated.add(client_id)
            await ws.send(json.dumps({"client_id": client_id, "type": "connected"}))
        else:
            await ws.send(json.dumps({"client_id": client_id, "error": "Invalid password"}))
        return

    text = msg.get("text", "").strip()
    if not text:
        return

    print(f"[{client_id[:8]}] User: {text[:80]}{'...' if len(text) > 80 else ''}")

    session_id = sessions.get(client_id)
    response_text, new_session_id = run_claude(text, session_id)
    sessions[client_id] = new_session_id

    print(f"[{client_id[:8]}] Claude: {response_text[:80]}{'...' if len(response_text) > 80 else ''}")

    await ws.send(json.dumps({
        "client_id": client_id,
        "text": response_text,
        "role": "assistant",
        "type": "message",
    }))


async def run():
    if not SERVER_URL:
        print("ERROR: SERVER_URL not set. Example:")
        print("  export SERVER_URL=wss://your-app.up.railway.app/bridge")
        sys.exit(1)
    if not USER_PASSWORD:
        print("ERROR: USER_PASSWORD not set. Example:")
        print("  export USER_PASSWORD=yourpassword")
        sys.exit(1)

    print(f"Connecting to {SERVER_URL} ...")

    while True:
        try:
            async with websockets.connect(SERVER_URL, ping_interval=30, ping_timeout=10) as ws:
                print("Connected. Waiting for messages...")

                while True:
                    try:
                        raw = await ws.recv()
                        asyncio.create_task(handle_message(ws, raw))
                    except ConnectionClosed:
                        print("Connection closed, reconnecting...")
                        break

        except Exception as e:
            print(f"Connection error: {e}")

        print("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())
