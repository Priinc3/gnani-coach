"""The service ports.

These are the boundaries the application code depends on. They are frozen
in Phase 03 so that the parallel build group does not have to guess an
API: the call UI, the coaching runtime and the private-history module
all import from here and never from a provider package.

| Port | What it owns | Owner after the freeze |
|---|---|---|
| :class:`SpeechToTextPort` | recognition sessions and the learner sample clock | Phase 05 |
| :class:`TextToSpeechPort` | synthesis sessions and chunk ordering | Phase 05 |
| :class:`ReasoningPort` | one bounded coach reply | Phase 05 |
| :class:`AnalysisPort` | measured observations for one turn | Phase 05 |
| :class:`IdentityPort` | bearer token to user id | Phase 06 |
| :class:`SessionStorePort` | metrics-only persistence | Phase 06 |
| :class:`RecordingStorePort` | opt-in audio retention | Phase 06 |

The provider clients from Phase 02 are reached through
:mod:`gnani_coach.ports.provider_adapters`, so the provider package is
never edited to satisfy a port.

This package also carries the **origin policy**
(:mod:`gnani_coach.ports.origins`): ``origin_allowed(origin)`` is the
single answer to "may this client open the call socket?", and Phase 05's
``/ws/call`` router calls it before ``accept()``.
"""

from gnani_coach.ports.analysis import (
    AnalysisObservation,
    AnalysisPort,
    AnalysisRequest,
    AnalysisResult,
)
from gnani_coach.ports.identity import IdentityPort
from gnani_coach.ports.origins import allowed_origins, origin_allowed
from gnani_coach.ports.provider_adapters import (
    GeminiReasoningAdapter,
    GnaniSpeechToTextAdapter,
    GnaniTextToSpeechAdapter,
)
from gnani_coach.ports.reasoning import ReasoningPort, ReasoningReply, ReasoningRequest
from gnani_coach.ports.recording_store import RecordingRef, RecordingStorePort
from gnani_coach.ports.session_store import SessionStorePort, SessionSummary
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
from gnani_coach.ports.types import (
    AudioSourceClassification,
    ConnectionId,
    CorrelationId,
    Denominator,
    ErrorCategory,
    EvidenceSpan,
    MetricKey,
    MethodId,
    ObservationStatus,
    RecognitionStatus,
    RecordingId,
    RoundId,
    ScenarioId,
    SessionId,
    TurnId,
    UnavailabilityReason,
    UserId,
)

__all__ = [
    "AnalysisObservation",
    "AnalysisPort",
    "AnalysisRequest",
    "AnalysisResult",
    "AudioSourceClassification",
    "ConnectionId",
    "CorrelationId",
    "Denominator",
    "ErrorCategory",
    "EvidenceSpan",
    "GeminiReasoningAdapter",
    "GnaniSpeechToTextAdapter",
    "GnaniTextToSpeechAdapter",
    "IdentityPort",
    "MetricKey",
    "MethodId",
    "ObservationStatus",
    "ReasoningPort",
    "ReasoningReply",
    "ReasoningRequest",
    "RecognitionStatus",
    "RecordingId",
    "RecordingRef",
    "RecordingStorePort",
    "RoundId",
    "ScenarioId",
    "SessionId",
    "SessionStorePort",
    "SessionSummary",
    "SpeechChunk",
    "SpeechToTextPort",
    "SpeechToTextSession",
    "SttOpenRequest",
    "SttRunResult",
    "TextToSpeechPort",
    "TextToSpeechSession",
    "TranscriptSegment",
    "TurnId",
    "TtsOpenRequest",
    "UnavailabilityReason",
    "UserId",
    "allowed_origins",
    "origin_allowed",
]
