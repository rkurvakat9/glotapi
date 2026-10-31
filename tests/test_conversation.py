import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient
from conversation.api import app
from conversation.providers import FakeProvider, OpenAIProvider
from conversation.service import converse


class ConversationTests(unittest.TestCase):
    def test_two_way_api_and_final_output(self):
        with TestClient(app).websocket_connect('/v1/conversations') as ws:
            ws.send_json({'type': 'start', 'participants': {'alice': 'en', 'bob': 'es'}})
            self.assertEqual(ws.receive_json(), {'type': 'ready'})
            for speaker in ['alice', 'bob']:
                ws.send_json({'type': 'audio', 'speaker': speaker, 'data': 'AAA='})
            ws.send_json({'type': 'end'})
            events = [ws.receive_json() for _ in range(3)]
            self.assertEqual(events[-1], {'type': 'ended'})
            self.assertEqual({(e['speaker'], e['recipient'], e['data']) for e in events[:-1]}, {
                ('alice', 'bob', '[demo output in es]'),
                ('bob', 'alice', '[demo output in en]')})


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_cleans_up_both_provider_streams(self):
        closed = []

        class TrackingProvider(FakeProvider):
            @asynccontextmanager
            async def open(self, target):
                try:
                    async with super().open(target) as stream:
                        yield stream
                finally:
                    closed.append(target)

        async def disconnect():
            raise ConnectionError('client disconnected')

        async def emit(event):
            pass

        with self.assertRaises(ExceptionGroup):
            await converse({'a': 'en', 'b': 'es'}, disconnect, emit, TrackingProvider())
        self.assertCountEqual(closed, ['en', 'es'])

    async def test_openai_wire_contract_and_drain(self):
        # No credentials or remote API needed: exercise the real adapter mapping.
        incoming = iter([
            {'type': 'session.created'}, {'type': 'session.updated'},
            {'type': 'session.output_transcript.delta', 'delta': 'Hola'},
            {'type': 'session.output_audio.delta', 'delta': 'AAA='},
            {'type': 'session.closed'},
        ])
        sent = []

        class Socket:
            async def recv(self):
                return json.dumps(next(incoming))

            async def send(self, raw):
                sent.append(json.loads(raw))

            def __aiter__(self):
                return self

            async def __anext__(self):
                return await self.recv()

        @asynccontextmanager
        async def connect(*args, **kwargs):
            yield Socket()

        with patch('conversation.providers.connect', connect), patch.dict('os.environ', OPENAI_API_KEY='test'):
            async with OpenAIProvider().open('es') as stream:
                await stream.send('AAA=')
                await stream.finish()
                events = [event async for event in stream.events()]
        self.assertEqual([e.kind for e in events], ['translation.delta', 'audio.delta'])
        self.assertEqual(sent, [
            {'type': 'session.update', 'session': {'audio': {'output': {'language': 'es'}}}},
            {'type': 'session.input_audio_buffer.append', 'audio': 'AAA='},
            {'type': 'session.close'},
        ])


if __name__ == '__main__':
    unittest.main()
