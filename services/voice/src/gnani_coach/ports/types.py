"""Shared vocabulary for the service ports.

Every value here mirrors a closed set in
``packages/contracts/schemas/``. The two runtimes must not drift: a port
value is written into a contract document, so it is a controlled identifier
and never free text.

The identifiers are plain strings so they serialise straight into the
contract shapes. The ``Literal`` aliases exist for type checking and for
the documentation value they carry.
"""

from __future__ import annotations

from typing import Literal

#: Opaque identifiers. The prefix identifies the kind; whether an id belongs
#: to a current session is a runtime identity check, not a shape check.
SessionId = str
ConnectionId = str
TurnId = str
RoundId = str
UserId = str
RecordingId = str
CorrelationId = str
ScenarioId = str

MetricKey = Literal[
    "pause.longest_ms",
    "pause.count",
    "filler.count",
    "speech.rate_wpm",
    "speech.active_rate_wpm",
    "turn.duration_ms",
]

MethodId = Literal[
    "vad_speech_regions",
    "stt_words_over_learner_span",
    "stt_words_over_speech_regions",
    "stt_words_over_speech_active",
    "disfluency_recognition",
    "learner_audio_sample_clock",
]

Denominator = Literal["learner_span_ms", "speech_active_ms"]

#: What the recogniser produced for an audio span.
#:
#: ``no-analyzable-speech`` and ``missing-transcription`` are NOT a measured
#: zero: a rate under them is absent, never 0.
RecognitionStatus = Literal[
    "measured",
    "no-analyzable-speech",
    "missing-transcription",
]

#: The declared source of a measured clip. A declaration, not a proof of
#: diarization or echo cancellation.
AudioSourceClassification = Literal["learner-audio", "synthetic-learner-audio"]

ObservationStatus = Literal["available", "unavailable", "insufficient_evidence"]

UnavailabilityReason = Literal[
    "stt_unavailable",
    "speech_analysis_unavailable",
    "too_little_speech",
    "filler_detection_unvalidated",
]

#: A measured region on the learner-audio sample clock. There is no
#: word-level timing anywhere in this project.
EvidenceSpan = tuple[int, int]

#: The stable error categories. ``not_available`` is what a frozen but
#: unimplemented seam answers with.
ErrorCategory = Literal[
    "invalid_request",
    "unauthenticated",
    "forbidden",
    "not_found",
    "conflict",
    "rate_limited",
    "provider_unavailable",
    "timeout",
    "cancelled",
    "not_available",
    "internal",
]
