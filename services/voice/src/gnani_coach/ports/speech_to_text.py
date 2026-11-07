"""The speech-to-text port.

What the application needs from a recogniser, and nothing more:

* open a session for one language at one sample rate;
* submit the learner's own PCM and get back recognised segments;
* keep the learner-audio sample clock, because it is the only clock that
  may anchor an evidence span;
* stop consuming without pretending the provider was cancelled.

The Phase 02 adapter (``gnani_coach.providers.stt``) satisfies this port
through the wrapper in :mod:`gnani_coach.ports.provider_adapters`; the
provider package itself is not modified.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from gnani_coach.ports.types import ConnectionId
from gnani_coach.providers.stt import VadSettings


@dataclass(frozen=True)
class SttOpenRequest:
    """How to open a recognition session.

    ``vad`` is the VAD settings object for the whole connection: the
    provider's VAD headers are fixed for the life of a connection, so the
    same object is carried across a reconnect.
    """

    language_code: str
    sample_rate: int = 16000
    vad: VadSettings = VadSettings()
    output_format: str = "verbatim"
    connection_id: ConnectionId | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    """One recognised VAD segment.

    A segment is **not** a turn: one sentence can be split into several
    segments when the recogniser's VAD closes on a pause. ``text`` is
    transient and is never written to durable metrics, logs or caches.
    """

    segment_id: str | None
    segment_index: int | None
    text: str
    latency_ms: int | None
    server_timestamp: str | None
    learner_clock_samples: int
    status: str = "observed"


@dataclass(frozen=True)
class SttRunResult:
    """The outcome of one submitted clip.

    The three durations are deliberately separate: ``genuine_ms`` is the
    elapsed learner audio, ``padding_ms`` is the deliberate end padding
    (never learner speech) and ``submitted_ms`` is everything written to
    the socket.
    """

    segments: tuple[TranscriptSegment, ...]
    genuine_ms: int
    submitted_ms: int
    padding_ms: int
    end_padding_ms: int = 0
    unrecognized_frame_count: int = 0

    @property
    def text(self) -> str:
        """The recognised text of the clip, in observed order."""
        return " ".join(segment.text for segment in self.segments if segment.text).strip()


@runtime_checkable
class SpeechToTextSession(Protocol):
    """One open recognition session."""

    async def stream_pcm(
        self, raw_pcm: bytes, *, trailing_silence_ms: int = 800
    ) -> SttRunResult:
        """Submit raw mono s16le PCM and collect the segments it produces."""
        ...

    def iter_transcripts(self) -> AsyncIterator[TranscriptSegment]:
        """Yield segments as they arrive, for a live microphone path."""
        ...

    async def aclose(self, *, reason: str = "done") -> None:
        """Close the session. Safe to call from a cancellation path."""
        ...

    async def fence(self) -> None:
        """Stop consuming.

        This is *stopping consumption*, not cancelling provider
        computation: nothing in the reviewed provider documentation cancels
        a synthesis or an in-flight recognition.
        """
        ...


@runtime_checkable
class SpeechToTextPort(Protocol):
    """The application-facing speech-to-text boundary."""

    def open_session(self, request: SttOpenRequest) -> SpeechToTextSession:
        """Open a recognition session for one language."""
        ...
