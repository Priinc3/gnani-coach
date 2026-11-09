"""The shared names of the Phase 05 coaching-runtime tests.

**Phase 05 owns this file.** It is a plain module (not a ``conftest``)
because a test module that does ``from conftest import ...`` picks up
*whichever* ``conftest`` was imported first, and this repository has
several of them. A uniquely named module has no such ambiguity.

Everything here is a **fake**: no socket leaves the process, no provider
is called and no model is asked. The fakes implement the same ports the
real runtime uses, so the runtime under test is the **real** runtime and
the **real** router, over a fake recogniser, a fake synthesiser and a
fake model.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from gnani_coach.conversation.connections import registry
from gnani_coach.conversation.runtime import CallOptions, CallProviders
from gnani_coach.ports.analysis import (
    AnalysisObservation,
    AnalysisRequest,
    AnalysisResult,
)
from gnani_coach.ports.reasoning import ReasoningReply
from gnani_coach.ports.speech_to_text import (
    SttOpenRequest,
    SttRunResult,
    TranscriptSegment,
)
from gnani_coach.ports.text_to_speech import SpeechChunk, TtsOpenRequest

#: The test directory goes on ``sys.path`` so a test module can import
#: this module by its own name.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ---------------------------------------------------------------------------
# audio helpers
# ---------------------------------------------------------------------------

#: One frame of learner audio: 512 samples of s16le.
FRAME_BYTES = 1024


def loud_frame(value: int = 8000) -> bytes:
    """A frame that the energy gate reads as speech."""
    return struct.pack("<512h", *([value] * 512))


def silent_frame() -> bytes:
    """A frame of silence."""
    return struct.pack("<512h", *([0] * 512))


def is_loud(frame: bytes) -> bool:
    """Whether a frame carries speech, by its peak amplitude."""
    peak = 0
    for index in range(0, len(frame) - 1, 2):
        value = abs(int.from_bytes(frame[index : index + 2], "little", signed=True))
        if value > peak:
            peak = value
    return peak > 3000


# ---------------------------------------------------------------------------
# the recogniser
# ---------------------------------------------------------------------------


class FakeSttSession:
    """One recognition session over the speech-to-text port."""

    def __init__(self, port: "FakeSttPort", request: SttOpenRequest) -> None:
        self._port = port
        self.request = request
        self.closed = False
        self.fenced = False
        self.submissions = 0

    async def stream_pcm(
        self, raw_pcm: bytes, *, trailing_silence_ms: int = 800
    ) -> SttRunResult:
        if self._port.delay:
            # A slow recogniser: the runtime must keep reading frames and
            # sending the heartbeat while this runs.
            await asyncio.sleep(self._port.delay)
        self.submissions += 1
        self._port.submissions += 1
        segments = self._port.recognise(raw_pcm)
        samples = len(raw_pcm) // 2
        return SttRunResult(
            segments=tuple(segments),
            genuine_ms=int(samples * 1000 / 16000),
            submitted_ms=int(samples * 1000 / 16000),
            padding_ms=trailing_silence_ms,
        )

    async def aclose(self, *, reason: str = "done") -> None:
        del reason
        self.closed = True

    async def fence(self) -> None:
        self.fenced = True


class FakeSttPort:
    """A recogniser that closes a segment per run of speech."""

    def __init__(
        self,
        texts: list[str] | None = None,
        *,
        fail: bool = False,
        delay: float = 0.0,
    ) -> None:
        self._texts = list(texts or ["one two three four five"])
        self.fail = fail
        self.delay = delay
        self.submissions = 0
        self.max_clip_bytes = 0
        self.sessions: list[FakeSttSession] = []
        self.requests: list[SttOpenRequest] = []

    def open_session(self, request: SttOpenRequest) -> FakeSttSession:
        self.requests.append(request)
        session = FakeSttSession(self, request)
        self.sessions.append(session)
        return session

    def recognise(self, raw_pcm: bytes) -> list[TranscriptSegment]:
        """The segments of one submitted clip."""
        if self.fail:
            raise RuntimeError("the recogniser is unavailable")
        self.max_clip_bytes = max(self.max_clip_bytes, len(raw_pcm))
        frame_bytes = 1024
        segments: list[TranscriptSegment] = []
        running = False
        for start in range(0, len(raw_pcm), frame_bytes):
            frame = raw_pcm[start : start + frame_bytes]
            if len(frame) < frame_bytes:
                break
            if is_loud(frame):
                running = True
                continue
            if running:
                running = False
                text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]
                segments.append(
                    TranscriptSegment(
                        segment_id=f"seg-{len(segments)}",
                        segment_index=len(segments),
                        text=text,
                        latency_ms=12,
                        server_timestamp=None,
                        learner_clock_samples=0,
                    )
                )
        return segments


# ---------------------------------------------------------------------------
# the synthesiser
# ---------------------------------------------------------------------------


@dataclass
class FakeTtsSession:
    """One synthesis. It can be slow, and it can answer after a fence."""

    text: str
    chunks: list[bytes] = field(default_factory=list)
    slow: bool = False
    late_chunk: bool = False
    #: A provider that keeps sending after the consumer was fenced. The
    #: runtime must drop those chunks; they are never sent.
    ignore_cancel: bool = False
    cancelled: bool = False
    closed: bool = False

    async def synthesize(self, *, on_chunk: Any = None) -> tuple[SpeechChunk, ...]:
        for index, data in enumerate(self.chunks):
            if self.slow:
                await asyncio.sleep(0.05)
            if self.cancelled and not self.ignore_cancel:
                # A fenced session delivers nothing more.
                break
            if on_chunk is not None:
                await on_chunk(
                    SpeechChunk(
                        data=data,
                        chunk_index=index,
                        is_final=index == len(self.chunks) - 1,
                    )
                )
        if self.late_chunk and not self.cancelled and on_chunk is not None:
            # A late chunk of a cancelled turn must never reach the client.
            await on_chunk(SpeechChunk(data=b"\x00\x00" * 16, chunk_index=99))
        return tuple(
            SpeechChunk(data=data, chunk_index=index)
            for index, data in enumerate(self.chunks)
        )

    async def cancel_consumption(self) -> None:
        self.cancelled = True

    async def aclose(self, *, reason: str = "done") -> None:
        del reason
        self.closed = True


class FakeTtsPort:
    """A synthesiser that hands out scripted sessions."""

    def __init__(
        self,
        *,
        chunks: list[bytes] | None = None,
        slow: bool = False,
        late_chunk: bool = False,
        ignore_cancel: bool = False,
    ) -> None:
        self._chunks = chunks if chunks is not None else [b"\x01\x02" * 64]
        self._slow = slow
        self._late_chunk = late_chunk
        self._ignore_cancel = ignore_cancel
        self.sessions: list[FakeTtsSession] = []
        self.requests: list[TtsOpenRequest] = []

    def open_session(self, request: TtsOpenRequest) -> FakeTtsSession:
        self.requests.append(request)
        session = FakeTtsSession(
            text=request.text,
            chunks=list(self._chunks),
            slow=self._slow,
            late_chunk=self._late_chunk,
            ignore_cancel=self._ignore_cancel,
        )
        self.sessions.append(session)
        return session


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------


class FakeReasoning:
    """A model whose answers are scripted.

    ``delay`` makes the model slow (so an interrupt can land while it is
    thinking) and ``error`` makes it fail.
    """

    def __init__(
        self,
        replies: list[str] | None = None,
        *,
        delay: float = 0.0,
        error: BaseException | None = None,
    ) -> None:
        self.replies = list(replies or ["That sounds like a good point."])
        self.delay = delay
        self.error = error
        self.requests: list[Any] = []

    async def reply(self, request: Any) -> ReasoningReply:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return ReasoningReply(
            text=text, model="fake-model", stored=False, tools_enabled=False
        )


# ---------------------------------------------------------------------------
# identity, analysis and the stores
# ---------------------------------------------------------------------------


class FakeIdentity:
    """An identity that knows exactly one token."""

    def __init__(
        self,
        user_id: str | None = "usr_testuser",
        *,
        valid_token: str = "good-token",
        raises: bool = False,
    ) -> None:
        self.user_id = user_id
        self.valid_token = valid_token
        self.raises = raises
        self.seen: list[str | None] = []

    async def verify_token(self, token: str | None) -> str | None:
        self.seen.append(token)
        if self.raises:
            raise RuntimeError("the identity service is unavailable")
        if token is None or token != self.valid_token:
            return None
        return self.user_id

    async def current_user(self) -> str | None:
        return self.user_id


class FakeAnalysis:
    """An analysis that reports scripted observations."""

    def __init__(
        self,
        *,
        recognition_status: str = "measured",
        speech_active_ms: int = 900,
        observations: tuple[AnalysisObservation, ...] | None = None,
    ) -> None:
        self.recognition_status = recognition_status
        self.speech_active_ms = speech_active_ms
        self.observations = observations
        self.requests: list[AnalysisRequest] = []

    def _observations(self) -> tuple[AnalysisObservation, ...]:
        if self.observations is not None:
            return self.observations
        return (
            AnalysisObservation(
                metric_key="turn.duration_ms",
                status="available",
                value=1000,
                unit="milliseconds",
                method="learner_audio_sample_clock",
                evidence_span=(0, 1000),
            ),
            AnalysisObservation(
                metric_key="speech.rate_wpm",
                status="available",
                value=120.0,
                unit="words_per_minute",
                method="stt_words_over_learner_span",
                denominator="learner_span_ms",
                evidence_span=(0, 1000),
            ),
            AnalysisObservation(
                metric_key="speech.active_rate_wpm",
                status="available",
                value=200.0,
                unit="words_per_minute",
                method="stt_words_over_speech_active",
                denominator="speech_active_ms",
                evidence_span=(0, 1000),
            ),
            AnalysisObservation(
                metric_key="pause.count",
                status="available",
                value=1,
                unit="count",
                method="vad_speech_regions",
                evidence_span=(0, 1000),
            ),
            AnalysisObservation(
                metric_key="pause.longest_ms",
                status="available",
                value=400,
                unit="milliseconds",
                method="vad_speech_regions",
                evidence_span=(0, 1000),
            ),
            AnalysisObservation(
                metric_key="filler.count",
                status="insufficient_evidence",
                value=None,
                unit=None,
                unavailability_reason="filler_detection_unvalidated",
            ),
        )

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        self.requests.append(request)
        return AnalysisResult(
            recognition_status=self.recognition_status,  # type: ignore[arg-type]
            observations=self._observations(),
            audio_source=request.audio_source,
        )

    async def measure(self, request: AnalysisRequest) -> Any:
        from gnani_coach.analysis.service import TurnMeasurement

        result = await self.analyze(request)
        return TurnMeasurement(result=result, speech_active_ms=self.speech_active_ms)


class FakeSessionStore:
    """An in-memory metrics store."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.fail = False

    async def save_metrics(self, record: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("the store is unavailable")
        self.records.append(record)


class FakeRecordingStore:
    """An in-memory recording store."""

    def __init__(self) -> None:
        self.saved: list[tuple[str, str, bytes, int]] = []

    async def save_recording(
        self,
        user_id: str,
        session_id: str,
        audio: bytes,
        *,
        duration_ms: int,
        content_type: str = "audio/wav",
    ) -> Any:
        del content_type
        self.saved.append((user_id, session_id, audio, duration_ms))
        from gnani_coach.ports.recording_store import RecordingRef

        return RecordingRef(
            recording_id="rec_testrecord",
            session_id=session_id,
            created_at="2026-10-20T00:00:00Z",
            duration_ms=duration_ms,
            size_bytes=len(audio),
        )




def build_options(
    *,
    identity: FakeIdentity,
    analysis: FakeAnalysis,
    stt: FakeSttPort,
    tts: FakeTtsPort,
    reasoning: FakeReasoning,
    session_store: FakeSessionStore | None = None,
    recording_store: FakeRecordingStore | None = None,
    consent_checker: Any = None,
    consent_granted: bool = False,
    hold_ms: int = 1200,
    min_words: int = 3,
    call_cap_seconds: float = 600.0,
) -> CallOptions:
    """The options one call needs, with fakes everywhere."""
    providers = CallProviders(
        stt=stt,
        tts=tts,
        reasoning=reasoning,
        language_code="en-IN",
        stt_vad=None,
        tts_voice="Devika",
        tts_model="timbre-v2.5",
        tts_language="en-IN",
    )
    return CallOptions(
        identity=identity,
        analyzer=analysis,
        providers=providers,
        practice_language="English",
        coaching_language="English",
        consent_granted=consent_granted,
        consent_checker=consent_checker,
        session_store=session_store,
        recording_store=recording_store,
        connections=registry,
        hold_ms=hold_ms,
        min_words=min_words,
        call_cap_seconds=call_cap_seconds,
    )


# ---------------------------------------------------------------------------
# the harness: one call over a real in-process WebSocket
# ---------------------------------------------------------------------------


class Timeout(Exception):
    """The service did not answer in time."""


class Harness:
    """Drives one call over a real in-process WebSocket.

    Every read is bounded: a service that never answers fails the test
    instead of hanging the suite.
    """

    def __init__(self, socket: Any, client: Any) -> None:
        self.socket = socket
        self.client = client

    # -- sending -------------------------------------------------------
    def start(self, **kwargs: Any) -> None:
        self.socket.send_json(start_event(**kwargs))

    def send(self, event: dict[str, Any]) -> None:
        self.socket.send_json(event)

    def speech(self, count: int = 8) -> None:
        for _ in range(count):
            self.socket.send_bytes(loud_frame())

    def silence(self, count: int = 45) -> None:
        for _ in range(count):
            self.socket.send_bytes(silent_frame())

    def frames(self, count: int, *, loud: bool = True) -> None:
        for _ in range(count):
            self.socket.send_bytes(loud_frame() if loud else silent_frame())

    # -- receiving -----------------------------------------------------
    def _receive(self, timeout: float) -> dict[str, Any]:
        import anyio

        async def _wait() -> dict[str, Any] | None:
            with anyio.move_on_after(timeout):
                return await self.socket._send_rx.receive()
            return None

        message = self.socket.portal.call(_wait)
        if message is None:
            raise Timeout("the service did not answer in time")
        return dict(message)

    def next_event(self, timeout: float = 5.0) -> dict[str, Any]:
        """The next JSON event, or a binary marker."""
        message = self._receive(timeout)
        if message.get("type") == "websocket.close":
            self.socket._raise_on_close(message)
        if "bytes" in message:
            return {"type": "__binary__", "bytes": message["bytes"]}
        import json as _json

        return _json.loads(message["text"])

    def events_until(
        self,
        wanted: set[str],
        *,
        limit: int = 40,
        timeout: float = 5.0,
    ) -> list[dict[str, Any]]:
        """Read events until one of ``wanted`` arrives."""
        collected: list[dict[str, Any]] = []
        for _ in range(limit):
            event = self.next_event(timeout=timeout)
            collected.append(event)
            if event.get("type") in wanted:
                return collected
        raise Timeout(f"none of {sorted(wanted)} arrived")

    def wait_for_state(
        self, state: str, *, limit: int = 40, timeout: float = 5.0
    ) -> list[dict[str, Any]]:
        """Read events until a ``status`` event with that state arrives."""
        collected: list[dict[str, Any]] = []
        for _ in range(limit):
            event = self.next_event(timeout=timeout)
            collected.append(event)
            if (
                event.get("type") == "status"
                and event.get("payload", {}).get("state") == state
            ):
                return collected
        raise Timeout(f"the status {state!r} did not arrive")

    def drain(self, *, limit: int = 60, timeout: float = 2.0) -> list[dict[str, Any]]:
        """Read what is available, until the socket closes or times out."""
        collected: list[dict[str, Any]] = []
        for _ in range(limit):
            try:
                event = self.next_event(timeout=timeout)
            except (Timeout, Exception):  # noqa: BLE001 - the drain is best effort
                break
            collected.append(event)
        return collected

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.socket.__exit__(None, None, None)
        with contextlib.suppress(Exception):
            self.client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# the start event
# ---------------------------------------------------------------------------


def start_event(
    *,
    token: str | None = None,
    coaching_round_turns: int = 4,
    session_limit_seconds: int = 600,
    recording_retention: bool = False,
    consent_granted: bool = False,
    scenario_id: str = "everyday",
    practice_language_id: str = "english",
    coaching_language_id: str = "english",
    custom_topic: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A valid ``start`` event."""
    payload: dict[str, Any] = {
        "audio": {"sampleRateHz": 16000, "channels": 1, "sampleFormat": "s16le"},
        "settings": {
            "settingsVersion": "0.1",
            "practiceLanguageId": practice_language_id,
            "coachingLanguageId": coaching_language_id,
            "scenarioId": scenario_id,
            "level": "beginner",
            "coachingRoundTurns": coaching_round_turns,
            "sessionLimitSeconds": session_limit_seconds,
            "recordingRetention": recording_retention,
            "consent": {
                "consentVersion": "0.1",
                "recordingRetentionGranted": consent_granted,
                "recordingRetentionGrantedAt": (
                    "2026-10-20T10:00:00Z" if consent_granted else None
                ),
            },
        },
    }
    if custom_topic is not None:
        payload["settings"]["customTopic"] = custom_topic
    if token is not None:
        payload["auth"] = {"token": token}
    envelope: dict[str, Any] = {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": "start",
        "sessionId": None,
        "connectionId": None,
        "roundId": None,
        "turnId": None,
        "sequence": 0,
        "sampleTimeMs": None,
        "emittedAt": "2026-10-20T10:00:00Z",
        "payload": payload,
    }
    if extra:
        envelope.update(extra)
    return envelope


def control_event(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """A client control event."""
    return {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": kind,
        "sessionId": None,
        "connectionId": None,
        "roundId": None,
        "turnId": None,
        "sequence": 0,
        "sampleTimeMs": None,
        "emittedAt": "2026-10-20T10:00:00Z",
        "payload": payload or {},
    }
