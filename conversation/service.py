"""Route a two-person conversation without knowing the API or provider details."""
import asyncio
import base64

from .ports import Provider


def validate_participants(participants):
    if len(participants) != 2:
        raise ValueError("provide two distinct participant IDs with language codes")

    for participant, language in participants.items():
        if not isinstance(participant, str) or not participant:
            raise ValueError("participant IDs must be nonempty strings")
        if not isinstance(language, str) or not language:
            raise ValueError("language codes must be nonempty strings")


async def forward_audio(receive, streams):
    """Send each speaker's audio to their translation stream until input ends."""
    while True:
        event = await receive()
        if event.get("type") == "end":
            return

        speaker = event.get("speaker")
        if event.get("type") != "audio" or speaker not in streams:
            raise ValueError("expected audio with a known speaker, or end")

        audio = event.get("data")
        if not isinstance(audio, str) or len(audio) > 64000:
            raise ValueError("audio must be base64, at most 64000 characters")
        pcm = base64.b64decode(audio, validate=True)
        if not pcm or len(pcm) % 2:
            raise ValueError("expected nonempty PCM16 samples")

        await streams[speaker].send(audio)


async def forward_output(stream, speaker, listener, publish):
    """Return translations to the listener and source transcripts to the speaker."""
    async for delta in stream.events():
        recipient = listener
        if delta.kind == "source.delta":
            recipient = speaker

        await publish({
            "type": delta.kind,
            "speaker": speaker,
            "recipient": recipient,
            "data": delta.data,
        })


async def converse(participants: dict[str, str], receive, emit, provider: Provider):
    validate_participants(participants)
    firstParticipant, secondParticipant = participants

    # Each speaker gets a stream targeting the other person's language.
    # Context managers close both streams on success, failure or disconnect.
    async with (
        provider.open(participants[secondParticipant]) as firstToSecondStream,
        provider.open(participants[firstParticipant]) as secondToFirstStream,
    ):
        streams = {firstParticipant: firstToSecondStream, secondParticipant: secondToFirstStream}
        output_lock = asyncio.Lock()

        async def publish(event):
            # Only one output task may write to the client at a time.
            async with output_lock:
                await emit(event)

        # Output runs while input arrives. A failure cancels the other tasks.
        async with asyncio.TaskGroup() as tasks:
            first_output = tasks.create_task(
                forward_output(firstToSecondStream, firstParticipant, secondParticipant, publish)
            )
            second_output = tasks.create_task(
                forward_output(secondToFirstStream, secondParticipant, firstParticipant, publish)
            )
            await publish({"type": "ready"})
            await forward_audio(receive, streams)

            # Finish input, then wait for the last translated words before closing.
            async with asyncio.timeout(15):
                await firstToSecondStream.finish()
                await secondToFirstStream.finish()
                await asyncio.gather(first_output, second_output)

            await publish({"type": "ended"})
