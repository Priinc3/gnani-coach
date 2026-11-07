"""The Supabase-backed stores, against a fake Supabase.

**Phase 06 owns this file.** The fake speaks the same HTTPS the real
backend speaks, so the request building, the owner scoping, the upload
and the fence are all exercised for real. Nothing here reaches the
network and no real credential is used.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from gnani_coach.persistence.errors import (
    ConsentRequiredError,
    ContentRejectedError,
    RecordingFencedError,
)
from gnani_coach.persistence.stores.supabase import (
    SupabaseConsentStore,
    SupabaseRecordingStore,
    SupabaseRest,
    SupabaseSessionStore,
)

from fake_supabase import FAKE_SUPABASE_URL, FakeSupabase

USER_A = f"usr_{'a' * 32}"
SUBJECT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = f"usr_{'b' * 32}"
SUBJECT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SESSION_ID = "ses_a1b2c3d4"
AUDIO = b"RIFF-fake-wav-bytes"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def rest(fake: FakeSupabase) -> SupabaseRest:
    return SupabaseRest(
        FAKE_SUPABASE_URL,
        "sb_fake_service_role_key_for_tests_only",
        transport=httpx.MockTransport(fake.handler),
    )


@pytest.fixture
def consent(rest: SupabaseRest) -> SupabaseConsentStore:
    return SupabaseConsentStore(rest=rest)


@pytest.fixture
def sessions(rest: SupabaseRest) -> SupabaseSessionStore:
    async def no_owner():
        return None

    return SupabaseSessionStore(rest=rest, owner_resolver=no_owner)


@pytest.fixture
def recordings(
    rest: SupabaseRest, consent: SupabaseConsentStore
) -> SupabaseRecordingStore:
    return SupabaseRecordingStore(rest=rest, consent_store=consent)


def document(session_id: str = SESSION_ID, recorded_at: str = "2026-10-16T09:40:00Z") -> dict:
    return {
        "metricsVersion": "0.1",
        "sessionId": session_id,
        "recordedAt": recorded_at,
        "practiceLanguageId": "hindi",
        "scenarioId": "everyday",
        "recordingId": None,
        "turns": [],
        "totals": {"turnCount": 1, "speakingTimeMs": 30000},
    }


# ---------------------------------------------------------------------------
# the session store
# ---------------------------------------------------------------------------


def test_a_record_is_stored_for_its_owner(sessions, fake) -> None:
    run(sessions.save_metrics_for(USER_A, document()))
    rows = fake.tables["session_metrics"]
    assert len(rows) == 1
    assert rows[0]["user_id"] == SUBJECT_A
    assert rows[0]["session_id"] == SESSION_ID
    assert rows[0]["turn_count"] == 1
    assert rows[0]["speaking_time_ms"] == 30000


def test_a_document_with_content_never_reaches_the_database(sessions, fake) -> None:
    poisoned = document()
    poisoned["transcript"] = "the learners own words"
    with pytest.raises(ContentRejectedError):
        run(sessions.save_metrics_for(USER_A, poisoned))
    assert fake.tables["session_metrics"] == []
    assert not [entry for entry in fake.audit if entry["kind"] == "insert"]


def test_the_history_is_owner_scoped(sessions, fake) -> None:
    run(sessions.save_metrics_for(USER_A, document()))
    run(sessions.save_metrics_for(USER_B, document("ses_b2c3d4e5")))
    assert len(run(sessions.list_sessions(USER_A))) == 1
    assert len(run(sessions.list_sessions(USER_B))) == 1
    assert run(sessions.get_session(USER_B, SESSION_ID)) is None


def test_the_history_is_newest_first(sessions) -> None:
    run(sessions.save_metrics_for(USER_A, document("ses_a1b2c3d4", "2026-10-16T09:40:00Z")))
    run(sessions.save_metrics_for(USER_A, document("ses_b2c3d4e5", "2026-10-18T09:40:00Z")))
    summaries = run(sessions.list_sessions(USER_A))
    assert [summary.session_id for summary in summaries] == [
        "ses_b2c3d4e5",
        "ses_a1b2c3d4",
    ]


def test_a_guest_writes_nothing(sessions, fake) -> None:
    run(sessions.save_metrics(document()))
    assert fake.tables["session_metrics"] == []


# ---------------------------------------------------------------------------
# the recording store
# ---------------------------------------------------------------------------


def test_a_recording_is_uploaded_under_the_owner_folder(
    recordings, consent, fake
) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert list(fake.objects) == [f"{SUBJECT_A}/{reference.recording_id}"]
    assert fake.objects[f"{SUBJECT_A}/{reference.recording_id}"] == AUDIO


def test_the_row_carries_the_expiry_and_no_url(recordings, consent, fake) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    row = fake.tables["recordings"][0]
    assert row["recording_id"] == reference.recording_id
    assert row["user_id"] == SUBJECT_A
    assert row["owner_ref"] == USER_A
    assert row["state"] == "retained"
    assert row["deleted_at"] is None
    assert row["size_bytes"] == len(AUDIO)
    # The expiry is written as ``expires_at``, thirty days out.
    created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    assert expires - created == timedelta(days=30)
    # No URL, no signed URL, no object key is ever stored.
    for forbidden in ("public_url", "signed_url", "url", "object_key", "objectkey"):
        assert forbidden not in row


def test_the_returned_reference_carries_no_url(recordings, consent) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    for attribute in vars(reference):
        value = str(getattr(reference, attribute))
        assert "http" not in value
        assert "://" not in value
        if attribute in ("recording_id", "session_id"):
            assert "/" not in value


def test_a_recording_needs_consent(recordings, consent) -> None:
    with pytest.raises(ConsentRequiredError):
        run(recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000))


def test_the_consent_is_re_checked_at_write_time(recordings, consent, fake) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    run(consent.set_state(USER_A, consent_version="0.1", granted=False))
    with pytest.raises(ConsentRequiredError):
        run(
            recordings.save_recording(
                USER_A, "ses_other1234", AUDIO, duration_ms=1000
            )
        )
    # The recording that was already there is untouched: a withdrawal
    # stops future retention and does not delete.
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO


def test_another_user_cannot_read_or_delete_a_recording(
    recordings, consent, fake
) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.get_recording(USER_B, reference.recording_id)) is None
    assert run(recordings.delete_recording(USER_B, reference.recording_id)) is False
    assert fake.tables["recordings"][0]["state"] == "retained"


def test_the_owner_can_read_their_recording(recordings, consent) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO


def test_a_delete_marks_the_state_and_removes_the_audio(recordings, consent, fake) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is True
    row = fake.tables["recordings"][0]
    assert row["state"] == "deleted"
    assert row["deleted_at"] is not None
    assert fake.objects == {}
    assert run(recordings.get_recording(USER_A, reference.recording_id)) is None


def test_a_repeated_delete_is_false(recordings, consent) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is True
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is False


def test_a_late_save_after_a_delete_cannot_recreate_the_recording(
    recordings, consent, fake
) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    run(recordings.delete_recording(USER_A, reference.recording_id))
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
    assert fake.objects == {}, "no audio may be uploaded after the deletion"


def test_a_late_save_after_a_delete_cannot_recreate_the_session(
    recordings, consent, fake
) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    run(recordings.delete_recording(USER_A, reference.recording_id))
    with pytest.raises(RecordingFencedError):
        run(recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000))


def test_an_expired_recording_is_gone(recordings, consent, fake) -> None:
    moment = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    clock = {"now": moment}
    store = SupabaseRecordingStore(
        rest=recordings.rest,
        consent_store=consent,
        _clock=lambda: clock["now"],
    )
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        store.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(store.get_recording(USER_A, reference.recording_id)) == AUDIO
    clock["now"] = moment + timedelta(days=31)
    assert run(store.get_recording(USER_A, reference.recording_id)) is None


def test_the_consent_write_records_the_version_and_the_time(consent, fake) -> None:
    state = run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    assert state.consent_version == "0.1"
    assert state.recording_retention_granted is True
    assert state.recording_retention_granted_at is not None
    row = fake.tables["consent"][0]
    assert row["consent_version"] == "0.1"
    assert row["recording_retention_granted"] is True
    assert row["updated_at"] is not None
    # Every write is also on the record.
    assert len(fake.tables["consent_events"]) == 1
    assert fake.tables["consent_events"][0]["consent_version"] == "0.1"


def test_a_withdrawal_is_recorded_and_does_not_delete_the_recording(
    recordings, consent, fake
) -> None:
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    state = run(consent.set_state(USER_A, consent_version="0.1", granted=False))
    assert state.recording_retention_granted is False
    assert state.recording_retention_granted_at is None
    assert fake.tables["recordings"][0]["state"] == "retained"
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO


def test_the_service_role_key_never_leaves_the_store(rest, fake) -> None:
    """The key is sent in the headers and never in a body or a query."""
    run(
        SupabaseConsentStore(rest=rest).set_state(
            USER_A, consent_version="0.1", granted=True
        )
    )
    for request in fake.requests:
        assert "sb_fake_service_role_key_for_tests_only" not in str(request.url)
        if request.content:
            assert b"sb_fake_service_role_key_for_tests_only" not in request.content
