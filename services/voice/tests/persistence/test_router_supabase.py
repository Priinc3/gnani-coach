"""The four routes against the **Supabase** stores.

**Phase 06 owns this file.** The routes, the owner scoping and the real
store implementations run here; only the Supabase HTTP API is faked. It
is the whole chain that the B2 TEST will exercise, minus a real project.
"""

from __future__ import annotations

import asyncio
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from phase06_support import TOKEN_A, TOKEN_B, USER_A, USER_B, FakeIdentity

from gnani_coach.identity import get_identity
from gnani_coach.main import app
from gnani_coach.persistence.stores.supabase import (
    SupabaseConsentStore,
    SupabaseRecordingStore,
    SupabaseRest,
    SupabaseSessionStore,
)

from fake_supabase import FAKE_SERVICE_ROLE_KEY, FAKE_SUPABASE_URL, FakeSupabase

# The package re-exports the APIRouter under the name ``router``, so the
# module object has to be taken from ``sys.modules`` to be able to
# monkeypatch the store accessors the routes call.
import gnani_coach.persistence.router  # noqa: F401

persistence_router = sys.modules["gnani_coach.persistence.router"]

SUBJECT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase) -> TestClient:
    """The service, wired to the Supabase stores over a fake backend."""
    rest = SupabaseRest(
        FAKE_SUPABASE_URL,
        FAKE_SERVICE_ROLE_KEY,
        transport=httpx.MockTransport(fake.handler),
    )
    consent = SupabaseConsentStore(rest=rest)
    sessions = SupabaseSessionStore(rest=rest)
    recordings = SupabaseRecordingStore(rest=rest, consent_store=consent)

    monkeypatch.setattr(persistence_router, "get_session_store", lambda: sessions)
    monkeypatch.setattr(persistence_router, "get_recording_store", lambda: recordings)
    monkeypatch.setattr(persistence_router, "get_consent_store", lambda: consent)

    app.dependency_overrides[get_identity] = lambda: FakeIdentity(
        {TOKEN_A: USER_A, TOKEN_B: USER_B}
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_the_consent_reaches_the_table(client: TestClient, fake: FakeSupabase) -> None:
    response = client.post(
        "/api/consent",
        json={"consentVersion": "0.1", "recordingRetentionGranted": True},
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    assert response.status_code == 200
    assert response.json()["recordingRetentionGranted"] is True
    assert fake.tables["consent"][0]["user_id"] == SUBJECT_A
    assert fake.tables["consent"][0]["consent_version"] == "0.1"
    assert fake.tables["consent_events"], "every consent write is on the record"


def test_the_history_reaches_the_table(client: TestClient, fake: FakeSupabase) -> None:
    fake.tables["session_metrics"].append(
        {
            "user_id": SUBJECT_A,
            "session_id": "ses_a1b2c3d4",
            "recorded_at": "2026-10-16T09:40:00Z",
            "practice_language_id": "hindi",
            "scenario_id": "everyday",
            "recording_id": None,
            "turn_count": 1,
            "speaking_time_ms": 30000,
        }
    )
    response = client.get("/api/history", headers={"Authorization": f"Bearer {TOKEN_A}"})
    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["sessionId"] == "ses_a1b2c3d4"
    assert sessions[0]["turnCount"] == 1
    assert sessions[0]["speakingTimeMs"] == 30000
    assert sessions[0]["recordingId"] is None


def test_the_recording_lifecycle_over_the_backend(
    client: TestClient, fake: FakeSupabase
) -> None:
    granted = client.post(
        "/api/consent",
        json={"consentVersion": "0.1", "recordingRetentionGranted": True},
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    assert granted.status_code == 200

    rest = SupabaseRest(
        FAKE_SUPABASE_URL,
        FAKE_SERVICE_ROLE_KEY,
        transport=httpx.MockTransport(fake.handler),
    )
    store = SupabaseRecordingStore(rest=rest, consent_store=SupabaseConsentStore(rest=rest))
    reference = run(
        store.save_recording(USER_A, "ses_a1b2c3d4", b"RIFF-fake", duration_ms=1000)
    )

    # The object is in the owner's own folder, and nowhere else.
    assert list(fake.objects) == [f"{SUBJECT_A}/{reference.recording_id}"]

    read = client.get(
        f"/api/recordings/{reference.recording_id}",
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    assert read.status_code == 200
    assert read.content == b"RIFF-fake"

    # Another user gets the same answer as for a recording that is not
    # there.
    foreign = client.get(
        f"/api/recordings/{reference.recording_id}",
        headers={"Authorization": f"Bearer {TOKEN_B}"},
    )
    assert foreign.status_code == 404

    deleted = client.delete(
        f"/api/recordings/{reference.recording_id}",
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    assert deleted.status_code == 204
    assert fake.objects == {}
    assert fake.tables["recordings"][0]["state"] == "deleted"
    assert fake.tables["recordings"][0]["deleted_at"] is not None

    repeat = client.delete(
        f"/api/recordings/{reference.recording_id}",
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    assert repeat.status_code == 404


def test_a_guest_gets_nothing_over_the_backend(
    client: TestClient, fake: FakeSupabase
) -> None:
    assert client.get("/api/history").status_code == 401
    assert client.post("/api/consent", json={}).status_code == 401
    assert not fake.requests, "a guest must not reach the backend at all"
