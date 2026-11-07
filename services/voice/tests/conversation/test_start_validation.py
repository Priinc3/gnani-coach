"""The start-event validation, against the frozen schemas.

The runtime validates the first message with a hand-written mirror of the
frozen ``event-envelope`` v0.1 schema and the frozen ``session-settings``
v0.1 shape, because the JSON Schema package is a **development**
dependency and a production install must not need it.

Two schemas, two layers
-----------------------

The frozen ``event-envelope`` schema pins the start payload's *settings*
object loosely: it fixes the required key set and lets unknown keys
through (``"additionalProperties": true``), and it says in so many words
that ``packages/contracts/schemas/session-settings.schema.json`` is
authoritative. So the mirror is checked against each schema at the layer
that schema owns:

* envelope-level rules (version, direction, type, ids, sequence,
  ``emittedAt``, the payload keys, the audio block) against
  ``event-envelope.schema.json``;
* settings-level rules (the level, the round size, the session limit, the
  consent, the custom topic) against ``session-settings.schema.json``.

One rule is **stricter than the schema on purpose**: the G1 runtime
accepts 16 kHz mono s16le only (ADDENDUM section D), while the frozen
envelope schema allows four rates. That difference is asserted, not
hidden.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from gnani_coach.conversation.validation import (
    InvalidStart,
    validate_start_envelope,
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "packages" / "contracts" / "schemas").is_dir():
            return candidate
    raise RuntimeError("repository root not found")


def _schema_validator(stem: str) -> Draft202012Validator:
    schema = json.loads(
        (_repo_root() / "packages" / "contracts" / "schemas" / f"{stem}.schema.json").read_text(
            encoding="utf-8"
        )
    )
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _accepts(document: Any) -> bool:
    """Whether the runtime's own validator accepts the document."""
    try:
        validate_start_envelope(document)
    except InvalidStart:
        return False
    return True


def _schema_accepts(document: Any) -> bool:
    validator = _schema_validator("event-envelope")
    return not list(validator.iter_errors(document))


def _settings_schema_accepts(settings: Any) -> bool:
    validator = _schema_validator("session-settings")
    return not list(validator.iter_errors(settings))


