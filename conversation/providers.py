import asyncio
import json
import os
from contextlib import asynccontextmanager

from websockets.asyncio.client import connect
from .provider_contract import Delta


class OpenAIStream:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, audio):
        await self.ws.send(json.dumps({"type": "session.input_audio_buffer.append", "audio": audio}))

    async def finish(self):
        await self.ws.send(json.dumps({"type": "session.close"}))

    async def events(self):
        mapping = {"session.output_audio.delta": "audio.delta",
                   "session.output_transcript.delta": "translation.delta",
                   "session.input_transcript.delta": "source.delta"}
        async for raw in self.ws:
            event = json.loads(raw)
            if event["type"] == "error":
                raise RuntimeError("translation provider failed")
            if event["type"] == "session.closed":
                return
            if event["type"] in mapping:
                yield Delta(mapping[event["type"]], event["delta"])
        raise RuntimeError("provider disconnected before final output")


class OpenAIProvider:
    @asynccontextmanager
    async def open(self, target):
        url = "wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate"
        headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
        async with connect(url, additional_headers=headers, max_queue=16) as ws:
            async with asyncio.timeout(10):
                if json.loads(await ws.recv())["type"] != "session.created":
                    raise RuntimeError("expected session creation")
                '''https://developers.openai.com/api/reference/resources/realtime/translation-client-events#session.update'''
                await ws.send(json.dumps({"type": "session.update",
                  "session": {
                    "audio": {
                      "input": {
                        "transcription": {
                          "model": "gpt-realtime-whisper"
                        }
                      },
                      "output": {"language": target}
                    }
                  }}))
                if json.loads(await ws.recv())["type"] != "session.updated":
                    raise RuntimeError("expected configuration acknowledgement")
            yield OpenAIStream(ws)


class FakeStream:
    """Deterministic plumbing demo. Does not recognize or translate speech."""
    def __init__(self, target):
        self.target, self.queue = target, asyncio.Queue(maxsize=16)

    async def send(self, audio):
        await self.queue.put(Delta("translation.delta", f"[demo output in {self.target}]"))

    async def finish(self):
        await self.queue.put(None)

    async def events(self):
        while (event := await self.queue.get()) is not None:
            yield event


class FakeProvider:
    @asynccontextmanager
    async def open(self, target):
        yield FakeStream(target)
