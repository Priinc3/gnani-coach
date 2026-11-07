"""The in-memory stores: the semantics both backends share.

**Phase 06 owns this file.** The in-memory stores are the reference
implementation of the behaviour: metrics-only, owner-scoped, consent
re-checked at write time, fenced against a late write, and expired.

The metrics-only inspection is the important one here: a document that
carries content must be refused *before* the write, and neither the
store nor the log may keep the content.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from gnani_coach.persistence.errors import (
    ConsentRequiredError,
    ContentRejectedError,
    RecordingFencedError,
)
from gnani_coach.persistence.stores.memory import (
    InMemoryConsentStore,
    InMemoryRecordingStore,
    InMemorySessionStore,
)

USER_A = f"usr_{'a' * 32}"
USER_B = f"usr_{'b' * 32}"
SESSION_ID = "ses_a1b2c3d4"
AUDIO = b"RIFF-fake-wav-bytes"


def run(coro):
    return asyncio.run(coro)


def document(session_id: str = SESSION_ID, recorded_at: str = "2026-10-16T09:40:00Z") -> dict:
    """A valid durable-metrics document (numbers and ids only)."""
    return {
        "metricsVersion": "0.1",
        "sessionId": session_id,
        "recordedAt": recorded_at,
        "practiceLanguageId": "hindi",
        "scenarioId": "everyday",
        "recordingId": None,
        "turns": [
            {
                "turnId": "trn_a3b4c5d6",
                "roundId": "rnd_c9d0e1f2",
                "durationMs": 42000,
                "recognitionStatus": "measured",
                "audioSourceClassification": "learner-audio",
                "observations": [
                    {
                        "metricKey": "pause.count",
                        "method": "vad_speech_regions",
                        "status": "available",
                        "value": 3,
                        "unit": "count",
                    }
                ],
            }
        ],
        "totals": {"turnCount": 1, "speakingTimeMs": 30000},
    }


# ---------------------------------------------------------------------------
# metrics only
# ---------------------------------------------------------------------------


def test_a_document_with_content_is_refused_before_the_write() -> None:
    store = InMemorySessionStore()
    poisoned = document()
    poisoned["transcript"] = "the learners own words"
    with pytest.raises(ContentRejectedError):
        run(store.save_metrics_for(USER_A, poisoned))
    assert run(store.list_sessions(USER_A)) == []


def test_a_nested_content_key_is_refused() -> None:
    store = InMemorySessionStore()
    poisoned = document()
    poisoned["turns"][0]["observations"][0]["modelText"] = "you said um a lot"
    with pytest.raises(ContentRejectedError):
        run(store.save_metrics_for(USER_A, poisoned))


def test_free_text_is_refused() -> None:
    store = InMemorySessionStore()
    poisoned = document()
    poisoned["totals"]["note"] = "a free-text note"
    with pytest.raises(ContentRejectedError):
        run(store.save_metrics_for(USER_A, poisoned))


def test_the_refusal_names_the_path_and_not_the_value() -> None:
    store = InMemorySessionStore()
    poisoned = document()
    poisoned["transcript"] = "the learners own words"
    with pytest.raises(ContentRejectedError) as caught:
        run(store.save_metrics_for(USER_A, poisoned))
    assert "transcript" in str(caught.value)
    assert "learners own words" not in str(caught.value)


def test_the_stored_record_holds_no_content(caplog: pytest.LogCaptureFixture) -> None:
    store = InMemorySessionStore()
    with caplog.at_level(logging.DEBUG):
        run(store.save_metrics_for(USER_A, document()))
    stored = run(store.get_session(USER_A, SESSION_ID))
    assert stored is not None
    assert "the learners own words" not in str(stored)
    assert "transcript" not in str(stored)
    assert "the learners own words" not in caplog.text


def test_a_guest_writes_nothing() -> None:
    async def no_owner():
        return None

    store = InMemorySessionStore(owner_resolver=no_owner)
    run(store.save_metrics(document()))
    assert run(store.list_sessions(USER_A)) == []


def test_the_owner_comes_from_the_request_context() -> None:
    async def owner():
        return USER_A

    store = InMemorySessionStore(owner_resolver=owner)
    run(store.save_metrics(document()))
    assert len(run(store.list_sessions(USER_A))) == 1
    assert run(store.list_sessions(USER_B)) == []


# ---------------------------------------------------------------------------
# isolation
# ---------------------------------------------------------------------------


def test_a_cannot_read_b_sessions() -> None:
    store = InMemorySessionStore()
    run(store.save_metrics_for(USER_B, document()))
    assert run(store.list_sessions(USER_A)) == []
    assert run(store.get_session(USER_A, SESSION_ID)) is None
    assert len(run(store.list_sessions(USER_B))) == 1


def test_a_cannot_read_or_delete_b_s_recording() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_B, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_B, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.get_recording(USER_A, reference.recording_id)) is None
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is False
    assert run(recordings.get_recording(USER_B, reference.recording_id)) == AUDIO


# ---------------------------------------------------------------------------
# consent
# ---------------------------------------------------------------------------


def test_a_recording_needs_consent() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    with pytest.raises(ConsentRequiredError):
        run(recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000))


def test_consent_on_then_off_stops_the_write() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert reference.recording_id.startswith("rec_")

    run(consent.set_state(USER_A, consent_version="0.1", granted=False))
    with pytest.raises(ConsentRequiredError):
        run(recordings.save_recording(USER_A, "ses_other1234", AUDIO, duration_ms=1000))


def test_a_withdrawal_records_the_version_and_the_time() -> None:
    consent = InMemoryConsentStore()
    state = run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    assert state.consent_version == "0.1"
    assert state.recording_retention_granted is True
    assert state.recording_retention_granted_at is not None
    withdrawn = run(consent.set_state(USER_A, consent_version="0.1", granted=False))
    assert withdrawn.recording_retention_granted is False
    assert withdrawn.recording_retention_granted_at is None
    assert withdrawn.updated_at is not None


def test_a_withdrawal_does_not_delete_the_old_recording() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    run(consent.set_state(USER_A, consent_version="0.1", granted=False))
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO


# ---------------------------------------------------------------------------
# the fence
# ---------------------------------------------------------------------------


def test_a_late_save_after_a_delete_cannot_recreate_the_recording() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is True

    with pytest.raises(RecordingFencedError):
        run(
            recordings.save_recording(
                USER_A,
                SESSION_ID,
                AUDIO,
                duration_ms=1000,
                recording_id=reference.recording_id,
            )
        )


def test_a_late_save_after_a_delete_cannot_recreate_the_session_either() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    run(recordings.delete_recording(USER_A, reference.recording_id))
    with pytest.raises(RecordingFencedError):
        run(recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000))


def test_a_late_save_after_a_withdrawal_is_refused() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    run(consent.set_state(USER_A, consent_version="0.1", granted=False))
    with pytest.raises(ConsentRequiredError):
        run(recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000))


def test_a_repeated_delete_is_false() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is True
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is False


# ---------------------------------------------------------------------------
# the expiry
# ---------------------------------------------------------------------------


def test_a_recording_expires_after_thirty_days() -> None:
    moment = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    clock = {"now": moment}
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent, clock=lambda: clock["now"])
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO

    clock["now"] = moment + timedelta(days=29, hours=23)
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO

    clock["now"] = moment + timedelta(days=30, seconds=1)
    assert run(recordings.get_recording(USER_A, reference.recording_id)) is None


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_ten_concurrent_saves_all_land() -> None:
    consent = InMemoryConsentStore()
    recordings = InMemoryRecordingStore(consent)
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))

    async def save_all() -> list[str]:
        references = await asyncio.gather(
            *[
                recordings.save_recording(
                    USER_A, f"ses_{index:08d}", AUDIO, duration_ms=1000
                )
                for index in range(10)
            ]
        )
        return [reference.recording_id for reference in references]

    identifiers = run(save_all())
    assert len(set(identifiers)) == 10, "every save gets its own id"
    for identifier in identifiers:
        assert run(recordings.get_recording(USER_A, identifier)) == AUDIO


def test_ten_concurrent_session_saves_all_land() -> None:
    async def owner():
        return USER_A

    store = InMemorySessionStore(owner_resolver=owner)

    async def save_all() -> None:
        await asyncio.gather(
            *[
                store.save_metrics(document(session_id=f"ses_{index:08d}"))
                for index in range(10)
            ]
        )

    run(save_all())
    assert len(run(store.list_sessions(USER_A, limit=100))) == 10
