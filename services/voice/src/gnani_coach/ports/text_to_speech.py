"""The text-to-speech port.

What the application needs from a synthesiser:

* open a session for one text, voice and language;
* receive audio chunks in order;
* stop playback without claiming the provider cancelled anything.

Two facts from the reviewed provider documentation shape this port: one
synthesis request at a time per connection, and **no cancel control
message**. The port therefore has :meth:`TextToSpeechSession.cancel_consumption`,
which fences the consumer. It is not a provider cancellation, and the user
interface must not describe it as one.

The Phase 02 adapter (``gnani_coach.providers.tts``) satisfies this port
through the wrapper in :mod:`gnani_coach.ports.provider_adapters`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TtsOpenRequest:
    """How to open a synthesis session.

    The voice catalog is model-specific and a mismatched pair is a hard
    error from the provider, so ``model`` and ``voice`` travel together.
    """

    text: str
    voice: str
    model: str = "timbre-v2.5"
    language: str = "en-IN"
    speed: float = 1.0
    sample_rate: int = 16000


@dataclass(frozen=True)
class SpeechChunk:
    """One chunk of synthesised audio.

    ``chunk_index`` is kept so ordering is verified rather than assumed:
    observed chunk sizes are not uniform, and concatenation must be
    append-only and index-driven.
    """

    data: bytes
    chunk_index: int | None = None
    is_final: bool = False


@runtime_checkable
class TextToSpeechSession(Protocol):
    """One open synthesis session."""

    async def synthesize(
        self,
        *,
        on_chunk: Callable[[SpeechChunk], Awaitable[None]] | None = None,
    ) -> tuple[SpeechChunk, ...]:
        """Run one synthesis and deliver the chunks in order."""
        ...

    async def cancel_consumption(self) -> None:
        """Stop delivering chunks to the caller.

        This fences the consumer. It does **not** cancel the provider's
        computation and it makes no claim about billing.
        """
        ...

    async def aclose(self, *, reason: str = "done") -> None:
        """Close the session. Safe to call from a cancellation path."""
        ...


@runtime_checkable
class TextToSpeechPort(Protocol):
    """The application-facing text-to-speech boundary."""

    def open_session(self, request: TtsOpenRequest) -> TextToSpeechSession:
        """Open a synthesis session."""
        ...