def _valid_start() -> dict[str, Any]:
    path = (
        _repo_root()
        / "packages"
        / "contracts"
        / "examples"
        / "event-envelope"
        / "valid"
        / "client-start-event.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_contract_fixture_is_accepted() -> None:
    """The contract's own valid start event passes the runtime."""
    document = _valid_start()
    assert _schema_accepts(document)
    assert _settings_schema_accepts(document["payload"]["settings"])
    assert _accepts(document)


def test_the_contract_invalid_fixtures_are_rejected() -> None:
    """Every invalid fixture is refused by the runtime as well."""
    folder = (
        _repo_root()
        / "packages"
        / "contracts"
        / "examples"
        / "event-envelope"
        / "invalid"
    )
    checked = 0
    for path in sorted(folder.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert not _schema_accepts(document), path.name
        assert not _accepts(document), path.name
        checked += 1
    assert checked >= 5


def _envelope_mutations() -> list[tuple[str, dict[str, Any]]]:
    """Broken start events, at the layer the envelope schema owns."""
    cases: list[tuple[str, dict[str, Any]]] = []

    def broken(name: str, mutate) -> None:
        document = _valid_start()
        mutate(document)
        cases.append((name, document))

    broken("a wrong envelope version", lambda d: d.update(envelopeVersion="0.2"))
    broken("a wrong direction", lambda d: d.update(direction="server_to_client"))
    broken("a wrong type", lambda d: d.update(type="status"))
    broken("an unknown envelope key", lambda d: d.update(unexpected=1))
    broken("a negative sequence", lambda d: d.update(sequence=-1))
    broken("a bad emittedAt", lambda d: d.update(emittedAt="2026-10-20 09:00:00"))
    broken("an emittedAt without an offset", lambda d: d.update(emittedAt="2026-10-20T09:00:00"))
    broken(
        "an unknown payload key",
        lambda d: d["payload"].update(credentials={"gnaniApiKey": "never"}),
    )
    broken("two channels", lambda d: d["payload"]["audio"].update(channels=2))
    broken(
        "a wrong sample format",
        lambda d: d["payload"]["audio"].update(sampleFormat="float32"),
    )
    broken(
        "a bad session id",
        lambda d: d.update(sessionId="session_1"),
    )
    broken(
        "a missing audio block",
        lambda d: d["payload"].pop("audio"),
    )
    broken(
        "an empty token",
        lambda d: d["payload"].update(auth={"token": ""}),
    )
    broken(
        "a token that is not a string",
        lambda d: d["payload"].update(auth={"token": 17}),
    )
    return cases


@pytest.mark.parametrize(
    "name,document",
    _envelope_mutations(),
    ids=[case[0] for case in _envelope_mutations()],
)
def test_the_envelope_mirror_agrees_with_the_schema(
    name: str, document: dict[str, Any]
) -> None:
    """A broken envelope is refused by the schema and by the mirror."""
    assert not _schema_accepts(document), f"{name}: the schema accepted it"
    assert not _accepts(document), f"{name}: the runtime accepted it"


def _settings_mutations() -> list[tuple[str, dict[str, Any]]]:
    """Broken settings, at the layer the session-settings schema owns."""
    cases: list[tuple[str, dict[str, Any]]] = []

    def broken(name: str, mutate) -> None:
        document = _valid_start()
        mutate(document["payload"]["settings"])
        cases.append((name, document))

    broken("a wrong settings version", lambda s: s.update(settingsVersion="0.2"))
    broken("an unknown settings key", lambda s: s.update(unexpected=True))
    broken("a bad language id", lambda s: s.update(practiceLanguageId="English"))
    broken("a bad level", lambda s: s.update(level="expert"))
    broken("too many round turns", lambda s: s.update(coachingRoundTurns=9))
    broken("a session limit over ten minutes", lambda s: s.update(sessionLimitSeconds=601))
    broken("a session limit under a minute", lambda s: s.update(sessionLimitSeconds=59))
    broken(
        "retention without consent",
        lambda s: (
            s.update(recordingRetention=True),
            s["consent"].update(recordingRetentionGranted=False),
        ),
    )
    broken(
        "consent without a moment",
        lambda s: s["consent"].update(
            recordingRetentionGranted=True, recordingRetentionGrantedAt=None
        ),
    )
    broken(
        "a moment without consent",
        lambda s: s["consent"].update(
            recordingRetentionGranted=False,
            recordingRetentionGrantedAt="2026-10-20T09:00:00Z",
        ),
    )
    broken("a wrong consent version", lambda s: s["consent"].update(consentVersion="0.2"))
    broken(
        "a custom topic in the wrong scenario",
        lambda s: s.update(customTopic={"text": "a topic", "persisted": False}),
    )
    broken(
        "a persisted custom topic",
        lambda s: (
            s.update(scenarioId="custom"),
            s.update(customTopic={"text": "a topic", "persisted": True}),
        ),
    )
    broken(
        "the custom scenario without a topic",
        lambda s: s.update(scenarioId="custom"),
    )
    return cases


@pytest.mark.parametrize(
    "name,document",
    _settings_mutations(),
    ids=[case[0] for case in _settings_mutations()],
)
def test_the_settings_mirror_agrees_with_the_schema(
    name: str, document: dict[str, Any]
) -> None:
    """Broken settings are refused by the settings schema and the mirror."""
    settings = document["payload"]["settings"]
    assert not _settings_schema_accepts(settings), f"{name}: the schema accepted it"
    assert not _accepts(document), f"{name}: the runtime accepted it"


def test_the_envelope_schema_leaves_the_settings_to_their_own_schema() -> None:
    """Why the two layers are checked separately.

    The frozen envelope schema accepts an unknown settings key and a
    broken consent pair, because the settings shape is owned by
    ``session-settings.schema.json``. The runtime follows the settings
    schema, not the looser envelope rule.
    """
    document = _valid_start()
    document["payload"]["settings"]["unexpected"] = True
    assert _schema_accepts(document)
    assert not _accepts(document)


def test_only_sixteen_kilohertz_is_accepted() -> None:
    """The runtime is stricter than the schema on purpose.

    The frozen envelope schema allows 8/16/44.1/48 kHz; the G1 runtime
    accepts 16 kHz only (ADDENDUM section D).
    """
    document = _valid_start()
    document["payload"]["audio"]["sampleRateHz"] = 44100
    assert _schema_accepts(document)
    with pytest.raises(InvalidStart) as refused:
        validate_start_envelope(document)
    assert refused.value.code == "unsupported_audio_format"


def test_a_valid_start_event_with_a_custom_topic_is_accepted() -> None:
    """The custom scenario carries its topic, and it is never persisted."""
    document = _valid_start()
    document["payload"]["settings"]["scenarioId"] = "custom"
    document["payload"]["settings"]["customTopic"] = {
        "text": "a practice topic",
        "persisted": False,
    }
    assert _schema_accepts(document)
    assert _settings_schema_accepts(document["payload"]["settings"])
    request = validate_start_envelope(document)
    assert request.custom_topic == "a practice topic"


def test_a_missing_custom_topic_is_refused() -> None:
    """The custom scenario needs its topic."""
    document = _valid_start()
    document["payload"]["settings"]["scenarioId"] = "custom"
    assert not _accepts(document)


def test_the_token_is_read_from_the_first_message() -> None:
    """The caller's own token travels in the body, never in the URL."""
    document = _valid_start()
    document["payload"]["auth"] = {"token": "a-short-lived-token"}
    request = validate_start_envelope(document)
    assert request.token == "a-short-lived-token"


def test_a_guest_start_event_carries_no_token() -> None:
    """A guest call is a start event without an auth block."""
    document = _valid_start()
    assert "auth" not in document["payload"]
    request = validate_start_envelope(document)
    assert request.token is None


def test_the_call_cap_is_the_shorter_of_the_two_limits() -> None:
    """The client's own limit may be shorter than the product cap."""
    document = _valid_start()
    document["payload"]["settings"]["sessionLimitSeconds"] = 120
    request = validate_start_envelope(document)
    assert request.call_cap_seconds == 120
    document["payload"]["settings"]["sessionLimitSeconds"] = 600
    request = validate_start_envelope(document)
    assert request.call_cap_seconds == 600
