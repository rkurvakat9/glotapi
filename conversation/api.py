import asyncio
import base64
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from .providers import FakeProvider, OpenAIProvider
from .service import converse

app = FastAPI()
provider = OpenAIProvider() if os.getenv("PROVIDER", "fake") == "openai" else FakeProvider()


async def receive_audio(ws, participants):
    """Parse a client message into a validated audio pair, or None on end."""
    event = await ws.receive_json()
    if event.get("type") == "end":
        return None

    speaker = event.get("speaker")
    if event.get("type") != "audio" or speaker not in participants:
        raise ValueError("expected audio with a known speaker, or end")

    audio = event.get("data")
    if not isinstance(audio, str) or len(audio) > 64000:
        raise ValueError("audio must be base64, at most 64000 characters")
    pcm = base64.b64decode(audio, validate=True)
    if not pcm or len(pcm) % 2:
        raise ValueError("expected nonempty PCM16 samples")

    return speaker, audio


@app.websocket("/v1/conversations")
async def conversation(ws: WebSocket):
    await ws.accept()
    try:
        # Demo limits: no abandoned connection or slow client may live forever.
        async with asyncio.timeout(300):
            start = await ws.receive_json()
            if start.get("type") != "start" or not isinstance(start.get("participants"), dict):
                raise ValueError("first message must start a conversation")
            participants = start["participants"]

            async def receive():
                return await receive_audio(ws, participants)

            await converse(participants, receive, ws.send_json, provider)
        await ws.close()
    except WebSocketDisconnect:
        pass
    except Exception:
        # Keep raw provider errors and credentials out of the public contract.
        await ws.close(code=1011, reason="conversation failed; start a new conversation")
