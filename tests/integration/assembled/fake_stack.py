"""Fake speech, reasoning and analysis ports for the assembled suite.

These fakes implement the **real ports**, and the launcher injects them at
the one factory the router uses (``build_call_providers``) plus the one
analysis accessor (``get_analysis``). Everything above them — the
runtime, the router, the envelope, the HTTP/WS service, the browser and
the Next.js server — is the real product.

Nothing here is a provider claim. The audio is a tone, the transcript is
a fixed script and the model is a lookup table. The labels in REPORT.md
and in the tests say so.
"""

from __future__ import annotations

import asyncio
import math
import struct
from dataclasses import dataclass
from typing import Any

from gnani_coach.analysis.service import TurnMeasurement
from gnani_coach.conversation.runtime import CallProviders
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
from gnani_coach.providers.errors import ProviderError
from gnani_coach.providers.stt import VadSettings

#: A recognisable transcript. The metrics-only inspection scans for
#: ``orchid`` in the database, the log and the temporary directories; it
#: must never appear.
TRANSCRIPT_SENTINEL = "orchid"
TRANSCRIPT_TEXTS = (
    "orchid lantern compass",
    "orchid lantern compass again",
    "orchid lantern compass please",
    "orchid lantern compass now",
)
#: A recognisable reply and custom topic, for the same inspection.
REPLY_SENTINEL = "That sounds clear. What happened next?"
REPLY_TEXTS = (
    REPLY_SENTINEL,
    "That sounds clear. Tell me a little more.",
    "That sounds clear. What would you say first?",
    "That sounds clear. How did that feel?",
)
TOPIC_SENTINEL = "garden planning afternoon"

FRAME_BYTES = 1024


@dataclass
class Behaviour:
    """Fault injection for the assembled failure matrix.

    ``tts_fail_after`` > 0 raises after that many chunks, which is how
    "TTS down mid-sentence" is produced. ``reasoning_mode`` is ``None``,
    ``"timeout"`` or ``"malformed"``.
    """

    stt_fail: bool = False
    #: ``network``, ``auth`` or ``throttle``; ``None`` is healthy.
    stt_mode: str | None = None
    tts_fail: bool = False
    tts_fail_after: int = 0
    reasoning_mode: str | None = None
    reasoning_delay: float = 0.25

    def reset(self) -> None:
        self.stt_fail = False
        self.stt_mode = None
        self.tts_fail = False
        self.tts_fail_after = 0
        self.reasoning_mode = None
        self.reasoning_delay = 0.25

    def as_dict(self) -> dict[str, Any]:
        return {
            "sttFail": self.stt_fail,
            "sttMode": self.stt_mode,
            "ttsFail": self.tts_fail,
            "ttsFailAfter": self.tts_fail_after,
            "reasoningMode": self.reasoning_mode,
        }


BEHAVIOUR = Behaviour()


def _is_loud(frame: bytes) -> bool:
    """The same energy gate the runtime uses, as a coarse speech check."""
    if len(frame) < FRAME_BYTES:
        return False
    total = 0
    count = len(frame) // 2
    for index in range(0, len(frame) - 1, 2):
        sample = int.from_bytes(frame[index : index + 2], "little", signed=True)
        total += sample * sample
    if total <= 0:
        return False
    rms = math.sqrt(total / count)
    return 20.0 * math.log10(rms / 32768.0) >= -45.0


class _NetworkError(ProviderError):
    category = "network"
    retryable = True


class _AuthError(ProviderError):
    category = "invalid_request"
    retryable = False


class _ThrottleError(ProviderError):
    category = "rate_limited"
    retryable = True


class FakeSttSession:
    def __init__(self, port: "FakeSttPort") -> None:
        self._port = port
        self.closed = False

    async def stream_pcm(self, raw_pcm: bytes, *, trailing_silence_ms: int = 800) -> SttRunResult:
        if BEHAVIOUR.stt_fail or BEHAVIOUR.stt_mode == "network":
            raise _NetworkError("the recogniser is unavailable", provider="gnani-stt")
        if BEHAVIOUR.stt_mode == "auth":
            raise _AuthError("the recogniser rejected the key", provider="gnani-stt")
        if BEHAVIOUR.stt_mode == "throttle":
            raise _ThrottleError("the recogniser is throttled", provider="gnani-stt")
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
        return


class FakeSttPort:
    """A recogniser that closes one segment per run of speech."""

    def __init__(self) -> None:
        self.segment_index = 0
        self.text_index = 0
        self.submissions = 0
        self.requests: list[SttOpenRequest] = []
        self._residual = b""

    def open_session(self, request: SttOpenRequest) -> FakeSttSession:
        self.requests.append(request)
        return FakeSttSession(self)

    def recognise(self, raw_pcm: bytes) -> list[TranscriptSegment]:
        self.submissions += 1
        segments: list[TranscriptSegment] = []
        running = False
        data = self._residual + raw_pcm
        complete = len(data) - (len(data) % FRAME_BYTES)
        self._residual = data[complete:]
        for start in range(0, complete, FRAME_BYTES):
            frame = data[start : start + FRAME_BYTES]
            if _is_loud(frame):
                running = True
                continue
            if running:
                running = False
                text = TRANSCRIPT_TEXTS[self.text_index % len(TRANSCRIPT_TEXTS)]
                self.text_index += 1
                segments.append(
                    TranscriptSegment(
                        segment_id=f"seg_assembled{self.segment_index:04d}",
                        segment_index=self.segment_index,
                        text=text,
                        latency_ms=12,
                        server_timestamp=None,
                        learner_clock_samples=0,
                    )
                )
                self.segment_index += 1
        return segments


