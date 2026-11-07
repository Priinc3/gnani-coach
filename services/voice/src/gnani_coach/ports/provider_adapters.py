"""Adapters that make the Phase 02 provider clients satisfy the ports.

The provider package (``gnani_coach.providers``) belongs to Phase 02 and
is **not modified**. This module is the seam: it wraps the Phase 02
clients so that the rest of the service depends on the ports, never on a
provider class.

The wrappers are deliberately thin. They translate shapes and nothing
else: no policy, no retry logic, no capability judgement. A behaviour
that belongs to the provider (frame pacing, budgets, fencing) stays in the
provider adapter.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from gnani_coach.ports.reasoning import ReasoningPort, ReasoningReply, ReasoningRequest
from gnani_coach.ports.speech_to_text import (
    SpeechToTextPort,
    SpeechToTextSession,
    SttOpenRequest,
    SttRunResult,
    TranscriptSegment,
)
from gnani_coach.ports.text_to_speech import (
    SpeechChunk,
    TextToSpeechPort,
    TextToSpeechSession,
    TtsOpenRequest,
)
from gnani_coach.providers.gemini import CoachRequest, GeminiCoach, GeminiConfig
from gnani_coach.providers.stt import GnaniSttSession, SttConfig
from gnani_coach.providers.tts import (
    AudioConfig,
    GnaniTtsSession,
    TtsConfig,
)


class _SttSession:
    """A :class:`GnaniSttSession` seen through the speech-to-text port."""

    def __init__(self, session: GnaniSttSession) -> None:
        self._session = session

    async def stream_pcm(
        self, raw_pcm: bytes, *, trailing_silence_ms: int = 800
    ) -> SttRunResult:
        result = await self._session.stream_pcm(
            raw_pcm, trailing_silence_ms=trailing_silence_ms
        )
        clock = result.sample_clock
        # ``SampleClock`` exposes milliseconds through ``summary()``; the
        # attributes are ``genuine_seconds``/``submitted_seconds``/
        # ``padding_seconds``. Read the documented summary so a live
        # submission does not fail on a missing attribute.
        summary = clock.summary()
        return SttRunResult(
            segments=tuple(_segment_from_event(event) for event in result.transcripts),
            genuine_ms=int(summary["genuine_ms"]),
            submitted_ms=int(summary["submitted_ms"]),
            padding_ms=int(summary["padding_ms"]),
            end_padding_ms=result.end_padding_ms,
            unrecognized_frame_count=len(result.unrecognized_frames),
        )

    async def iter_transcripts(self) -> AsyncIterator[TranscriptSegment]:
        async for event in self._session.iter_transcripts():
            yield _segment_from_event(event)

    async def aclose(self, *, reason: str = "done") -> None:
        await self._session.aclose(reason=reason)

    async def fence(self) -> None:
        await self._session.fence()


def _segment_from_event(event: Any) -> TranscriptSegment:
    """Map one provider transcript event onto the port's segment."""
    return TranscriptSegment(
        segment_id=event.segment_id,
        segment_index=event.segment_index,
        text=event.text,
        latency_ms=event.latency_ms,
        server_timestamp=event.server_timestamp,
        learner_clock_samples=event.learner_clock_samples,
        status=event.status,
    )


class GnaniSpeechToTextAdapter:
    """Satisfies :class:`SpeechToTextPort` using the Phase 02 STT client."""

    def __init__(
        self,
        api_key: str,
        *,
        budget: Any | None = None,
        transport: Any | None = None,
        catalog_codes: Any | None = None,
        url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._budget = budget
        self._transport = transport
        self._catalog_codes = catalog_codes
        self._url = url

    def open_session(self, request: SttOpenRequest) -> SpeechToTextSession:
        config = SttConfig(
            language_code=request.language_code,
            sample_rate=request.sample_rate,
            output_format=request.output_format,
            vad=request.vad,
            **({"url": self._url} if self._url else {}),
        )
        session = GnaniSttSession(
            config,
            self._api_key,
            budget=self._budget,
            catalog_codes=self._catalog_codes,
            transport=self._transport,
        )
        return _SttSession(session)


class _TtsSession:
    """A :class:`GnaniTtsSession` seen through the text-to-speech port."""

    def __init__(self, session: GnaniTtsSession) -> None:
        self._session = session

    async def synthesize(self, *, on_chunk: Any | None = None) -> tuple[SpeechChunk, ...]:
        """Run one synthesis and deliver the chunks in order.

        ``on_chunk`` is called as the chunks arrive, so a live call can
        play them without waiting for the whole utterance. The provider
        only reveals a chunk's index once the synthesis is complete, so
        the streamed chunks carry no index and the returned tuple carries
        the ordered chunks with their provider indexes.
        """
        forward = None
        if on_chunk is not None:

            async def forward(data: bytes) -> None:  # type: ignore[misc]
                await on_chunk(SpeechChunk(data=data))

        result = await self._session.synthesize(forward=forward)
        return tuple(
            SpeechChunk(
                data=chunk.bytes,
                chunk_index=chunk.chunk_index,
                is_final=chunk.is_final,
            )
            for chunk in result.chunks
            if chunk.status == "observed"
        )

    async def cancel_consumption(self) -> None:
        await self._session.cancel_consumption()

    async def aclose(self, *, reason: str = "done") -> None:
        await self._session.aclose(reason=reason)


class GnaniTextToSpeechAdapter:
    """Satisfies :class:`TextToSpeechPort` using the Phase 02 TTS client."""

    def __init__(
        self,
        api_key: str,
        *,
        budget: Any | None = None,
        transport: Any | None = None,
        catalog_languages: Any | None = None,
        url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._budget = budget
        self._transport = transport
        self._catalog_languages = catalog_languages
        self._url = url

    def open_session(self, request: TtsOpenRequest) -> TextToSpeechSession:
        config = TtsConfig(
            text=request.text,
            voice=request.voice,
            model=request.model,
            language=request.language,
            speed=request.speed,
            audio=AudioConfig(sample_rate=request.sample_rate),
        )
        session = GnaniTtsSession(
            config,
            self._api_key,
            budget=self._budget,
            catalog_languages=self._catalog_languages,
            transport=self._transport,
            **({"url": self._url} if self._url else {}),
        )
        return _TtsSession(session)


class GeminiReasoningAdapter:
    """Satisfies :class:`ReasoningPort` using the Phase 02 Gemini client."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        budget: Any | None = None,
        client_factory: Any | None = None,
        attempt_timeout: float | None = None,
        deadline: float | None = None,
    ) -> None:
        config = GeminiConfig(model=model, store=False)
        kwargs: dict[str, Any] = {
            "budget": budget,
            "client_factory": client_factory,
        }
        if attempt_timeout is not None:
            kwargs["attempt_timeout"] = attempt_timeout
        if deadline is not None:
            kwargs["deadline"] = deadline
        self._coach = GeminiCoach(config, api_key, **kwargs)

    async def reply(self, request: ReasoningRequest) -> ReasoningReply:
        coach_request = CoachRequest(
            recognized_text=request.recognized_text,
            system_instruction=request.instruction,
            scenario=request.scenario,
            level=request.level,
            reply_language=request.reply_language,
        )
        event = await self._coach.reply(coach_request)
        return ReasoningReply(
            text=event.text,
            model=event.model,
            stored=event.store,
            tools_enabled=event.tools_enabled,
        )
