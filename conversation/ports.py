"""The application owns this contract; providers implement it."""
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Delta:
    kind: str  # audio.delta | translation.delta | source.delta
    data: str  # base64 PCM for audio; text otherwise


class Stream(Protocol):
    async def send(self, audio: str) -> None: ...
    async def finish(self) -> None: ...
    def events(self) -> AsyncIterator[Delta]: ...


class Provider(Protocol):
    def open(self, target: str) -> AbstractAsyncContextManager[Stream]: ...
