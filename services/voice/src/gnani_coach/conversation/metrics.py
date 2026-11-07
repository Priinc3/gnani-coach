"""The durable-metrics document, and the writer boundary that guards it.

At the end of a call the runtime builds the **durable metrics** document:
numbers and controlled identifiers only. The shape is the frozen
``durable-metrics`` v0.1 schema
(``packages/contracts/schemas/durable-metrics.schema.json``).

The document is validated **before** it is handed to the session store.
The JSON Schema package is a development dependency of this service, so
the runtime validates with the rules mirrored here; the test suite proves
the mirror agrees with the real schema by running both over the same
documents.

What the writer boundary refuses
---------------------------------

* a property the schema forbids (``transcript``, ``quotedMistakes``,
  ``modelText``, ``audioUrl``, ``embedding``, ``customTopic``);
* a metric key bound to the wrong method, unit or denominator;
* an unavailable observation that carries a value, and an available
  observation that carries no value;
* a rate that claims to be available under a missing or unanalyzable
  transcript — a missing transcription is never a measured zero;
* a speaking time larger than the sum of the turn durations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from gnani_coach.ports.analysis import AnalysisObservation

#: The frozen metric bindings: metric key -> (method, unit, denominator).
METRIC_BINDINGS: dict[str, tuple[str, str, str | None]] = {
    "pause.longest_ms": ("vad_speech_regions", "milliseconds", None),
    "pause.count": ("vad_speech_regions", "count", None),
    "filler.count": ("disfluency_recognition", "count", None),
    "speech.rate_wpm": (
        "stt_words_over_learner_span",
        "words_per_minute",
        "learner_span_ms",
    ),
    "speech.active_rate_wpm": (
        "stt_words_over_speech_active",
        "words_per_minute",
        "speech_active_ms",
    ),
    "turn.duration_ms": ("learner_audio_sample_clock", "milliseconds", None),
}

#: The observation keys that may not carry a recognition status.
_NO_RECOGNITION_STATUS = frozenset(
    {"pause.longest_ms", "pause.count", "turn.duration_ms"}
)

#: The properties the durable schema forbids by name.
FORBIDDEN_PROPERTIES = (
    "transcript",
    "quotedMistakes",
    "modelText",
    "audioUrl",
    "embedding",
    "customTopic",
)

#: The closed vocabularies of the durable shape.
RECOGNITION_STATUSES = ("measured", "no-analyzable-speech", "missing-transcription")
SOURCE_CLASSIFICATIONS = ("learner-audio", "synthetic-learner-audio")
OBSERVATION_STATUSES = ("available", "unavailable", "insufficient_evidence")
UNAVAILABILITY_REASONS = (
    "stt_unavailable",
    "speech_analysis_unavailable",
    "too_little_speech",
    "filler_detection_unvalidated",
)

_TURN_ID_RE = re.compile(r"^trn_[a-z0-9]{6,40}$")
_ROUND_ID_RE = re.compile(r"^rnd_[a-z0-9]{6,40}$")
_SESSION_ID_RE = re.compile(r"^ses_[a-z0-9]{6,40}$")
_RECORDING_ID_RE = re.compile(r"^rec_[a-z0-9]{6,40}$")
_CATALOG_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


@dataclass
class TurnMetrics:
    """The measured facts of one completed turn."""

    turn_id: str
    round_id: str | None
    duration_ms: int
    recognition_status: str
    audio_source_classification: str
    observations: tuple[AnalysisObservation, ...] = ()
    #: The VAD-estimated speech-active time of the turn, in milliseconds.
    speech_active_ms: int = 0


@dataclass
class DurableMetrics:
    """The durable document, before it is serialised."""

    session_id: str
    recorded_at: str
    practice_language_id: str
    scenario_id: str
    turns: list[TurnMetrics] = field(default_factory=list)
    recording_id: str | None = None
    speaking_time_ms: int = 0

    def to_document(self) -> dict[str, Any]:
        """The frozen durable-metrics document."""
        return {
            "metricsVersion": "0.1",
            "sessionId": self.session_id,
            "recordedAt": self.recorded_at,
            "practiceLanguageId": self.practice_language_id,
            "scenarioId": self.scenario_id,
            "recordingId": self.recording_id,
            "turns": [_turn_document(turn) for turn in self.turns],
            "totals": {
                "turnCount": len(self.turns),
                "speakingTimeMs": int(self.speaking_time_ms),
            },
        }


def _turn_document(turn: TurnMetrics) -> dict[str, Any]:
    """One turn of the durable document."""
    return {
        "turnId": turn.turn_id,
        "roundId": turn.round_id,
        "durationMs": int(turn.duration_ms),
        "recognitionStatus": turn.recognition_status,
        "audioSourceClassification": turn.audio_source_classification,
        "observations": [
            _observation_document(observation) for observation in turn.observations
        ],
    }


def _observation_document(observation: AnalysisObservation) -> dict[str, Any]:
    """One observation of the durable document.

    The method is written only for an available observation, and the
    unavailability reason only for one that is not available: the schema
    forbids both the other way round.
    """
    metric_key = observation.metric_key
    document: dict[str, Any] = {"metricKey": metric_key}
    if observation.status == "available":
        document["method"] = observation.method
        if observation.denominator is not None:
            document["denominator"] = observation.denominator
        document["status"] = "available"
        document["value"] = observation.value
        document["unit"] = observation.unit
    else:
        document["status"] = observation.status
        document["value"] = None
        document["unit"] = None
        document["unavailabilityReason"] = observation.unavailability_reason
        if (
            observation.recognition_status is not None
            and metric_key not in _NO_RECOGNITION_STATUS
        ):
            document["recognitionStatus"] = observation.recognition_status
    return document


def validate_durable_metrics(document: Any) -> list[str]:
    """Check a durable-metrics document against the writer boundary.

    Returns the list of problems; an empty list means the document may
    be written.
    """
    problems: list[str] = []
    if not isinstance(document, dict):
        return ["the document is not an object"]

    for name in FORBIDDEN_PROPERTIES:
        if name in document:
            problems.append(f"the document carries a forbidden property: {name}")

    if document.get("metricsVersion") != "0.1":
        problems.append("metricsVersion must be 0.1")
    session_id = document.get("sessionId")
    if not isinstance(session_id, str) or not _SESSION_ID_RE.match(session_id):
        problems.append("sessionId is not a session id")
    if not isinstance(document.get("recordedAt"), str):
        problems.append("recordedAt must be a string")
    for key in ("practiceLanguageId", "scenarioId"):
        value = document.get(key)
        if not isinstance(value, str) or not _CATALOG_ID_RE.match(value):
            problems.append(f"{key} is not a catalog id")
    recording_id = document.get("recordingId")
    if recording_id is not None and (
        not isinstance(recording_id, str) or not _RECORDING_ID_RE.match(recording_id)
    ):
        problems.append("recordingId is not a recording id")

    turns = document.get("turns")
    if not isinstance(turns, list):
        problems.append("turns must be a list")
        turns = []
    total_duration = 0
    for index, turn in enumerate(turns):
        problems.extend(_validate_turn(turn, index))
        if isinstance(turn, dict) and isinstance(turn.get("durationMs"), int):
            total_duration += turn["durationMs"]

    totals = document.get("totals")
    if not isinstance(totals, dict):
        problems.append("totals must be an object")
    else:
        unknown = sorted(set(totals) - {"turnCount", "speakingTimeMs"})
        if unknown:
            problems.append(f"unknown totals keys: {unknown}")
        turn_count = totals.get("turnCount")
        speaking = totals.get("speakingTimeMs")
        if not isinstance(turn_count, int) or isinstance(turn_count, bool) or turn_count < 0:
            problems.append("turnCount must be a nonnegative integer")
        if (
            not isinstance(speaking, int)
            or isinstance(speaking, bool)
            or speaking < 0
        ):
            problems.append("speakingTimeMs must be a nonnegative integer")
        elif speaking > total_duration:
            problems.append(
                "speakingTimeMs is larger than the sum of the turn durations"
            )
        if isinstance(turn_count, int) and turn_count != len(turns):
            problems.append("turnCount does not match the number of turns")
    return problems


def _validate_turn(turn: Any, index: int) -> list[str]:
    problems: list[str] = []
    prefix = f"turn {index}"
    if not isinstance(turn, dict):
        return [f"{prefix} is not an object"]
    unknown = sorted(
        set(turn)
        - {
            "turnId",
            "roundId",
            "durationMs",
            "recognitionStatus",
            "audioSourceClassification",
            "observations",
        }
    )
    if unknown:
        problems.append(f"{prefix} carries unknown keys: {unknown}")
    turn_id = turn.get("turnId")
    if not isinstance(turn_id, str) or not _TURN_ID_RE.match(turn_id):
        problems.append(f"{prefix} has no valid turnId")
    round_id = turn.get("roundId")
    if round_id is not None and (
        not isinstance(round_id, str) or not _ROUND_ID_RE.match(round_id)
    ):
        problems.append(f"{prefix} has no valid roundId")
    duration = turn.get("durationMs")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
        problems.append(f"{prefix} has no valid durationMs")
    status = turn.get("recognitionStatus")
    if status not in RECOGNITION_STATUSES:
        problems.append(f"{prefix} has no valid recognitionStatus")
    if turn.get("audioSourceClassification") not in SOURCE_CLASSIFICATIONS:
        problems.append(f"{prefix} has no valid audioSourceClassification")
    observations = turn.get("observations")
    if not isinstance(observations, list):
        problems.append(f"{prefix} has no observations list")
        return problems
    for observation_index, observation in enumerate(observations):
        problems.extend(
            _validate_observation(
                observation,
                prefix=f"{prefix} observation {observation_index}",
                turn_status=status if isinstance(status, str) else None,
            )
        )
    return problems


def _validate_observation(
    observation: Any, *, prefix: str, turn_status: str | None
) -> list[str]:
    problems: list[str] = []
    if not isinstance(observation, dict):
        return [f"{prefix} is not an object"]
    metric_key = observation.get("metricKey")
    if metric_key not in METRIC_BINDINGS:
        problems.append(f"{prefix} has no valid metricKey")
        return problems
    method, unit, denominator = METRIC_BINDINGS[metric_key]
    unknown = sorted(
        set(observation)
        - {
            "metricKey",
            "method",
            "denominator",
            "recognitionStatus",
            "status",
            "value",
            "unit",
            "unavailabilityReason",
        }
    )
    if unknown:
        problems.append(f"{prefix} carries unknown keys: {unknown}")

    status = observation.get("status")
    if status not in OBSERVATION_STATUSES:
        problems.append(f"{prefix} has no valid status")
        return problems

    if status == "available":
        if observation.get("method") != method:
            problems.append(f"{prefix} does not use the bound method")
        if observation.get("unit") != unit:
            problems.append(f"{prefix} does not use the bound unit")
        if denominator is not None and observation.get("denominator") != denominator:
            problems.append(f"{prefix} does not use the bound denominator")
        if denominator is None and "denominator" in observation:
            problems.append(f"{prefix} may not carry a denominator")
        value = observation.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(f"{prefix} is available but carries no value")
        elif value < 0:
            problems.append(f"{prefix} carries a negative value")
        if "unavailabilityReason" in observation:
            problems.append(f"{prefix} may not carry an unavailability reason")
    else:
        if observation.get("value") is not None:
            problems.append(f"{prefix} is not available but carries a value")
        if observation.get("unit") is not None:
            problems.append(f"{prefix} is not available but carries a unit")
        if "method" in observation:
            problems.append(f"{prefix} may not claim a method")
        reason = observation.get("unavailabilityReason")
        if reason not in UNAVAILABILITY_REASONS:
            problems.append(f"{prefix} has no valid unavailability reason")
        elif status == "unavailable" and reason not in (
            "stt_unavailable",
            "speech_analysis_unavailable",
            "filler_detection_unvalidated",
        ):
            problems.append(f"{prefix} uses a reason that is not allowed when unavailable")
        elif status == "insufficient_evidence" and reason not in (
            "too_little_speech",
            "filler_detection_unvalidated",
        ):
            problems.append(
                f"{prefix} uses a reason that is not allowed when insufficient"
            )

    if metric_key in _NO_RECOGNITION_STATUS and "recognitionStatus" in observation:
        problems.append(f"{prefix} may not carry a recognition status")
    if metric_key in _NO_RECOGNITION_STATUS and "denominator" in observation:
        problems.append(f"{prefix} may not carry a denominator")

    own_status = observation.get("recognitionStatus")
    if own_status is not None:
        if own_status not in RECOGNITION_STATUSES:
            problems.append(f"{prefix} has no valid recognition status")
        elif own_status == "missing-transcription":
            if status != "unavailable" or observation.get("value") is not None:
                problems.append(
                    f"{prefix} under a missing transcription must be unavailable"
                )
        elif own_status == "no-analyzable-speech":
            if status != "insufficient_evidence" or observation.get("value") is not None:
                problems.append(
                    f"{prefix} under an unanalyzable transcript must be insufficient"
                )

    if turn_status in ("missing-transcription", "no-analyzable-speech"):
        if metric_key in ("speech.rate_wpm", "speech.active_rate_wpm", "filler.count"):
            if status == "available":
                problems.append(
                    f"{prefix} may not be available under a missing or "
                    "unanalyzable transcript"
                )
    return problems


def derive_speech_active_ms(
    observations: tuple[AnalysisObservation, ...],
    *,
    duration_ms: int,
) -> int:
    """Derive the turn's speech-active time from the measured rates.

    The two rates share one numerator (the recognised word count) and
    two different denominators, so the ratio of the rates is the ratio of
    the denominators::

        speech_active_ms = rate_wpm * duration_ms / active_rate_wpm

    It is a derivation from two measured values, not a new measurement,
    and it is clamped to the turn's own duration. When either rate is
    unavailable the speech-active time is reported as 0 — never as a
    guess.
    """
    rate = None
    active = None
    for observation in observations:
        if observation.status != "available":
            continue
        if observation.metric_key == "speech.rate_wpm":
            rate = observation.value
        elif observation.metric_key == "speech.active_rate_wpm":
            active = observation.value
    if rate is None or active is None or not active:
        return 0
    derived = rate * duration_ms / active
    bounded = int(round(derived))
    return max(0, min(bounded, max(0, duration_ms)))
