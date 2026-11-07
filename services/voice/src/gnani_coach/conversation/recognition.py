"""The recognition stream: the runtime's view of a recogniser.

The frozen speech-to-text port exposes one submission per session
(:meth:`SpeechToTextSession.stream_pcm` submits a clip and returns the
segments it produced). The runtime therefore drives the recogniser in
two steps:

* :meth:`RecognitionStream.push_frame` moves the learner's audio into the
  recogniser;
* :meth:`RecognitionStream.collect` returns the segments recognised for
  the audio pushed so far.

A live recogniser (one that closes segments as the learner speaks) and a
clip recogniser (one that answers when the clip is submitted) both
satisfy that contract, and the turn controller above it does not care
which one it has.

**The seam gap.** The Phase 02 provider client closes its session at the
end of a submission, so a *long-lived* session that carries a whole
multi-turn call is not reachable through the frozen port. The stream
therefore treats a submission as a reconnectable step: when the provider
closes the session, the stream opens a **new** session with the **same
VAD settings object** — which is exactly the documented reconnect rule —
and the round boundary is where a language change is applied. The
reconnects are counted, never hidden. See ``prompts/parallel-G1/COMM.md``
for the ``HELP:`` item about the missing live-send capability.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from gnani_coach.conversation.config import MAX_CALL_SUBMISSIONS
from gnani_coach.ports.speech_to_text import (
    SpeechToTextPort,
    SpeechToTextSession,
    SttOpenRequest,
    TranscriptSegment,
)
from gnani_coach.providers.errors import BudgetExceededError, CancelledError

#: The silence appended after a clip so the provider's VAD closes its last
#: segment. It is padding, never learner speech.
TRAILING_SILENCE_MS = 800

#: The largest buffer of learner audio the stream holds before it is
#: submitted. A burst of frames must not grow the process's memory: the
#: audio is submitted as it goes.
MAX_PENDING_AUDIO_BYTES = 4 * 1024 * 1024


@runtime_checkable
class RecognitionStream(Protocol):
    """What the turn controller needs from a recogniser."""

    async def push_frame(self, frame: bytes) -> None:
        """Move one frame of learner audio into the recogniser."""
        ...

    async def collect(self, *, grace_ms: int) -> tuple[TranscriptSegment, ...]:
        """Return the segments recognised for the audio pushed so far.

        ``grace_ms`` bounds how long the call waits for a segment to
        arrive. The result may be empty: no segment was closed yet.
        """
        ...

    async def reopen(self, *, language_code: str | None = None) -> None:
        """Open a new session, carrying the same VAD settings object.

        Used at a round boundary when the practice language changes: the
        provider's VAD headers are fixed for the life of a connection, so
        a change needs a reconnect with the same VAD object.
        """
        ...

    async def close(self, *, reason: str = "done") -> None:
        """Close the stream. Safe to call from a cancellation path."""
        ...


class PortRecognitionStream:
    """A recognition stream backed by the frozen speech-to-text port."""

    def __init__(
        self,
        *,
        port: SpeechToTextPort,
        request: SttOpenRequest,
        max_submissions: int = MAX_CALL_SUBMISSIONS,
    ) -> None:
        self._port = port
        self._request = request
        self._session: SpeechToTextSession | None = None
        self._pending = bytearray()
        #: How many times the provider closed a session and the stream had
        #: to reconnect. Counted, never hidden.
        self.reconnects = 0
        #: How many submissions were made.
        self.submissions = 0
        #: How many submissions this call may still make. The ceiling is a
        #: bound, not a target: it is never raised.
        self._max_submissions = max(0, int(max_submissions))
        self._closed = False

    # -- lifecycle -----------------------------------------------------
    def _ensure_session(self) -> SpeechToTextSession:
        if self._session is None:
            self._session = self._port.open_session(self._request)
        return self._session

    async def push_frame(self, frame: bytes) -> None:
        """Buffer one frame of learner audio.

        The buffer is bounded: when it reaches its ceiling the audio is
        submitted, so a burst of frames cannot grow the process's memory.
        """
        if self._closed:
            return
        if self.submissions >= self._max_submissions:
            # The submission ceiling is reached: the frame is dropped
            # rather than buffered, because it could never be submitted.
            return
        if (
            self._pending
            and len(self._pending) + len(frame) > MAX_PENDING_AUDIO_BYTES
        ):
            await self.collect(grace_ms=0)
        self._pending.extend(frame)

    async def collect(self, *, grace_ms: int) -> tuple[TranscriptSegment, ...]:
        """Return the segments recognised for the audio pushed so far."""
        if self._closed:
            return ()
        if self.submissions >= self._max_submissions:
            # The per-call submission ceiling is reached. The stream stops
            # submitting: the call survives, the recogniser is not called
            # again, and the reason is reported to the caller.
            raise BudgetExceededError(
                "the call reached its speech-to-text submission ceiling "
                f"({self._max_submissions})"
            )
        if not self._pending:
            return ()
        clip = bytes(self._pending)
        self._pending = bytearray()
        self.submissions += 1
        try:
            result = await self._submit(clip)
        except CancelledError:
            # The provider closed its session at the end of the previous
            # submission. Reconnect with the same VAD object and try once
            # more; a second failure is a real failure.
            self.reconnects += 1
            await self._close_session()
            result = await self._submit(clip)
        return tuple(result.segments)

    async def _submit(self, clip: bytes):
        session = self._ensure_session()
        return await session.stream_pcm(
            clip, trailing_silence_ms=TRAILING_SILENCE_MS
        )

    async def reopen(self, *, language_code: str | None = None) -> None:
        """Open a new session, carrying the same VAD settings object."""
        await self._close_session()
        if language_code is not None:
            self._request = SttOpenRequest(
                language_code=language_code,
                sample_rate=self._request.sample_rate,
                vad=self._request.vad,
                output_format=self._request.output_format,
                connection_id=self._request.connection_id,
            )
        self.reconnects += 1

    async def _close_session(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            try:
                await session.aclose(reason="reconnect")
            except Exception:  # noqa: BLE001 - closing must not mask
                pass

    async def close(self, *, reason: str = "done") -> None:
        """Close the stream and the session it owns."""
        if self._closed:
            return
        self._closed = True
        self._pending = bytearray()
        await self._close_session()


class BufferedRecognitionStream:
    """A stream that answers from a fixed list of segments.

    This is the offline shape: the segments are already known, so a
    submission returns the next batch of them. It is used by the tests
    and by the deterministic paths that need a recogniser without a
    provider.
    """

    def __init__(self, batches: list[list[TranscriptSegment]]) -> None:
        self._batches = list(batches)
        self._index = 0
        self.pushed = bytearray()

    async def push_frame(self, frame: bytes) -> None:
        self.pushed.extend(frame)

    async def collect(self, *, grace_ms: int) -> tuple[TranscriptSegment, ...]:
        del grace_ms
        if self._index >= len(self._batches):
            return ()
        batch = self._batches[self._index]
        self._index += 1
        return tuple(batch)

    async def reopen(self, *, language_code: str | None = None) -> None:
        del language_code

    async def close(self, *, reason: str = "done") -> None:
        del reason


async def drain_stream(stream: RecognitionStream, *, grace_ms: int = 0) -> tuple[TranscriptSegment, ...]:
    """Collect whatever the stream has, never raising."""
    try:
        return await stream.collect(grace_ms=grace_ms)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the caller reports the failure
        return ()
