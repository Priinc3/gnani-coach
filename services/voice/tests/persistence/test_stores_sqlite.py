"""The SQLite stores: the same semantics as the in-memory reference.

The tests use a temporary directory and a temporary database. Nothing
reaches the network. The owner ids and the audio bytes are obvious
sentinels.
"""

from __future__ import annotations

import asyncio
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

import gnani_coach.persistence.stores.sqlite as sqlite_module
from gnani_coach.persistence.consent import isoformat, utc_now
from gnani_coach.persistence.errors import (
    ConsentRequiredError,
    ContentRejectedError,
    RecordingFencedError,
    RecordingTooLargeError,
    StorageQuotaExceededError,
)
from gnani_coach.persistence.stores.sqlite import (
    SQLiteConsentStore,
    SQLiteDatabase,
    SQLiteRecordingStore,
    SQLiteSessionStore,
)

USER_A = f"usr_{'a' * 32}"
USER_B = f"usr_{'b' * 32}"
SESSION_ID = "ses_a1b2c3d4"
AUDIO = b"RIFF-fake-wav-bytes"


def run(coro):
    return asyncio.run(coro)


async def add_user(database: SQLiteDatabase, user_id: str, email: str) -> None:
    created = await database.create_user(
        user_id, email, "scrypt$16384$8$1$00$00", isoformat(utc_now())
    )
    assert created is True


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(tmp_path / "data")
    run(add_user(db, USER_A, "a@example.com"))
    run(add_user(db, USER_B, "b@example.com"))
    yield db
    db.close()


@pytest.fixture
def stores(database):
    consent = SQLiteConsentStore(database)
    sessions = SQLiteSessionStore(database)
    recordings = SQLiteRecordingStore(database, consent)
    return consent, sessions, recordings


def document(session_id: str = SESSION_ID, recorded_at: str = "2026-10-16T09:40:00Z") -> dict:
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


def test_a_document_with_content_is_refused(stores) -> None:
    _, sessions, _ = stores
    poisoned = document()
    poisoned["transcript"] = "the learners own words"
    with pytest.raises(ContentRejectedError):
        run(sessions.save_metrics_for(USER_A, poisoned))
    assert run(sessions.list_sessions(USER_A)) == []


def test_a_nested_content_key_is_refused(stores) -> None:
    _, sessions, _ = stores
    poisoned = document()
    poisoned["turns"][0]["observations"][0]["modelText"] = "you said um a lot"
    with pytest.raises(ContentRejectedError):
        run(sessions.save_metrics_for(USER_A, poisoned))


def test_the_stored_record_holds_no_content(stores) -> None:
    _, sessions, _ = stores
    run(sessions.save_metrics_for(USER_A, document()))
    stored = run(sessions.get_session(USER_A, SESSION_ID))
    assert stored is not None
    assert "transcript" not in str(stored)
    assert len(run(sessions.list_sessions(USER_A))) == 1


def test_a_guest_writes_nothing(database: SQLiteDatabase) -> None:
    async def no_owner():
        return None

    sessions = SQLiteSessionStore(database, owner_resolver=no_owner)
    run(sessions.save_metrics(document()))
    assert run(sessions.list_sessions(USER_A)) == []


# ---------------------------------------------------------------------------
# isolation
# ---------------------------------------------------------------------------


def test_a_cannot_read_b_sessions(stores) -> None:
    _, sessions, _ = stores
    run(sessions.save_metrics_for(USER_B, document()))
    assert run(sessions.list_sessions(USER_A)) == []
    assert run(sessions.get_session(USER_A, SESSION_ID)) is None
    assert len(run(sessions.list_sessions(USER_B))) == 1


def test_a_cannot_read_or_delete_b_s_recording(stores) -> None:
    consent, _, recordings = stores
    run(consent.set_state(USER_B, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_B, SESSION_ID, AUDIO, duration_ms=1000)
    )
    assert run(recordings.get_recording(USER_A, reference.recording_id)) is None
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is False
    assert run(recordings.get_recording(USER_B, reference.recording_id)) == AUDIO


# ---------------------------------------------------------------------------
# consent and the fence
# ---------------------------------------------------------------------------


