# Glot interview exercise

Start with [DESIGN.md](DESIGN.md). The implementation is intentionally small: a two-person conversation API, a provider contract, a real adapter and a deterministic fake.

## Run (Python 3.11+)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn conversation.api:app --host 127.0.0.1 --port 8000 --ws-max-size 65536 --ws-max-queue 16
```

In a second terminal, from this directory:

```bash
.venv/bin/python demo.py
```

Expected: `ready`, two attributed demo translations (their order may vary), then `ended`. The two-byte silence frames exercise routing only; the fake does not translate speech.

Run checks:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

For real speech, set `PROVIDER=openai` and `OPENAI_API_KEY` in the server environment before starting it. Keep the key server-side. Send actual base64 PCM16 little-endian, mono, 24 kHz audio in small chunks (e.g. 100 ms / 4800 bytes), including silence between phrases; consume output concurrently with sending. `demo.py` is a fake-provider routing demo, not a microphone or translation-quality demo. Languages must be supported by the chosen provider. Live OpenAI integration requires network access and credentials and has not been exercised here.

## A 1–2 day implementation plan

Budget roughly 12 focused hours; use the remaining time for interview rehearsal or a live audio check if credentials are available.

| Work | Time | Concrete output |
|---|---:|---|
| Read mission and API; choose one use case and assumptions | 1.5 h | Scope and product rationale |
| Define public events, direction and lifecycle | 2 h | API examples and architecture diagram |
| Explain trade-offs, omissions and three expansion paths | 2.5 h | Short design document |
| Write `ports.py` and `service.py` | 2 h | Translation stream port; two-way routing and cleanup |
| Write `providers.py` and `api.py` | 2 h | Fake + OpenAI adapters; thin WebSocket endpoint |
| Write demo, targeted tests and run instructions | 2 h | Reproducible walkthrough |

Stop when the boundaries and complete slice are demonstrated. Avoid adding repositories, service classes, queues or deployment infrastructure without a concrete requirement.

## Interview walkthrough (10–12 minutes)

1. Start with the product decision: a conversation has people and directions; the provider translates one stream toward one language.
2. Show the diagram and explain why v1 has two streams and one application socket.
3. Run the fake demo; point out both recipients and final drain. Be explicit that fake text is not translation.
4. Walk through `ports.py`, then the routing function. Show where vendor-specific event names are isolated in the real adapter.
5. Describe a provider swap: implement the same port and change composition in `api.py`. Media conversion stays in the adapter; unsupported capabilities must be rejected.
6. Choose one expansion and name the modules that change. Close with omissions and what must happen before a pilot.

Useful discussion: "I chose isolated speaker streams so attribution is deterministic. If a shared-phone experience is the immediate priority, I'd first validate speaker separation and language routing, because that changes the input assumption."

## Verification

Three automated checks cover two-way WebSocket routing and final output, cleanup on client failure, and the real adapter's configuration/input/output/finish wire mapping using a local fixture. They do not establish live provider compatibility, audio quality or production readiness.
