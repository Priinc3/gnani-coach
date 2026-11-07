"""Validation of the client's first message.

The first event of every call is a ``start`` event, and it is validated
against the **frozen** ``event-envelope`` v0.1 schema and the frozen
``session-settings`` v0.1 shape.

Why the validation is written by hand
-------------------------------------

The JSON Schema files live in ``packages/contracts/schemas/`` and the
``jsonschema`` package is a **development** dependency of this service
(it is not in ``[project.dependencies]``, and the manifests are locked).
The runtime therefore cannot import it: a production install would fail
to start. So the rules are mirrored here, and
``services/voice/tests/conversation/test_start_validation.py`` proves the
mirror agrees with the real schema by running both over the contract's
own valid/invalid fixtures.

Every rule below is a rule of the frozen schema, not a choice of this
phase. The one *product* rule on top of them is the G1 audio rule: only
16 kHz mono s16le is accepted (ADDENDUM §D).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

#: The frozen catalog-id shape.
CATALOG_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")

#: The frozen id shapes.
SESSION_ID_RE = re.compile(r"^ses_[a-z0-9]{6,40}$")
CONNECTION_ID_RE = re.compile(r"^con_[a-z0-9]{6,40}$")
ROUND_ID_RE = re.compile(r"^rnd_[a-z0-9]{6,40}$")
TURN_ID_RE = re.compile(r"^trn_[a-z0-9]{6,40}$")

#: The RFC 3339 ``date-time`` shape the frozen schemas require.
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)

#: The accepted sample rates of the frozen envelope schema.
SCHEMA_SAMPLE_RATES = (8000, 16000, 44100, 48000)

#: The levels of the frozen session-settings shape.
LEVELS = ("beginner", "intermediate", "advanced")

#: The keys the frozen ``start`` payload's settings object must carry.
REQUIRED_SETTINGS_KEYS = (
    "settingsVersion",
    "practiceLanguageId",
    "coachingLanguageId",
    "scenarioId",
    "level",
    "coachingRoundTurns",
    "sessionLimitSeconds",
    "recordingRetention",
    "consent",
)

#: The keys the frozen session-settings shape allows.
ALLOWED_SETTINGS_KEYS = frozenset(REQUIRED_SETTINGS_KEYS) | {"scenarioPresetId", "customTopic"}

#: The keys of the frozen envelope itself.
ENVELOPE_KEYS = frozenset(
    {
        "envelopeVersion",
        "direction",
        "type",
        "sessionId",
        "connectionId",
        "roundId",
        "turnId",
        "sequence",
        "sampleTimeMs",
        "emittedAt",
        "payload",
    }
)


class InvalidStart(ValueError):
    """The first message was not a valid ``start`` event.

    ``code`` is the stable machine identifier of the failure; it is what
    the error envelope carries. ``retryable`` is false for every start
    failure: the same message will fail the same way.
    """

    def __init__(self, reason: str, *, code: str = "invalid_start") -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class StartRequest:
    """The validated contents of a ``start`` event.

    ``custom_topic`` is **transient**: it is a learner-written topic that
    is used in the prompt and never written to metrics, logs or caches.
    """

    sample_rate_hz: int
    practice_language_id: str
    coaching_language_id: str
    scenario_id: str
    scenario_preset_id: str | None
    level: str
    coaching_round_turns: int
    session_limit_seconds: int
    recording_retention: bool
    consent_version: str
    recording_retention_granted: bool
    recording_retention_granted_at: str | None
    token: str | None
    custom_topic: str | None

    @property
    def call_cap_seconds(self) -> int:
        """The wall-clock cap for this call.

        The product cap is 600 s and the client's own
        ``sessionLimitSeconds`` may ask for less; the shorter of the two
        wins.
        """
        from gnani_coach.conversation.config import MAX_SESSION_LIMIT_SECONDS

        return min(self.session_limit_seconds, MAX_SESSION_LIMIT_SECONDS)


def validate_start_envelope(document: Any) -> StartRequest:
    """Validate one client message as a ``start`` event.

    Raises :class:`InvalidStart` with a stable code when the message is
    not a valid start. The checks mirror
    ``packages/contracts/schemas/event-envelope.schema.json`` (the
    ``start`` payload) and
    ``packages/contracts/schemas/session-settings.schema.json``.
    """
    if not isinstance(document, dict):
        raise InvalidStart("the first message must be a JSON object")

    unknown = sorted(set(document) - ENVELOPE_KEYS)
    if unknown:
        raise InvalidStart(f"unknown envelope keys: {unknown}")
    if document.get("envelopeVersion") != "0.1":
        raise InvalidStart("envelopeVersion must be 0.1")
    if document.get("direction") != "client_to_server":
        raise InvalidStart("a client event must have direction client_to_server")
    if document.get("type") != "start":
        raise InvalidStart("the first event of a call must be a start event")

    for key, pattern in (
        ("sessionId", SESSION_ID_RE),
        ("connectionId", CONNECTION_ID_RE),
        ("roundId", ROUND_ID_RE),
        ("turnId", TURN_ID_RE),
    ):
        value = document.get(key)
        if value is not None and (
            not isinstance(value, str) or not pattern.match(value)
        ):
            raise InvalidStart(f"{key} is not a valid identifier")

    sequence = document.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise InvalidStart("sequence must be a nonnegative integer")

    sample_time = document.get("sampleTimeMs")
    if sample_time is not None and (
        not isinstance(sample_time, int)
        or isinstance(sample_time, bool)
        or sample_time < 0
    ):
        raise InvalidStart("sampleTimeMs must be null or a nonnegative integer")

    if not isinstance(document.get("emittedAt"), str):
        raise InvalidStart("emittedAt must be a string")
    _require_iso_datetime(document["emittedAt"], "emittedAt")

    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise InvalidStart("payload must be an object")
    return _validate_start_payload(payload)


def _validate_start_payload(payload: dict[str, Any]) -> StartRequest:
    unknown = sorted(set(payload) - {"audio", "settings", "auth"})
    if unknown:
        raise InvalidStart(f"unknown start payload keys: {unknown}")

    audio = payload.get("audio")
    if not isinstance(audio, dict):
        raise InvalidStart("the start event must declare the audio format")
    unknown_audio = sorted(set(audio) - {"sampleRateHz", "channels", "sampleFormat"})
    if unknown_audio:
        raise InvalidStart(f"unknown audio keys: {unknown_audio}")
    rate = audio.get("sampleRateHz")
    if rate not in SCHEMA_SAMPLE_RATES:
        raise InvalidStart(
            "sampleRateHz must be one of the documented rates",
            code="unsupported_audio_format",
        )
    if audio.get("channels") != 1:
        raise InvalidStart(
            "only mono audio is accepted",
            code="unsupported_audio_format",
        )
    if audio.get("sampleFormat") != "s16le":
        raise InvalidStart(
            "only signed 16-bit little-endian PCM is accepted",
            code="unsupported_audio_format",
        )
    # The G1 runtime accepts one rate only (ADDENDUM section D).
    from gnani_coach.conversation.config import ACCEPTED_SAMPLE_RATE_HZ

    if rate != ACCEPTED_SAMPLE_RATE_HZ:
        raise InvalidStart(
            f"this service accepts {ACCEPTED_SAMPLE_RATE_HZ} Hz audio only",
            code="unsupported_audio_format",
        )

    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise InvalidStart("the start event must declare the session settings")
    checked = _validate_settings(settings)

    token: str | None = None
    auth = payload.get("auth")
    if auth is not None:
        if not isinstance(auth, dict):
            raise InvalidStart("auth must be an object")
        unknown_auth = sorted(set(auth) - {"token"})
        if unknown_auth:
            raise InvalidStart(f"unknown auth keys: {unknown_auth}")
        raw_token = auth.get("token")
        if not isinstance(raw_token, str) or not 1 <= len(raw_token) <= 4096:
            raise InvalidStart("the access token must be a non-empty string")
        token = raw_token

    return StartRequest(
        sample_rate_hz=int(rate),
        practice_language_id=checked["practiceLanguageId"],
        coaching_language_id=checked["coachingLanguageId"],
        scenario_id=checked["scenarioId"],
        scenario_preset_id=checked.get("scenarioPresetId"),
        level=checked["level"],
        coaching_round_turns=checked["coachingRoundTurns"],
        session_limit_seconds=checked["sessionLimitSeconds"],
        recording_retention=checked["recordingRetention"],
        consent_version=checked["consent"]["consentVersion"],
        recording_retention_granted=checked["consent"]["recordingRetentionGranted"],
        recording_retention_granted_at=checked["consent"]["recordingRetentionGrantedAt"],
        token=token,
        custom_topic=checked.get("customTopic", {}).get("text")
        if isinstance(checked.get("customTopic"), dict)
        else None,
    )


def _validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Validate the frozen session-settings shape."""
    missing = [key for key in REQUIRED_SETTINGS_KEYS if key not in settings]
    if missing:
        raise InvalidStart(f"the session settings are missing: {missing}")
    unknown = sorted(set(settings) - ALLOWED_SETTINGS_KEYS)
    if unknown:
        raise InvalidStart(f"unknown session settings keys: {unknown}")

    if settings["settingsVersion"] != "0.1":
        raise InvalidStart("settingsVersion must be 0.1")
    for key in ("practiceLanguageId", "coachingLanguageId", "scenarioId"):
        value = settings[key]
        if not isinstance(value, str) or not CATALOG_ID_RE.match(value):
            raise InvalidStart(f"{key} is not a catalog id")
    preset = settings.get("scenarioPresetId")
    if preset is not None and (
        not isinstance(preset, str) or not CATALOG_ID_RE.match(preset)
    ):
        raise InvalidStart("scenarioPresetId is not a catalog id")
    if settings["level"] not in LEVELS:
        raise InvalidStart("level is not one of beginner, intermediate, advanced")
    rounds = settings["coachingRoundTurns"]
    if (
        not isinstance(rounds, int)
        or isinstance(rounds, bool)
        or not 1 <= rounds <= 8
    ):
        raise InvalidStart("coachingRoundTurns must be an integer within 1-8")
    limit = settings["sessionLimitSeconds"]
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 60 <= limit <= 600
    ):
        raise InvalidStart("sessionLimitSeconds must be an integer within 60-600")
    if not isinstance(settings["recordingRetention"], bool):
        raise InvalidStart("recordingRetention must be a boolean")

    consent = settings["consent"]
    if not isinstance(consent, dict):
        raise InvalidStart("consent must be an object")
    unknown_consent = sorted(
        set(consent)
        - {"consentVersion", "recordingRetentionGranted", "recordingRetentionGrantedAt"}
    )
    if unknown_consent:
        raise InvalidStart(f"unknown consent keys: {unknown_consent}")
    if consent.get("consentVersion") != "0.1":
        raise InvalidStart("consentVersion must be 0.1")
    if not isinstance(consent.get("recordingRetentionGranted"), bool):
        raise InvalidStart("recordingRetentionGranted must be a boolean")
    granted_at = consent.get("recordingRetentionGrantedAt")
    if granted_at is not None:
        _require_iso_datetime(granted_at, "recordingRetentionGrantedAt")
    if settings["recordingRetention"] and not consent["recordingRetentionGranted"]:
        raise InvalidStart(
            "recording retention needs the recording-retention consent"
        )
    if consent["recordingRetentionGranted"] and granted_at is None:
        raise InvalidStart(
            "a granted recording-retention consent needs the moment it was granted"
        )
    if not consent["recordingRetentionGranted"] and granted_at is not None:
        raise InvalidStart(
            "recordingRetentionGrantedAt must be null when no consent was granted"
        )

    custom_topic = settings.get("customTopic")
    if settings["scenarioId"] == "custom":
        if not isinstance(custom_topic, dict):
            raise InvalidStart("the custom scenario needs a custom topic")
        unknown_topic = sorted(set(custom_topic) - {"text", "persisted"})
        if unknown_topic:
            raise InvalidStart(f"unknown custom topic keys: {unknown_topic}")
        text = custom_topic.get("text")
        if not isinstance(text, str) or not 1 <= len(text) <= 200:
            raise InvalidStart("the custom topic text must be 1-200 characters")
        if custom_topic.get("persisted") is not False:
            raise InvalidStart("a custom topic is never persisted")
    elif custom_topic is not None:
        raise InvalidStart("a custom topic is only allowed with the custom scenario")

    return settings


def _require_iso_datetime(value: Any, field_name: str) -> None:
    """Accept an RFC 3339 date-time, as the frozen schemas do.

    The frozen schemas use the JSON Schema ``date-time`` format, which is
    RFC 3339: the date and the time are separated by ``T`` and a UTC
    offset is mandatory. Python's ``datetime.fromisoformat`` is more
    forgiving than that (it accepts a space separator and a missing
    offset), so the shape is checked here first and only then parsed.
    """
    if not isinstance(value, str):
        raise InvalidStart(f"{field_name} must be a date-time string")
    if not RFC3339_RE.match(value):
        raise InvalidStart(f"{field_name} must be an RFC 3339 date-time")
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise InvalidStart(f"{field_name} must be an RFC 3339 date-time") from exc
