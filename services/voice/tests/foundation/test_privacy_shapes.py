"""Privacy shapes — content must not slip into the wrong places.

These are explicit, named assertions on top of the folder-based parity tests:
they document *why* each rejection exists, so a future schema change cannot
silently reopen the hole. Coverage mirrors the new FIX-1 cases:

- ``method`` in durable metrics is a controlled identifier, so a learner
  transcript sentence or a model feedback sentence in that (formerly
  free-text) field is rejected.
- Metric values are nonnegative, counts and millisecond quantities are
  integers, and every metric key is coupled to exactly one unit.
"""

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(contracts_dir: Path, stem: str) -> Draft202012Validator:
    schema = _load(contracts_dir / "schemas" / f"{stem}.schema.json")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_durable_metrics_reject_every_content_bearing_field(contracts_dir: Path) -> None:
    base = _load(contracts_dir / "examples" / "durable-metrics" / "valid" / "numeric-only.json")
    validator = _validator(contracts_dir, "durable-metrics")
    injections = {
        "transcript": "hello and welcome",
        "quotedMistakes": ["I am go to office"],
        "modelText": "You did well!",
        "audioUrl": "https://storage.example/recording.wav",
        "embedding": [0.1, 0.2],
    }
    for field, value in injections.items():
        document = {**base, field: value}
        assert list(validator.iter_errors(document)), f"{field} must be rejected in durable metrics"


def test_durable_method_rejects_prose_and_accepts_controlled_identifiers(
    contracts_dir: Path,
) -> None:
    """F02: `method` was any 1-120 char string, so transcript/model text could
    occupy it while satisfying every constraint. It is now a closed identifier
    set; a learner sentence and a model feedback sentence must both fail, and
    a controlled identifier must pass.
    """
    validator = _validator(contracts_dir, "durable-metrics")
    base = _load(contracts_dir / "examples" / "durable-metrics" / "valid" / "numeric-only.json")
    observation = base["turns"][0]["observations"][0]
    prose_in_method = {
        "learner transcript sentence": "I said I will go to the office tomorrow",
        "model feedback sentence": "Great job overall — your pauses were well placed this time.",
        "empty string": "",
    }
    for label, prose in prose_in_method.items():
        document = copy.deepcopy(base)
        document["turns"][0]["observations"][0] = {**observation, "method": prose}
        errors = list(validator.iter_errors(document))
        assert errors, f"method must reject {label}"
    controlled = copy.deepcopy(base)
    controlled["turns"][0]["observations"][0] = {
        **observation,
        "method": "vad_speech_regions",
    }
    assert list(validator.iter_errors(controlled)) == [], (
        "a controlled method identifier must validate"
    )
    reason_document = copy.deepcopy(base)
    reason_document["turns"][0]["observations"][0] = {
        "metricKey": "speech.rate_wpm",
        "unavailabilityReason": "stt_unavailable",
        "status": "unavailable",
        "value": None,
        "unit": None,
    }
    assert list(validator.iter_errors(reason_document)) == [], (
        "closed reason codes must validate for unavailable metrics"
    )


def test_metric_domains_and_units_are_enforced(contracts_dir: Path) -> None:
    """F03: nonnegative domains, integer counts/ms quantities, and one unit per
    metric key — while keeping valid zero, fractional rates and unavailable nulls.
    """
    durable = _validator(contracts_dir, "durable-metrics")
    base = _load(contracts_dir / "examples" / "durable-metrics" / "valid" / "numeric-only.json")

    def durable_doc(observation: dict) -> dict:
        document = copy.deepcopy(base)
        document["turns"][0]["observations"] = [observation]
        return document

    must_reject = [
        ("negative count", {
            "metricKey": "pause.count", "method": "vad_speech_regions",
            "status": "available", "value": -1, "unit": "count",
        }),
        ("fractional count", {
            "metricKey": "filler.count", "method": "disfluency_recognition",
            "status": "available", "value": 2.5, "unit": "count",
        }),
        ("negative duration", {
            "metricKey": "pause.longest_ms", "method": "vad_speech_regions",
            "status": "available", "value": -250, "unit": "milliseconds",
        }),
        ("mismatched unit (count metric as wpm)", {
            "metricKey": "pause.count", "method": "vad_speech_regions",
            "status": "available", "value": 3, "unit": "words_per_minute",
        }),
        ("mismatched unit (duration as count)", {
            "metricKey": "pause.longest_ms", "method": "vad_speech_regions",
            "status": "available", "value": 1200, "unit": "count",
        }),
    ]
    for label, observation in must_reject:
        assert list(durable.iter_errors(durable_doc(observation))), (
            f"durable metrics must reject: {label}"
        )

    must_accept = [
        ("valid zero", {
            "metricKey": "filler.count", "method": "disfluency_recognition",
            "status": "available", "value": 0, "unit": "count",
        }),
        ("valid fractional rate", {
            "metricKey": "speech.rate_wpm", "method": "stt_words_over_speech_regions",
            "status": "available", "value": 112.4, "unit": "words_per_minute",
        }),
        ("unavailable null", {
            "metricKey": "speech.rate_wpm", "unavailabilityReason": "stt_unavailable",
            "status": "unavailable", "value": None, "unit": None,
        }),
    ]
    for label, observation in must_accept:
        assert list(durable.iter_errors(durable_doc(observation))) == [], (
            f"durable metrics must accept: {label}"
        )

    transient = _validator(contracts_dir, "analysis-observation")
    valid_observation = _load(
        contracts_dir / "examples" / "analysis-observation" / "valid" / "measured-fractional-rate.json"
    )

    def transient_doc(**overrides: Any) -> dict:
        document = copy.deepcopy(valid_observation)
        document.update(overrides)
        return document

    for label, overrides in [
        ("negative value", {"metricKey": "pause.longest_ms", "value": -250, "unit": "milliseconds"}),
        ("fractional count", {"metricKey": "pause.count", "value": 2.5, "unit": "count"}),
        ("mismatched unit", {"metricKey": "filler.count", "value": 1, "unit": "milliseconds"}),
    ]:
        assert list(transient.iter_errors(transient_doc(**overrides))), (
            f"analysis observation must reject: {label}"
        )
    for label, overrides in [
        ("valid zero", {"metricKey": "filler.count", "value": 0, "unit": "count"}),
        ("valid fractional rate", {"metricKey": "speech.rate_wpm", "value": 112.4, "unit": "words_per_minute"}),
    ]:
        assert list(transient.iter_errors(transient_doc(**overrides))) == [], (
            f"analysis observation must accept: {label}"
        )


