"""Privacy shapes — content must not slip into the wrong places.

These are explicit, named assertions on top of the folder-based parity tests:
they document *why* each rejection exists, so a future schema change cannot
silently reopen the hole.
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
