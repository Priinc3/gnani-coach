"""The metrics-only guard: what may be written into a durable record.

The durable-metrics contract (``packages/contracts/schemas/
durable-metrics.schema.json``) is the boundary, and the schema check has
already run before a document reaches a store. The guard here is the
**second** line, inside the store itself, and it exists because the
schema is not the only writer: a future caller could hand a store a
document that never went through the schema.

The rule the guard enforces is simple and strict:

* a **content key** anywhere in the document is refused — a transcript, a
  quoted mistake, model text, an audio URL, an embedding, a custom topic,
  or any of the forbidden recording-metadata keys;
* every **string** in the document must be a controlled identifier: an
  opaque id, a catalog id, a version, a timestamp, or one of the closed
  enumerations of the schema. Free text has no place in a durable record,
  so a string that is not recognisable as an identifier is refused;
* numbers, booleans and ``null`` are always allowed.

The result is a store that can only ever hold numbers and ids, which is
what "metrics-only" means. The refusal is loud
(:class:`~gnani_coach.persistence.errors.ContentRejectedError`), because a
silent drop of a session would be worse.
"""

from __future__ import annotations

import re
from typing import Any

from gnani_coach.persistence.errors import ContentRejectedError

#: The keys that may never appear in a durable record.
#:
#: The first group is the set the durable-metrics schema refuses by name;
#: the second group is the set the recording-metadata schema refuses. A
#: stored URL becomes a shareable capability, which is why it is on the
#: list.
CONTENT_KEYS: frozenset[str] = frozenset(
    {
        "transcript",
        "quotedmistakes",
        "modeltext",
        "audiourl",
        "embedding",
        "customtopic",
        "publicurl",
        "signedurl",
        "url",
        "objectkey",
        "audio",
        "text",
        "content",
        "modeloutput",
        "coachtext",
        "prompt",
        "completion",
    }
)

#: The opaque id shapes the contract uses.
_ID_PATTERN = re.compile(r"^(ses|trn|rnd|rec|usr)_[a-z0-9]{6,40}$")

#: A stable catalog id (a language, a scenario).
_CATALOG_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")

#: A version string.
_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")

#: An RFC 3339 timestamp.
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

#: The closed enumerations of the durable-metrics schema.
ALLOWED_VALUES: frozenset[str] = frozenset(
    {
        # metric keys
        "pause.longest_ms",
        "pause.count",
        "filler.count",
        "speech.rate_wpm",
        "speech.active_rate_wpm",
        "turn.duration_ms",
        # method identifiers
        "vad_speech_regions",
        "stt_words_over_learner_span",
        "stt_words_over_learner_span_legacy",
        "stt_words_over_speech_regions",
        "stt_words_over_speech_active",
        "disfluency_recognition",
        "learner_audio_sample_clock",
        # denominators
        "learner_span_ms",
        "speech_active_ms",
        # recognition statuses
        "measured",
        "no-analyzable-speech",
        "missing-transcription",
        # audio source classifications
        "learner-audio",
        "synthetic-learner-audio",
        # observation statuses
        "available",
        "unavailable",
        "insufficient_evidence",
        # unavailability reasons
        "stt_unavailable",
        "speech_analysis_unavailable",
        "too_little_speech",
        "filler_detection_unvalidated",
        # units
        "milliseconds",
        "count",
        "words_per_minute",
        # versions
        "0.1",
    }
)


def _is_controlled_string(value: str) -> bool:
    """Whether a string is a controlled identifier rather than content."""
    if value in ALLOWED_VALUES:
        return True
    if _ID_PATTERN.match(value):
        return True
    if _CATALOG_ID_PATTERN.match(value):
        return True
    if _VERSION_PATTERN.match(value):
        return True
    return bool(_TIMESTAMP_PATTERN.match(value))


def assert_metrics_only(document: Any, *, path: str = "$") -> None:
    """Refuse a document that carries anything but numbers and ids.

    Raises :class:`~gnani_coach.persistence.errors.ContentRejectedError`
    with the **path** of the offending key — never the value, because the
    value may be the learner's own words.
    """
    if not isinstance(document, dict):
        raise ContentRejectedError(
            f"a durable record must be an object, got {type(document).__name__}"
        )

    for key, value in document.items():
        if not isinstance(key, str):
            raise ContentRejectedError(f"{path}: a key must be a string")
        normalized = key.strip().lower()
        if normalized in CONTENT_KEYS:
            raise ContentRejectedError(
                f"{path}.{key}: a durable record may not carry this key"
            )
        _assert_value(value, path=f"{path}.{key}")


def _assert_value(value: Any, *, path: str) -> None:
    """Recursively check one value of a durable record."""
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        return
    if isinstance(value, str):
        if not _is_controlled_string(value):
            raise ContentRejectedError(
                f"{path}: a durable record may only carry controlled identifiers"
            )
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ContentRejectedError(f"{path}: a key must be a string")
            normalized = key.strip().lower()
            if normalized in CONTENT_KEYS:
                raise ContentRejectedError(
                    f"{path}.{key}: a durable record may not carry this key"
                )
            _assert_value(nested, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_value(nested, path=f"{path}[{index}]")
        return
    raise ContentRejectedError(
        f"{path}: a durable record may not carry a {type(value).__name__}"
    )