def test_transient_observation_keeps_unavailable_distinct_from_zero(contracts_dir: Path) -> None:
    validator = _validator(contracts_dir, "analysis-observation")
    available_zero = {
        "observationVersion": "0.1",
        "metricKey": "filler.count",
        "source": "measured",
        "status": "available",
        "value": 0,
        "unit": "count",
        "evidenceSpan": None,
        "reliability": {"level": "low", "limitations": []},
        "roundId": None,
        "turnId": None,
        "observedAt": "2026-10-16T09:31:10Z",
    }
    assert list(validator.iter_errors(available_zero)) == []
    unavailable_with_zero = {**available_zero, "status": "unavailable"}
    assert list(validator.iter_errors(unavailable_with_zero)), (
        "unavailable must not carry a numeric value such as 0"
    )


def test_event_envelope_rejects_base64_audio(contracts_dir: Path) -> None:
    validator = _validator(contracts_dir, "event-envelope")
    base = _load(contracts_dir / "examples" / "event-envelope" / "valid" / "text-event.json")
    document = copy.deepcopy(base)
    document["payload"]["audioBase64"] = "UklGRg=="
    assert list(validator.iter_errors(document))
    # Binary audio travels as its own frame type with a metadata-only descriptor.
    frame = _load(
        contracts_dir / "examples" / "event-envelope" / "valid" / "audio-frame-descriptor.json"
    )
    assert list(validator.iter_errors(frame)) == []
    assert "audioBytes" not in frame["payload"]


def test_recording_metadata_is_a_private_reference_only(contracts_dir: Path) -> None:
    validator = _validator(contracts_dir, "recording-metadata")
    base = _load(contracts_dir / "examples" / "recording-metadata" / "valid" / "retained.json")
    assert list(validator.iter_errors(base)) == []
    rejected_url_fields = {
        "publicUrl": "https://cdn.example/recording.wav",
        "signedUrl": "https://cdn.example/recording.wav?sig=1",
        "objectKey": "recordings/2026/recording.wav",
    }
    for field, value in rejected_url_fields.items():
        document = {**base, field: value}
        assert list(validator.iter_errors(document)), f"{field} must be rejected"
    deleted_without_timestamp = copy.deepcopy(base)
    deleted_without_timestamp["lifecycle"]["state"] = "deleted"
    assert list(validator.iter_errors(deleted_without_timestamp)), (
        "deleted state requires a deletedAt timestamp"
    )


def test_session_settings_consent_boundary(contracts_dir: Path) -> None:
    validator = _validator(contracts_dir, "session-settings")
    base = _load(
        contracts_dir / "examples" / "session-settings" / "valid" / "default-recording-off.json"
    )
    assert list(validator.iter_errors(base)) == []
    retention_without_grant = copy.deepcopy(base)
    retention_without_grant["recordingRetention"] = True
    assert list(validator.iter_errors(retention_without_grant)), (
        "recording retention requires an explicit consent grant"
    )


def test_error_shape_rejects_private_failure_details(contracts_dir: Path) -> None:
    validator = _validator(contracts_dir, "error-shape")
    base = _load(
        contracts_dir / "examples" / "error-shape" / "valid" / "provider-unavailable-retryable.json"
    )
    assert list(validator.iter_errors(base)) == []
    rejected_fields = {
        "stack": "Traceback (most recent call last): ...",
        "rawTranscript": "hello I wanted to ask about the bus",
        "rawProviderResponse": {"internal": "provider dump"},
        "secret": "sk_live_example",
    }
    for field, value in rejected_fields.items():
        document = {**base, field: value}
        assert list(validator.iter_errors(document)), f"{field} must be rejected in error payloads"