def test_a_recording_needs_consent(stores) -> None:
    _, _, recordings = stores
    with pytest.raises(ConsentRequiredError):
        run(recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000))


def test_a_withdrawal_stops_the_next_write_but_keeps_the_old_audio(stores) -> None:
    consent, _, recordings = stores
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    run(consent.set_state(USER_A, consent_version="0.1", granted=False))
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO
    with pytest.raises(ConsentRequiredError):
        run(recordings.save_recording(USER_A, "ses_other1234", AUDIO, duration_ms=1000))


def test_a_late_save_after_delete_is_fenced(stores) -> None:
    consent, _, recordings = stores
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
    with pytest.raises(RecordingFencedError):
        run(recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000))
    assert run(recordings.delete_recording(USER_A, reference.recording_id)) is False


# ---------------------------------------------------------------------------
# files, paths and expiry
# ---------------------------------------------------------------------------


def test_the_file_and_its_directory_are_private(stores) -> None:
    consent, _, recordings = stores
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    path = recordings._root / USER_A / f"{reference.recording_id}.wav"
    assert path.read_bytes() == AUDIO
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700


def test_path_traversal_is_rejected(stores) -> None:
    consent, _, recordings = stores
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    with pytest.raises(ContentRejectedError):
        run(
            recordings.save_recording(
                USER_A, SESSION_ID, AUDIO, duration_ms=1000, recording_id="../../evil"
            )
        )
    assert run(recordings.get_recording(USER_A, "../../evil")) is None


def test_a_recording_expires_after_thirty_days(database: SQLiteDatabase) -> None:
    moment = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    clock = {"now": moment}
    consent = SQLiteConsentStore(database, clock=lambda: clock["now"])
    recordings = SQLiteRecordingStore(database, consent, clock=lambda: clock["now"])
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    path = recordings._root / USER_A / f"{reference.recording_id}.wav"
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO

    clock["now"] = moment + timedelta(days=29, hours=23)
    assert run(recordings.get_recording(USER_A, reference.recording_id)) == AUDIO

    clock["now"] = moment + timedelta(days=30, seconds=1)
    assert run(recordings.get_recording(USER_A, reference.recording_id)) is None
    assert not path.exists()


def test_the_caps_are_enforced(stores, monkeypatch: pytest.MonkeyPatch) -> None:
    consent, _, recordings = stores
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    monkeypatch.setattr(sqlite_module, "MAX_RECORDING_BYTES", 100)
    monkeypatch.setattr(sqlite_module, "MAX_USER_RECORDING_BYTES", 150)
    with pytest.raises(RecordingTooLargeError):
        run(recordings.save_recording(USER_A, "ses_big00001", b"x" * 101, duration_ms=1))
    run(recordings.save_recording(USER_A, "ses_ok000001", b"x" * 100, duration_ms=1))
    with pytest.raises(StorageQuotaExceededError):
        run(recordings.save_recording(USER_A, "ses_ok000002", b"x" * 100, duration_ms=1))


# ---------------------------------------------------------------------------
# account deletion
# ---------------------------------------------------------------------------


def test_deleting_an_account_removes_rows_and_files(stores, database: SQLiteDatabase) -> None:
    consent, sessions, recordings = stores
    run(sessions.save_metrics_for(USER_A, document()))
    run(consent.set_state(USER_A, consent_version="0.1", granted=True))
    reference = run(
        recordings.save_recording(USER_A, SESSION_ID, AUDIO, duration_ms=1000)
    )
    path = recordings._root / USER_A / f"{reference.recording_id}.wav"
    assert path.exists()

    assert run(database.delete_user(USER_A)) is True
    assert not path.exists()
    assert run(sessions.list_sessions(USER_A)) == []
    assert run(recordings.get_recording(USER_A, reference.recording_id)) is None
    state = run(consent.get_state(USER_A))
    assert state.recording_retention_granted is False


def test_ten_concurrent_recording_saves_all_land(stores) -> None:
    consent, _, recordings = stores
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
    assert len(set(identifiers)) == 10
    for identifier in identifiers:
        assert run(recordings.get_recording(USER_A, identifier)) == AUDIO
