"""Conversation policy: direction, attribution, and stream lifetime. No vendor imports."""
import asyncio
import base64
from contextlib import AsyncExitStack
from .ports import Provider


async def converse(participants: dict[str, str], receive, emit, provider: Provider):
    if len(participants) != 2 or not all(
        isinstance(k, str) and k and isinstance(v, str) and v for k, v in participants.items()
    ):
        raise ValueError("provide two distinct participant IDs with language codes")
    a, b = participants
    routes = {a: b, b: a}
    async with AsyncExitStack() as stack:
        streams = {speaker: await stack.enter_async_context(provider.open(participants[listener]))
                   for speaker, listener in routes.items()}
        # One writer protects transport ordering across independent output streams.
        lock = asyncio.Lock()

        async def publish(event):
            async with lock:
                await emit(event)

        async def output(speaker, stream):
            async for delta in stream.events():
                await publish({"type": delta.kind, "speaker": speaker,
                               "recipient": speaker if delta.kind == "source.delta" else routes[speaker],
                               "data": delta.data})

        async with asyncio.TaskGroup() as tasks:
            readers = [tasks.create_task(output(s, stream)) for s, stream in streams.items()]
            await publish({"type": "ready"})
            while True:
                event = await receive()
                if event.get("type") == "end":
                    break
                if event.get("type") != "audio" or event.get("speaker") not in streams:
                    raise ValueError("expected audio with a known speaker, or end")
                audio = event.get("data")
                if not isinstance(audio, str) or len(audio) > 64000:
                    raise ValueError("audio must be base64, at most 64000 characters")
                pcm = base64.b64decode(audio, validate=True)
                if not pcm or len(pcm) % 2:
                    raise ValueError("expected nonempty PCM16 samples")
                await streams[event["speaker"]].send(audio)
            # Finish input, then drain output: closing immediately loses the last words.
            async with asyncio.timeout(15):
                for stream in streams.values():
                    await stream.finish()
                await asyncio.gather(*readers)
            await publish({"type": "ended"})
