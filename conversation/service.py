"""Route a two-person conversation without knowing the API or provider details."""
import asyncio

from .provider_contract import Provider


def validate_participants(participants):
    if len(participants) != 2:
        raise ValueError("provide two distinct participant IDs with language codes")

    for participant, language in participants.items():
        if not isinstance(participant, str) or not participant:
            raise ValueError("participant IDs must be nonempty strings")
        if not isinstance(language, str) or not language:
            raise ValueError("language codes must be nonempty strings")


async def forward_audio_from_client(receive, streams):
    """Receive validated (speaker, audio) pairs; None means input has ended."""
    while True:
        chunk = await receive()
        if chunk is None:
            return
        speaker, audio = chunk
        await streams[speaker].send(audio)


async def forward_translated_output(stream, speaker, listener, publish):
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
                forward_translated_output(firstToSecondStream, firstParticipant, secondParticipant, publish)
            )
            second_output = tasks.create_task(
                forward_translated_output(secondToFirstStream, secondParticipant, firstParticipant, publish)
            )
            await publish({"type": "ready"})
            await forward_audio_from_client(receive, streams)

            # Finish input, then wait for the last translated words before closing.
            async with asyncio.timeout(15):
                await firstToSecondStream.finish()
                await secondToFirstStream.finish()
                await asyncio.gather(first_output, second_output)

            await publish({"type": "ended"})
