"""The analysis port.

Analysis turns the learner's own audio (and, where it exists, the
recognised text) into measured observations. The contract rules that the
port exists to enforce:

* the four denominators stay separate — the elapsed learner-audio span,
  the speech-active duration, and never connection or session time;
* a missing transcription or a transcript with no analyzable speech is
  **not** a measured zero: the rate is absent and the recognition status
  says why;
* the measured audio declares its source, and that declaration is not a
  proof of diarization or echo cancellation;
* a missing or unvalidated filler count is ``insufficient_evidence``,
  never 0.

The Phase 03 stub (``gnani_coach.analysis``) returns
``insufficient_evidence`` for everything, because no filler detector has
passed. Phase 05 replaces the implementation; the port does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from gnani_coach.ports.types import (
    AudioSourceClassification,
    Denominator,
    EvidenceSpan,
    MethodId,
    MetricKey,
    ObservationStatus,
    RecognitionStatus,
    RoundId,
    TurnId,
    UnavailabilityReason,
)


@dataclass(frozen=True)
class AnalysisRequest:
    """What one analysis pass is given.

    ``recognized_text`` is ``None`` when no transcript was obtained, and
    an empty string when the recogniser ran and returned nothing
    analyzable. The two are different facts and are reported differently.
    """

    audio: bytes
    sample_rate: int = 16000
    turn_id: TurnId | None = None
    round_id: RoundId | None = None
    recognized_text: str | None = None
    audio_source: AudioSourceClassification = "learner-audio"
    #: True when the clip came from a fixture rather than a live learner.
    synthetic: bool = False


@dataclass(frozen=True)
class AnalysisObservation:
    """One measured-or-unavailable observation."""

    metric_key: MetricKey
    status: ObservationStatus
    value: float | None = None
    unit: str | None = None
    method: MethodId | None = None
    denominator: Denominator | None = None
    recognition_status: RecognitionStatus | None = None
    unavailability_reason: UnavailabilityReason | None = None
    evidence_span: EvidenceSpan | None = None
    reliability_level: str = "unknown"
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisResult:
    """The outcome of one analysis pass."""

    recognition_status: RecognitionStatus
    observations: tuple[AnalysisObservation, ...] = field(default_factory=tuple)
    audio_source: AudioSourceClassification = "learner-audio"

    @property
    def has_measured_rate(self) -> bool:
        """True only when a rate was actually measured."""
        return self.recognition_status == "measured"


@runtime_checkable
class AnalysisPort(Protocol):
    """The application-facing analysis boundary."""

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Measure one turn's audio."""
        ...