def _tone(ms: int = 32, *, frequency: float = 320.0, amplitude: float = 0.25) -> bytes:
    count = int(16000 * ms / 1000)
    samples = [
        int(32767 * amplitude * math.sin(2 * math.pi * frequency * index / 16000.0))
        for index in range(count)
    ]
    return struct.pack(f"<{count}h", *samples)


#: One coach reply chunk: 32 ms of tone at 16 kHz mono s16le.
TTS_CHUNK = _tone(32)


class FakeTtsSession:
    def __init__(self, request: TtsOpenRequest, *, chunk_count: int = 30) -> None:
        self.request = request
        self.chunk_count = chunk_count
        self.cancelled = False
        self.closed = False

    async def synthesize(self, *, on_chunk: Any = None) -> tuple[SpeechChunk, ...]:
        chunks: list[SpeechChunk] = []
        for index in range(self.chunk_count):
            if BEHAVIOUR.tts_fail:
                raise _NetworkError("the synthesiser is unavailable", provider="gnani-tts")
            if BEHAVIOUR.tts_fail_after and index >= BEHAVIOUR.tts_fail_after:
                raise _NetworkError(
                    "the synthesiser closed mid-sentence", provider="gnani-tts"
                )
            if self.cancelled:
                break
            chunk = SpeechChunk(
                data=TTS_CHUNK,
                chunk_index=index,
                is_final=index == self.chunk_count - 1,
            )
            chunks.append(chunk)
            if on_chunk is not None:
                await on_chunk(chunk)
            # A real synthesiser streams in real time. The delay gives the
            # interface a visible "Speaking" state and the interrupt test
            # a window in which to speak over the coach.
            await asyncio.sleep(0.025)
        return tuple(chunks)

    async def cancel_consumption(self) -> None:
        self.cancelled = True

    async def aclose(self, *, reason: str = "done") -> None:
        del reason
        self.closed = True


class FakeTtsPort:
    def __init__(self) -> None:
        self.sessions: list[FakeTtsSession] = []
        self.requests: list[TtsOpenRequest] = []

    def open_session(self, request: TtsOpenRequest) -> FakeTtsSession:
        self.requests.append(request)
        session = FakeTtsSession(request)
        self.sessions.append(session)
        return session


class FakeReasoning:
    """A model whose answers are a script. No provider is called."""

    def __init__(self) -> None:
        self.replies = list(REPLY_TEXTS)
        self.requests: list[Any] = []

    async def reply(self, request: Any) -> ReasoningReply:
        self.requests.append(request)
        if BEHAVIOUR.reasoning_delay:
            await asyncio.sleep(BEHAVIOUR.reasoning_delay)
        if BEHAVIOUR.reasoning_mode == "timeout":
            raise TimeoutError("the reasoning provider timed out")
        if BEHAVIOUR.reasoning_mode == "malformed":
            # Valid text, but not the JSON feedback shape. The runtime must
            # fall back to the facts-only message.
            return ReasoningReply(
                text="not a feedback document",
                model="fake-model",
                stored=False,
                tools_enabled=False,
            )
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return ReasoningReply(text=text, model="fake-model", stored=False, tools_enabled=False)


def _observations() -> tuple[AnalysisObservation, ...]:
    return (
        AnalysisObservation(
            metric_key="turn.duration_ms",
            status="available",
            value=1800,
            unit="milliseconds",
            method="learner_audio_sample_clock",
            evidence_span=(0, 1800),
        ),
        AnalysisObservation(
            metric_key="speech.rate_wpm",
            status="available",
            value=110.0,
            unit="words_per_minute",
            method="stt_words_over_learner_span",
            denominator="learner_span_ms",
            evidence_span=(0, 1800),
        ),
        AnalysisObservation(
            metric_key="speech.active_rate_wpm",
            status="available",
            value=180.0,
            unit="words_per_minute",
            method="stt_words_over_speech_active",
            denominator="speech_active_ms",
            evidence_span=(0, 1800),
        ),
        AnalysisObservation(
            metric_key="pause.count",
            status="available",
            value=1,
            unit="count",
            method="vad_speech_regions",
            evidence_span=(0, 1800),
        ),
        AnalysisObservation(
            metric_key="pause.longest_ms",
            status="available",
            value=400,
            unit="milliseconds",
            method="vad_speech_regions",
            evidence_span=(0, 1800),
        ),
        AnalysisObservation(
            metric_key="filler.count",
            status="insufficient_evidence",
            value=None,
            unit=None,
            unavailability_reason="filler_detection_unvalidated",
        ),
    )


class FakeAnalysis:
    """Scripted observations; no signal processing and no model."""

    def __init__(self) -> None:
        self.requests: list[AnalysisRequest] = []

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        self.requests.append(request)
        return AnalysisResult(
            recognition_status="measured",
            observations=_observations(),
            audio_source=request.audio_source,
        )

    async def measure(self, request: AnalysisRequest) -> TurnMeasurement:
        return TurnMeasurement(result=await self.analyze(request), speech_active_ms=900)


FAKE_ANALYSIS = FakeAnalysis()


def build_fake_providers(practice_language_id: str) -> CallProviders:
    """The provider set one assembled call uses."""
    return CallProviders(
        stt=FakeSttPort(),
        tts=FakeTtsPort(),
        reasoning=FakeReasoning(),
        language_code="en-IN",
        stt_vad=VadSettings(),
        tts_voice="Kaveri",
        tts_model="timbre-v2.5",
        tts_language="en-IN",
    )
