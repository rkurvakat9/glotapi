import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from .providers import FakeProvider, OpenAIProvider
from .service import converse

app = FastAPI()
provider = OpenAIProvider() if os.getenv("PROVIDER", "fake") == "openai" else FakeProvider()


@app.websocket("/v1/conversations")
async def conversation(ws: WebSocket):
    await ws.accept()
    try:
        # Demo limits: no abandoned connection or slow client may live forever.
        async with asyncio.timeout(300):
            start = await ws.receive_json()
            if start.get("type") != "start" or not isinstance(start.get("participants"), dict):
                raise ValueError("first message must start a conversation")
            await converse(start["participants"], ws.receive_json, ws.send_json, provider)
        await ws.close()
    except WebSocketDisconnect:
        pass
    except Exception:
        # Keep raw provider errors and credentials out of the public contract.
        await ws.close(code=1011, reason="conversation failed; start a new conversation")
