"""A deterministic two-way conversation against the running server."""
import asyncio
import json
from websockets.asyncio.client import connect


async def main():
    async with connect('ws://127.0.0.1:8000/v1/conversations') as ws:
        await ws.send(json.dumps({'type': 'start', 'participants': {'alice': 'en', 'bob': 'es'}}))
        print(await ws.recv())
        for speaker in ['alice', 'bob']:
            await ws.send(json.dumps({'type': 'audio', 'speaker': speaker, 'data': 'AAA='}))
        await ws.send(json.dumps({'type': 'end'}))
        async for raw in ws:
            print(raw)
            if json.loads(raw)['type'] == 'ended':
                return


asyncio.run(main())
