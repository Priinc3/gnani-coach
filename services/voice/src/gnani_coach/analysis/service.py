"""The analysis service — the real :class:`AnalysisPort` implementation.

Phase 03 shipped a stub that answered ``insufficient_evidence`` for every
metric. This module is the real measurement, re-homed from the Phase 02
probe semantics (see :mod:`gnani_coach.analysis.measurement` and
:mod:`gnani_coach.analysis.vad`) into the service tree.

What it guarantees
------------------

* **The four denominators stay separate.** ``speech.rate_wpm`` divides by
  the elapsed learner-audio span; ``speech.active_rate_wpm`` divides by
  the VAD-estimated speech-active time. Neither is ever connection time,
  session time, network round-trip time or provider emission time.
* **A missing transcription is never a measured zero.** ``None`` means
  ``missing-transcription`` and every rate is absent with a null value;
  an empty transcript means ``no-analyzable-speech`` and the rates are
  absent too. A transcript that exists but holds no words is a genuine
  measured ``0``.
* **The measured audio declares its source.** The trusted-source rule
  refuses an empty, assistant-only, mixed or unknown classification
  *before* a measurement is produced. A source label is a declaration,
  not a proof of diarization or echo cancellation.
* **The filler capability is unvalidated.** The filler count is always
  ``insufficient_evidence`` with the reason
  ``filler_detection_unvalidated`` and a null value. Never ``0``.
* **Only the learner's own audio is measured.** The coach's audio never
  enters an analysis request: the runtime only ever hands this service
  the learner's own frames.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass

from gnani_coach.analysis.measurement import (
    LIVE_LEARNER,
    RECOGNITION_MEASURED,
    RECOGNITION_MISSING,
    RECOGNITION_NO_SPEECH,
    SYNTHETIC_LEARNER,
    ClipSource,
    assert_trusted_learner_source,
    compute,
    count_words,
)
from gnani_coach.analysis.vad import (
    MODEL_SHA256,
    ModelAsset,
    ModelAssetMissing,
    SileroVad,
    asset_present,
    model_path,
)
from gnani_coach.ports.analysis import (
    AnalysisObservation,
    AnalysisPort,
    AnalysisRequest,
    AnalysisResult,
)
from gnani_coach.ports.types import (
    AudioSourceClassification,
    ObservationStatus,
    RecognitionStatus,
    UnavailabilityReason,
)

LOGGER = logging.getLogger("gnani_coach.analysis")

#: The metric keys the service reports on. The keys are the contract's
#: allowlist; only some of them can ever carry a value.
REPORTED_METRIC_KEYS = (
    "pause.longest_ms",
    "pause.count",
    "filler.count",
    "speech.rate_wpm",
    "speech.active_rate_wpm",
    "turn.duration_ms",
)

#: A pause shorter than this is not a pause worth reporting.
MIN_PAUSE_MS = 300

#: A turn with less speech-active time than this has too little speech for
#: a pause measurement.
MIN_SPEECH_ACTIVE_MS = 200

#: The trusted source declarations this service accepts.
_TRUSTED_SOURCES: dict[str, ClipSource] = {
    "learner-audio": LIVE_LEARNER,
    "synthetic-learner-audio": SYNTHETIC_LEARNER,
}


@dataclass
class _VadEngine:
    """Lazily loaded Silero VAD, shared by every analysis in the process.

    The ONNX session is expensive to build and is safe to share: the
    recurrent state is per call, not per session.
    """

    threshold: float = 0.5
    _lock: threading.Lock = threading.Lock()
    _model: SileroVad | None = None
    _attempted: bool = False

    @property
    def available(self) -> bool:
        """True when a prepared, hash-verified asset is present."""
        if self._model is not None:
            return True
        if self._attempted:
            return False
        return asset_present()

    def _load(self) -> SileroVad | None:
        with self._lock:
            if self._model is not None:
                return self._model
            if self._attempted:
                return None
            self._attempted = True
            path = model_path()
            if not path.is_file():
                return None
            asset = ModelAsset(
                path=path,
                sha256=MODEL_SHA256,
                bytes=path.stat().st_size,
                source="pinned asset; see gnani_coach.analysis.vad",
                license="MIT (snakers4/silero-vad)",
            )
            try:
                self._model = SileroVad(asset, threshold=self.threshold)
            except (ModelAssetMissing, OSError, Exception):  # noqa: BLE001
                # A broken or absent asset is an honest "unavailable", never
                # a crash of the call path.
                self._model = None
            return self._model

    def analyse(self, pcm: bytes, sample_rate: int):
        """Estimate the speech regions of one clip, or ``None``."""
        model = self._load()
        if model is None:
            return None
        try:
            return model.analyse(
                pcm,
                sample_rate,
                min_speech_ms=100,
                min_silence_ms=MIN_PAUSE_MS,
            )
        except (ValueError, ModelAssetMissing):
            return None


@dataclass(frozen=True)
class TurnMeasurement:
    """One measured turn, with the speech-active time beside it.

    The analysis **port** returns only the observations. The
    conversation runtime also needs the detected speech-active time, to
    write ``totals.speakingTimeMs``; this method carries it without
    changing the frozen port.
    """

    result: AnalysisResult
    speech_active_ms: int


class LearnerAudioAnalysis:
    """The analysis port, backed by the learner's own audio.

    The service is stateless apart from the shared VAD engine, so one
    instance may serve every call.
    """

    def __init__(self, *, engine: _VadEngine | None = None) -> None:
        self._engine = engine if engine is not None else _VadEngine()

    # -- port ----------------------------------------------------------
    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Measure one turn's audio."""
        measurement = await self.measure(request)
        return measurement.result

    async def measure(self, request: AnalysisRequest) -> TurnMeasurement:
        """Measure one turn's audio, with the speech-active time.

        The measurement is CPU-bound (the ONNX inference), so it runs in a
        worker thread: the call loop must keep serving the socket while a
        turn is measured.
        """
        source = _TRUSTED_SOURCES.get(str(request.audio_source))
        try:
            assert_trusted_learner_source([source] if source is not None else [])
        except Exception:  # noqa: BLE001 - the refusal is the answer
            LOGGER.warning(
                "analysis refused: audio source classification is not a trusted "
                "learner source"
            )
            return TurnMeasurement(
                result=_refused_result(request), speech_active_ms=0
            )

        span_ms = _span_ms(len(request.audio), request.sample_rate)
        recognition_status = _recognition_status(request.recognized_text)

        vad_result = None
        if request.audio:
            vad_result = await asyncio.to_thread(
                self._engine.analyse, request.audio, request.sample_rate
            )

        if vad_result is None:
            speech_active_ms = 0
            pauses: list[int] = []
            pause_status: ObservationStatus = "unavailable"
            pause_reason: UnavailabilityReason = "speech_analysis_unavailable"
        else:
            speech_active_ms = vad_result.speech_active_ms
            pauses = [
                region.duration_ms
                for region in vad_result.internal_pauses(MIN_PAUSE_MS)
            ]
            if vad_result.speech_samples == 0:
                # No speech at all: there is no pause structure to measure.
                pause_status = "insufficient_evidence"
                pause_reason = "too_little_speech"
            elif speech_active_ms < MIN_SPEECH_ACTIVE_MS:
                pause_status = "insufficient_evidence"
                pause_reason = "too_little_speech"
            else:
                pause_status = "available"
                pause_reason = "too_little_speech"  # unused when available

        metrics = compute(
            clip_span_ms=span_ms,
            speech_active_ms=speech_active_ms,
            recognized_text=request.recognized_text,
            internal_pause_ms=pauses,
            source_labels=[source.label] if source is not None else [],
        )

        observations = self._observations(
            request=request,
            metrics=metrics,
            span_ms=span_ms,
            speech_active_ms=speech_active_ms,
            recognition_status=recognition_status,
            pause_status=pause_status,
            pause_reason=pause_reason,
        )
        return TurnMeasurement(
            result=AnalysisResult(
                recognition_status=recognition_status,
                observations=observations,
                audio_source=request.audio_source,
            ),
            speech_active_ms=speech_active_ms,
        )

    # -- observations --------------------------------------------------
    def _observations(
        self,
        *,
        request: AnalysisRequest,
        metrics,
        span_ms: int,
        speech_active_ms: int,
        recognition_status: RecognitionStatus,
        pause_status: ObservationStatus,
        pause_reason: UnavailabilityReason,
    ) -> tuple[AnalysisObservation, ...]:
        """Build the six observations, with their methods and denominators."""
        limitations = (
            "speech regions are an estimate from Silero VAD, validated against "
            "synthetic signals only",
        )
        rate_limitations = limitations + (
            "; the word count comes from an imperfect recogniser",
        )
        observations: list[AnalysisObservation] = []

        # turn.duration_ms — the elapsed learner-audio span. Always
        # measurable from the clip itself, and never carries a
        # recognition status: a transcript says nothing about a duration.
        observations.append(
            AnalysisObservation(
                metric_key="turn.duration_ms",
                status="available",
                value=int(span_ms),
                unit="milliseconds",
                method="learner_audio_sample_clock",
                denominator=None,
                recognition_status=None,
                unavailability_reason=None,
                evidence_span=(0, int(span_ms)),
                reliability_level="medium",
                limitations=(limitations,),
            )
        )

        # pause.longest_ms / pause.count — VAD speech regions.
        if pause_status == "available":
            observations.append(
                AnalysisObservation(
                    metric_key="pause.longest_ms",
                    status="available",
                    value=int(metrics.longest_pause_ms),
                    unit="milliseconds",
                    method="vad_speech_regions",
                    denominator=None,
                    recognition_status=None,
                    unavailability_reason=None,
                    evidence_span=(0, int(span_ms)),
                    reliability_level="medium",
                    limitations=(limitations,),
                )
            )
            observations.append(
                AnalysisObservation(
                    metric_key="pause.count",
                    status="available",
                    value=int(metrics.pause_count),
                    unit="count",
                    method="vad_speech_regions",
                    denominator=None,
                    recognition_status=None,
                    unavailability_reason=None,
                    evidence_span=(0, int(span_ms)),
                    reliability_level="medium",
                    limitations=(limitations,),
                )
            )
        else:
            for metric_key in ("pause.longest_ms", "pause.count"):
                observations.append(
                    AnalysisObservation(
                        metric_key=metric_key,  # type: ignore[arg-type]
                        status=pause_status,
                        value=None,
                        unit=None,
                        method=None,
                        denominator=None,
                        recognition_status=None,
                        unavailability_reason=pause_reason,
                        evidence_span=(0, int(span_ms)),
                        reliability_level="unknown",
                        limitations=(limitations,),
                    )
                )

        # filler.count — always unvalidated. Never a number, never 0.
        observations.append(
            AnalysisObservation(
                metric_key="filler.count",
                status="insufficient_evidence",
                value=None,
                unit=None,
                method=None,
                denominator=None,
                recognition_status=None,
                unavailability_reason="filler_detection_unvalidated",
                evidence_span=None,
                reliability_level="unknown",
                limitations=(
                    "no filler detector has passed validation; a filler count "
                    "would be a guess, so none is reported",
                ),
            )
        )

        # speech.rate_wpm — words over the elapsed learner span.
        observations.append(
            _rate_observation(
                metric_key="speech.rate_wpm",
                method="stt_words_over_learner_span",
                denominator="learner_span_ms",
                value=metrics.rate_wpm,
                recognition_status=recognition_status,
                span_ms=span_ms,
                limitations=rate_limitations,
            )
        )

        # speech.active_rate_wpm — words over the speech-active duration.
        active_value = metrics.active_rate_wpm
        if active_value is None and speech_active_ms <= 0:
            active_reason: UnavailabilityReason = "too_little_speech"
        else:
            active_reason = "too_little_speech"
        observations.append(
            _rate_observation(
                metric_key="speech.active_rate_wpm",
                method="stt_words_over_speech_active",
                denominator="speech_active_ms",
                value=active_value,
                recognition_status=recognition_status,
                span_ms=span_ms,
                limitations=rate_limitations,
                extra_reason=active_reason,
            )
        )
        return tuple(observations)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _span_ms(byte_length: int, sample_rate: int) -> int:
    """The elapsed learner-audio span of a clip, in milliseconds.

    ``byte_length`` is raw mono s16le, so the sample count is half of it.
    The span **includes** the source's leading and trailing silence and
    **excludes** any end padding, because the padding is never part of the
    audio the runtime hands over.
    """
    if sample_rate <= 0:
        return 0
    samples = max(0, byte_length // 2)
    return int(round(samples * 1000.0 / sample_rate))


def _recognition_status(recognized_text: str | None) -> RecognitionStatus:
    """Three outcomes, kept distinct on purpose."""
    if recognized_text is None:
        return RECOGNITION_MISSING
    if recognized_text == "":
        return RECOGNITION_NO_SPEECH
    return RECOGNITION_MEASURED


def _rate_observation(
    *,
    metric_key: str,
    method: str,
    denominator: str,
    value: float | None,
    recognition_status: RecognitionStatus,
    span_ms: int,
    limitations: tuple[str, ...],
    extra_reason: UnavailabilityReason = "too_little_speech",
) -> AnalysisObservation:
    """One rate observation: measured, or absent with a reason.

    A rate under a missing or unanalyzable transcript is **absent**, never
    ``0``: that is the whole point of the recognition status.
    """
    if value is None:
        reason: UnavailabilityReason = (
            "stt_unavailable"
            if recognition_status == RECOGNITION_MISSING
            else extra_reason
        )
        status: ObservationStatus = (
            "unavailable"
            if recognition_status == RECOGNITION_MISSING
            else "insufficient_evidence"
        )
        return AnalysisObservation(
            metric_key=metric_key,  # type: ignore[arg-type]
            status=status,
            value=None,
            unit=None,
            method=None,
            denominator=None,
            recognition_status=recognition_status,
            unavailability_reason=reason,
            evidence_span=(0, int(span_ms)),
            reliability_level="unknown",
            limitations=limitations,
        )
    return AnalysisObservation(
        metric_key=metric_key,  # type: ignore[arg-type]
        status="available",
        value=float(value),
        unit="words_per_minute",
        method=method,  # type: ignore[arg-type]
        denominator=denominator,  # type: ignore[arg-type]
        recognition_status=recognition_status,
        unavailability_reason=None,
        evidence_span=(0, int(span_ms)),
        reliability_level="medium",
        limitations=limitations,
    )


def _refused_result(request: AnalysisRequest) -> AnalysisResult:
    """The answer to a measurement that may not be taken at all.

    No observation carries a value, and the reason says why: the audio
    source was not a trusted learner source.
    """
    observations = tuple(
        AnalysisObservation(
            metric_key=metric_key,  # type: ignore[arg-type]
            status="unavailable",
            value=None,
            unit=None,
            method=None,
            denominator=None,
            recognition_status=None,
            unavailability_reason="speech_analysis_unavailable",
            evidence_span=None,
            reliability_level="unknown",
            limitations=(
                "the measurement was refused: the audio source was not an "
                "explicitly trusted learner source",
            ),
        )
        for metric_key in REPORTED_METRIC_KEYS
    )
    return AnalysisResult(
        recognition_status=_recognition_status(request.recognized_text),
        observations=observations,
        audio_source=request.audio_source,
    )


def count_recognised_words(text: str | None) -> int:
    """The word count of a transcript, or 0 when there is no transcript."""
    if not text:
        return 0
    return count_words(text)
