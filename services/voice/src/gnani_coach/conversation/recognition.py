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
import math
import time
from typing import Protocol, runtime_checkable

from gnani_coach.conversation.config import (
    ENDPOINTING_GATE_DBFS,
    MAX_CALL_SUBMISSIONS,
)
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

#: How much audio before the first speech frame is kept as pre-roll. A
#: short pre-roll preserves the attack of the first word without submitting
#: the leading silence of a call (which used to be replayed on every turn).
PRE_ROLL_MS = 96
PRE_ROLL_BYTES = 3 * 1024  # three 32 ms frames at 16 kHz mono s16le

#: The live pump (Phase 16, deliverable B6). When a recogniser can accept
#: frames while the learner speaks, they are forwarded at real-time
#: cadence instead of being replayed at the end of the turn. Set this to
#: ``False`` to revert to the clip path in one line.
LIVE_PUMP_ENABLED = True

#: One frame's cadence at 16 kHz mono s16le.
FRAME_SECONDS = 1024 / (16000 * 2)


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
        #: The last few frames before the first speech frame, kept so the
        #: attack of the first word is not clipped.
        self._pre_roll = bytearray()
        #: False until the clip being accumulated has seen a speech frame.
        #: A clip with no speech is never submitted.
        self._speech_started = False
        #: The live pump's state. ``None`` means "not tried yet", ``True``
        #: means frames are being forwarded as they arrive, ``False``
        #: means the provider cannot (or stopped) and the clip path is
        #: used for the rest of the call.
        self._live_active: bool | None = None
        self._live_pending_bytes = 0
        self._last_live_send_at = 0.0
        #: Stage timings of the last submission. Numbers only; the runtime
        #: logs them, never the audio.
        self.last_connect_ms = 0.0
        self.last_collect_ms = 0.0
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

        Leading and idle silence is kept only as a short pre-roll: a clip
        starts at the first speech frame, so a call no longer replays the
        silence from its own start on every turn. A clip that never sees a
        speech frame is never submitted at all.

        The buffer is bounded: when it reaches its ceiling the audio is
        submitted, so a burst of frames cannot grow the process's memory.
        """
        if self._closed:
            return
        if self.submissions >= self._max_submissions:
            # The submission ceiling is reached: the frame is dropped
            # rather than buffered, because it could never be submitted.
            return
        prefix = b""
        if not self._speech_started:
            if not _is_speech_frame(frame):
                self._pre_roll.extend(frame)
                if len(self._pre_roll) > PRE_ROLL_BYTES:
                    del self._pre_roll[: len(self._pre_roll) - PRE_ROLL_BYTES]
                return
            self._speech_started = True
            prefix = bytes(self._pre_roll)
            self._pre_roll = bytearray()

        if LIVE_PUMP_ENABLED and self._live_active is not False:
            if await self._push_live(prefix, frame):
                return

        self._pending.extend(prefix)
        if (
            self._pending
            and len(self._pending) + len(frame) > MAX_PENDING_AUDIO_BYTES
        ):
            await self.collect(grace_ms=0)
        self._pending.extend(frame)

    async def _push_live(self, prefix: bytes, frame: bytes) -> bool:
        """Forward frames to a live recogniser; False means "use the clip path"."""
        session = self._ensure_session()
        if not getattr(session, "live_capable", False):
            self._live_active = False
            return False
        try:
            if not self._live_active:
                await session.start_live()
                self._live_active = True
            for chunk in (prefix, frame):
                if not chunk:
                    continue
                now = time.monotonic()
                wait = self._last_live_send_at + FRAME_SECONDS - now
                if self._last_live_send_at and wait > 0:
                    await asyncio.sleep(wait)
                await session.send_live_frame(chunk)
                self._last_live_send_at = time.monotonic()
                self._live_pending_bytes += len(chunk)
            return True
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - fall back to the clip path
            self._live_active = False
            return False

    @property
    def has_closed_segment(self) -> bool:
        """True when a live recogniser has a segment ready to collect.

        Only the live path can answer before a submission: the clip path
        learns its segments only when the clip is submitted. A False here
        therefore keeps the longer hold, which is the safe choice.
        """
        if not self._live_active:
            return False
        session = self._session
        if session is None:
            return False
        return bool(getattr(session, "has_pending_live_segments", False))

    @property
    def pending_text(self) -> str:
        """The text of closed live segments not yet collected.

        It is a *peek*, not a collect: the segments are still returned by
        the turn's own ``collect``. Phase 19 uses it to start the reasoning
        call early without sending the transcript twice.
        """
        if not self._live_active or self._session is None:
            return ""
        segments = getattr(self._session, "pending_live_segments", ())
        return " ".join(
            getattr(segment, "text", "") or "" for segment in segments
        ).strip()

    @property
    def pending_audio_ms(self) -> int:
        """The audio waiting to be submitted, in milliseconds."""
        buffered = (
            self._live_pending_bytes
            if self._live_active
            else len(self._pending)
        )
        return buffered * 1000 // (16000 * 2)

    def _reset_clip(self) -> None:
        self._pending = bytearray()
        self._pre_roll = bytearray()
        self._speech_started = False

    async def collect(self, *, grace_ms: int) -> tuple[TranscriptSegment, ...]:
        """Return the segments recognised for the audio pushed so far.

        A clip that carries no speech frame is discarded without calling
        the provider: silence is not a submission.
        """
        if self._closed:
            return ()
        if self._live_active:
            # The frames are already on the provider's wire; there is no
            # clip to submit. Only the segments closed since the last
            # collect are returned.
            self._reset_clip()
            self._live_pending_bytes = 0
            session = self._ensure_session()
            started = time.monotonic()
            try:
                segments = await session.collect_live(grace_ms=grace_ms)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - fall back to the clip path
                self._live_active = False
                return ()
            self.last_collect_ms = (time.monotonic() - started) * 1000.0
            return tuple(segments)
        if self.submissions >= self._max_submissions:
            # The per-call submission ceiling is reached. The stream stops
            # submitting: the call survives, the recogniser is not called
            # again, and the reason is reported to the caller.
            raise BudgetExceededError(
                "the call reached its speech-to-text submission ceiling "
                f"({self._max_submissions})"
            )
        if not self._speech_started or not self._pending:
            # Nothing but silence: it is discarded, never submitted.
            self._reset_clip()
            return ()
        clip = bytes(self._pending)
        # New frames that arrive while the clip is in flight belong to the
        # next clip, so they are not lost and do not grow this one.
        self._reset_clip()
        self.submissions += 1
        started = time.monotonic()
        try:
            result = await self._submit(clip)
        except CancelledError:
            # The provider closed its session at the end of the previous
            # submission. Reconnect with the same VAD object and try once
            # more; a second failure is a real failure.
            self.reconnects += 1
            await self._close_session()
            result = await self._submit(clip)
        self.last_collect_ms = (time.monotonic() - started) * 1000.0
        return tuple(result.segments)

    async def _submit(self, clip: bytes):
        session = self._ensure_session()
        result = await session.stream_pcm(
            clip, trailing_silence_ms=TRAILING_SILENCE_MS
        )
        self.last_connect_ms = float(
            getattr(session, "last_connect_ms", 0.0) or 0.0
        )
        return result

    async def reopen(self, *, language_code: str | None = None) -> None:
        """Open a new session, carrying the same VAD settings object."""
        await self._close_session()
        self._live_active = None
        self._live_pending_bytes = 0
        self._last_live_send_at = 0.0
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
        self._reset_clip()
        self._live_active = False
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


def _is_speech_frame(frame: bytes, gate_dbfs: float = ENDPOINTING_GATE_DBFS) -> bool:
    """The same cheap energy gate the endpointing uses.

    It only decides whether a clip contains speech at all, so leading
    silence is not submitted; it is not a measurement.
    """
    if not frame:
        return False
    count = len(frame) // 2
    if count == 0:
        return False
    total = 0
    for index in range(0, len(frame) - 1, 2):
        sample = int.from_bytes(frame[index : index + 2], "little", signed=True)
        total += sample * sample
    rms = math.sqrt(total / count)
    if rms <= 0:
        return False
    return 20.0 * math.log10(rms / 32768.0) >= gate_dbfs


async def drain_stream(stream: RecognitionStream, *, grace_ms: int = 0) -> tuple[TranscriptSegment, ...]:
    """Collect whatever the stream has, never raising."""
    try:
        return await stream.collect(grace_ms=grace_ms)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the caller reports the failure
        return ()
