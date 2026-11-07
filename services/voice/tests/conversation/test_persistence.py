"""What is written at the end of a call, and what is never written.

The rules:

* a **guest** writes nothing;
* an authenticated caller gets the durable metrics — numbers and ids
  only;
* the audio is written only when the consent was granted **and** is
  still granted at write time;
* a withdrawal between the ``start`` event and the end of the call stops
  the write; a late save must not resurrect it;
* the logs carry ids, counts and durations only — no transcript, no
  model text, no quoted text, no custom topic.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import wave
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from gnani_coach.conversation.metrics import validate_durable_metrics
from gnani_coach.persistence.consent import CONSENT_VERSION
from gnani_coach.persistence.errors import ConsentRequiredError
from gnani_coach.persistence.stores.memory import (
    InMemoryConsentStore,
    InMemoryRecordingStore,
)
from phase05_support import (
    FakeAnalysis,
    FakeIdentity,
    FakeReasoning,
    FakeRecordingStore,
    FakeSessionStore,
    FakeSttPort,
    FakeTtsPort,
    build_options,
    control_event,
    start_event,
)

SECRET_TOPIC = "my-secret-topic-about-the-raise"

#: ``_run_one_turn`` sends this many 512-sample frames per call.
TURN_FRAMES = 53
SAMPLES_PER_FRAME = 512


def _options(
    *,
    identity: FakeIdentity | None = None,
    analysis: FakeAnalysis | None = None,
    stt: FakeSttPort | None = None,
    tts: FakeTtsPort | None = None,
    reasoning: FakeReasoning | None = None,
    session_store: FakeSessionStore | None = None,
    recording_store: FakeRecordingStore | None = None,
    **kwargs,
):
    return build_options(
        identity=identity or FakeIdentity(),
        analysis=analysis or FakeAnalysis(),
        stt=stt or FakeSttPort(),
        tts=tts or FakeTtsPort(),
        reasoning=reasoning or FakeReasoning(),
        session_store=session_store,
        recording_store=recording_store,
        **kwargs,
    )


def _run_one_turn(call) -> None:
    call.speech(8)
    call.silence(45)


def _end(call) -> None:
    call.send(control_event("end", {"reason": "learner_ended"}))
    call.wait_for_state("ended", limit=30, timeout=5.0)


def test_a_guest_writes_nothing(harness) -> None:
    """No token, no store, no recording."""
    store = FakeSessionStore()
    recordings = FakeRecordingStore()
    options = _options(session_store=store, recording_store=recordings)
    call = harness(options)
    try:
        call.start()
        _run_one_turn(call)
        _end(call)
    finally:
        call.close()
    assert store.records == []
    assert recordings.saved == []


def test_an_account_without_consent_writes_metrics_only(harness) -> None:
    """The metrics are written; the audio is not."""
    store = FakeSessionStore()
    recordings = FakeRecordingStore()
    options = _options(session_store=store, recording_store=recordings)
    call = harness(options)
    try:
        call.start(token="good-token")
        _run_one_turn(call)
        _end(call)
    finally:
        call.close()
    assert len(store.records) == 1
    assert recordings.saved == []
    assert store.records[0]["recordingId"] is None


def test_an_account_with_consent_writes_the_recording(harness) -> None:
    """The consented audio is written, as a playable WAV, and the metrics name it."""
    store = FakeSessionStore()
    recordings = FakeRecordingStore()
    options = _options(session_store=store, recording_store=recordings)
    call = harness(options)
    try:
        call.start(
            token="good-token",
            recording_retention=True,
            consent_granted=True,
        )
        _run_one_turn(call)
        _end(call)
    finally:
        call.close()
    assert len(recordings.saved) == 1
    user_id, session_id, audio, duration_ms = recordings.saved[0]
    assert user_id == "usr_testuser"
    assert audio, "the consented audio is written"
    assert duration_ms > 0
    assert len(store.records) == 1
    assert store.records[0]["recordingId"] == "rec_testrecord"

    # The store records the object as ``audio/wav``; the bytes it received
    # must therefore be a real WAV, not the raw PCM buffer.
    assert audio[:4] == b"RIFF"
    assert audio[8:16] == b"WAVEfmt "
    with wave.open(io.BytesIO(audio), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getframerate() == 16_000
        assert reader.getsampwidth() == 2
        assert reader.getnframes() == TURN_FRAMES * SAMPLES_PER_FRAME
        assert duration_ms == int(reader.getnframes() * 1000 / 16_000)


def test_a_withdrawn_consent_stops_the_late_write(harness) -> None:
    """A withdrawal between the start and the end stops the write."""
    store = FakeSessionStore()
    recordings = FakeRecordingStore()
    granted = {"value": True}

    def consent_checker() -> bool:
        return granted["value"]

    options = _options(
        session_store=store,
        recording_store=recordings,
        consent_checker=consent_checker,
    )
    call = harness(options)
    try:
        call.start(
            token="good-token",
            recording_retention=True,
            consent_granted=True,
        )
        _run_one_turn(call)
        granted["value"] = False  # the learner withdraws the consent
        _end(call)
    finally:
        call.close()
    assert recordings.saved == [], "a withdrawn consent must not be written"
    assert len(store.records) == 1
    assert store.records[0]["recordingId"] is None


def test_a_store_side_withdrawal_refuses_the_write(harness, caplog) -> None:
    """The recording store re-reads consent at write time.

    This is the race the real store exists for: the runtime's consent
    snapshot was taken at ``start`` and still says granted, while the
    account withdrew before the write. The store raises
    ``ConsentRequiredError``; the runtime handles it, the metrics are still
    written, and no recording is.
    """
    consent = InMemoryConsentStore()
    asyncio.run(
        consent.set_state(
            "usr_testuser", consent_version=CONSENT_VERSION, granted=True
        )
    )
    recordings = InMemoryRecordingStore(consent_store=consent)
    store = FakeSessionStore()
    options = _options(session_store=store, recording_store=recordings)
    call = harness(options)
    try:
        call.start(
            token="good-token",
            recording_retention=True,
            consent_granted=True,
        )
        _run_one_turn(call)
        asyncio.run(
            consent.set_state(
                "usr_testuser", consent_version=CONSENT_VERSION, granted=False
            )
        )
        with caplog.at_level(logging.INFO, logger="gnani_coach.conversation"):
            _end(call)
    finally:
        call.close()

    log = "\n".join(record.getMessage() for record in caplog.records)
    assert "recording write failed" in log, "the store refused the write"
    assert len(store.records) == 1, "the metrics are still written"
    assert store.records[0]["recordingId"] is None

    # The refusal is the store's own semantics, not merely the runtime's
    # snapshot: the real store raises when asked after the withdrawal.
    with pytest.raises(ConsentRequiredError):
        asyncio.run(
            recordings.save_recording(
                "usr_testuser",
                "ses_withdrawn",
                b"\x00\x00" * 16,
                duration_ms=1,
            )
        )


def test_the_metrics_document_is_valid(harness) -> None:
    """The durable document satisfies the frozen schema."""
    contracts = Path("packages/contracts/data/catalog.json").resolve().parents[1]
    schema = json.loads(
        (contracts / "schemas" / "durable-metrics.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    store = FakeSessionStore()
    options = _options(session_store=store)
    call = harness(options)
    try:
        call.start(token="good-token")
        _run_one_turn(call)
        _end(call)
    finally:
        call.close()
    document = store.records[0]
    assert validate_durable_metrics(document) == []
    errors = list(validator.iter_errors(document))
    assert errors == [], errors[0].message if errors else ""


def test_the_metrics_document_carries_no_content(harness) -> None:
    """The durable document has no transcript, no model text and no topic."""
    store = FakeSessionStore()
    options = _options(session_store=store)
    call = harness(options)
    try:
        call.start(
            token="good-token",
            scenario_id="custom",
            custom_topic={"text": SECRET_TOPIC, "persisted": False},
        )
        _run_one_turn(call)
        _end(call)
    finally:
        call.close()
    raw = json.dumps(store.records[0])
    assert "one two three" not in raw
    assert "That sounds like a good point" not in raw
    assert SECRET_TOPIC not in raw
    for forbidden in ("transcript", "quotedMistakes", "modelText", "customTopic"):
        assert forbidden not in store.records[0]


def test_the_logs_carry_no_content(harness, caplog) -> None:
    """The metrics-only logs carry ids, counts and durations only."""
    store = FakeSessionStore()
    options = _options(session_store=store)
    call = harness(options)
    with caplog.at_level(logging.DEBUG, logger="gnani_coach.conversation"):
        try:
            call.start(
                token="good-token",
                scenario_id="custom",
                custom_topic={"text": SECRET_TOPIC, "persisted": False},
            )
            _run_one_turn(call)
            _end(call)
        finally:
            call.close()
    assert caplog.records, "the call must log something"
    raw = "\n".join(record.getMessage() for record in caplog.records)
    assert "one two three" not in raw
    assert "That sounds like a good point" not in raw
    assert SECRET_TOPIC not in raw
    assert "raise" not in raw
    # What is left is ids, counts and durations.
    assert "session=" in raw
    assert "turns=" in raw
    assert "duration_ms=" in raw


def test_a_failing_store_does_not_break_the_call(harness) -> None:
    """A store failure is reported, and the call still ends cleanly."""
    store = FakeSessionStore()
    store.fail = True
    options = _options(session_store=store)
    call = harness(options)
    try:
        call.start(token="good-token")
        _run_one_turn(call)
        _end(call)
    finally:
        call.close()
    assert store.records == []


def test_the_start_event_may_not_carry_a_persisted_topic(harness) -> None:
    """A custom topic is never persisted, so it may not claim to be."""
    options = _options()
    call = harness(options)
    try:
        event = start_event(
            scenario_id="custom",
            custom_topic={"text": SECRET_TOPIC, "persisted": True},
        )
        call.socket.send_json(event)
        seen = call.next_event()
        while seen["type"] == "status":
            seen = call.next_event()
        assert seen["type"] == "error"
        assert seen["payload"]["code"] == "invalid_start"
    finally:
        call.close()
