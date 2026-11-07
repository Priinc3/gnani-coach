"""The four private-history routes.

**Phase 06 owns this file.** The checks are the privacy promises of the
frozen contract: a guest has no history, another user's recording is
invisible, an error never echoes a token, and every failure uses the
frozen error shape.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from phase06_support import TOKEN_A, TOKEN_B, USER_A, USER_B

from fake_supabase import new_recording_id


def assert_error_shape(payload: dict, schema: dict) -> None:
    """The payload is the frozen error shape and nothing else."""
    Draft202012Validator(schema).validate(payload)


def consent_body(granted: bool, version: str = "0.1") -> dict:
    return {"consentVersion": version, "recordingRetentionGranted": granted}


# ---------------------------------------------------------------------------
# GET /api/history
# ---------------------------------------------------------------------------


def test_a_guest_has_no_history(harness, error_shape_schema) -> None:
    response = harness.client.get("/api/history")
    assert response.status_code == 401
    body = response.json()
    assert_error_shape(body, error_shape_schema)
    assert body["category"] == "unauthenticated"
    assert body["retryable"] is False


def test_a_request_without_an_authorization_header_is_a_guest(harness) -> None:
    assert harness.client.get("/api/history").status_code == 401


def test_a_malformed_authorization_header_is_a_guest(harness) -> None:
    for header in ("Bearer", "Basic abc", "Bearer  a b", "token"):
        response = harness.client.get("/api/history", headers={"Authorization": header})
        assert response.status_code == 401, header


def test_an_unknown_token_is_a_guest(harness) -> None:
    response = harness.client.get(
        "/api/history", headers={"Authorization": "Bearer not-a-known-token"}
    )
    assert response.status_code == 401


def test_an_empty_history_is_a_real_state(harness) -> None:
    response = harness.client.get("/api/history", headers=harness.auth(TOKEN_A))
    assert response.status_code == 200
    assert response.json() == {"sessions": []}


def test_the_history_carries_the_documented_shape(harness) -> None:
    _save_session(harness, USER_A, "ses_a1b2c3d4", "2026-10-16T09:40:00Z")
    response = harness.client.get("/api/history", headers=harness.auth(TOKEN_A))
    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert len(sessions) == 1
    row = sessions[0]
    assert set(row) == {
        "sessionId",
        "recordedAt",
        "practiceLanguageId",
        "scenarioId",
        "recordingId",
        "turnCount",
        "speakingTimeMs",
    }
    assert row["sessionId"] == "ses_a1b2c3d4"
    assert row["recordedAt"] == "2026-10-16T09:40:00Z"
    assert row["practiceLanguageId"] == "hindi"
    assert row["scenarioId"] == "everyday"
    assert row["recordingId"] is None
    assert row["turnCount"] == 1
    assert row["speakingTimeMs"] == 30000


def test_the_history_is_newest_first(harness) -> None:
    import asyncio

    asyncio.run(
        harness.sessions.save_metrics_for(
            USER_A, _document("ses_a1b2c3d4", "2026-10-16T09:40:00Z")
        )
    )
    asyncio.run(
        harness.sessions.save_metrics_for(
            USER_A, _document("ses_b2c3d4e5", "2026-10-18T09:40:00Z")
        )
    )
    response = harness.client.get("/api/history", headers=harness.auth(TOKEN_A))
    sessions = response.json()["sessions"]
    assert [row["sessionId"] for row in sessions] == [
        "ses_b2c3d4e5",
        "ses_a1b2c3d4",
    ]


# ---------------------------------------------------------------------------
# POST /api/consent
# ---------------------------------------------------------------------------


def test_a_guest_cannot_change_the_consent(harness, error_shape_schema) -> None:
    response = harness.client.post("/api/consent", json=consent_body(True))
    assert response.status_code == 401
    assert_error_shape(response.json(), error_shape_schema)


def test_granting_the_consent_records_the_version_and_the_time(harness) -> None:
    response = harness.client.post(
        "/api/consent", json=consent_body(True), headers=harness.auth(TOKEN_A)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recordingRetentionGranted"] is True
    assert isinstance(body["recordingRetentionGrantedAt"], str)
    assert body["recordingRetentionGrantedAt"].endswith("Z")

    import asyncio

    state = asyncio.run(harness.consent.get_state(USER_A))
    assert state.consent_version == "0.1"
    assert state.recording_retention_granted is True


def test_withdrawing_the_consent_does_not_delete_the_old_recordings(harness) -> None:
    import asyncio

    asyncio.run(harness.consent.set_state(USER_A, consent_version="0.1", granted=True))
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None

    response = harness.client.post(
        "/api/consent", json=consent_body(False), headers=harness.auth(TOKEN_A)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recordingRetentionGranted"] is False
    assert body["recordingRetentionGrantedAt"] is None

    # The audio is still there: a withdrawal stops future retention, and
    # the deletion is an explicit action.
    still_there = harness.client.get(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
    )
    assert still_there.status_code == 200


def test_an_unknown_consent_version_is_refused(harness, error_shape_schema) -> None:
    response = harness.client.post(
        "/api/consent", json=consent_body(True, "9.9"), headers=harness.auth(TOKEN_A)
    )
    assert response.status_code == 400
    assert_error_shape(response.json(), error_shape_schema)


def test_a_consent_body_that_is_not_a_boolean_is_refused(harness) -> None:
    for granted in ("yes", 1, None, [], {}):
        response = harness.client.post(
            "/api/consent",
            json={"consentVersion": "0.1", "recordingRetentionGranted": granted},
            headers=harness.auth(TOKEN_A),
        )
        assert response.status_code == 400, granted


def test_a_forged_user_id_in_the_body_is_ignored(harness) -> None:
    """Ownership comes from the verified token, never from the body."""
    import asyncio

    response = harness.client.post(
        "/api/consent",
        json={**consent_body(True), "userId": USER_B, "user_id": USER_B},
        headers=harness.auth(TOKEN_A),
    )
    assert response.status_code == 200
    state_a = asyncio.run(harness.consent.get_state(USER_A))
    state_b = asyncio.run(harness.consent.get_state(USER_B))
    assert state_a.recording_retention_granted is True
    assert state_b.recording_retention_granted is False


def test_an_oversized_body_is_refused(harness, error_shape_schema) -> None:
    payload = {**consent_body(True), "padding": "x" * 8000}
    response = harness.client.post(
        "/api/consent", json=payload, headers=harness.auth(TOKEN_A)
    )
    assert response.status_code == 413
    assert_error_shape(response.json(), error_shape_schema)


def test_a_body_that_is_not_json_is_refused(harness) -> None:
    response = harness.client.post(
        "/api/consent",
        content=b"this is not json",
        headers={**harness.auth(TOKEN_A), "Content-Type": "application/json"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET and DELETE /api/recordings/{id}
# ---------------------------------------------------------------------------


def test_the_owner_can_read_their_recording(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    response = harness.client.get(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFF-fake-wav-bytes"
    assert response.headers["cache-control"] == "no-store"


def test_another_users_recording_is_invisible(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    response = harness.client.get(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_B)
    )
    assert response.status_code == 404


def test_a_missing_recording_and_a_foreign_one_answer_identically(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    foreign = harness.client.get(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_B)
    )
    missing = harness.client.get(
        f"/api/recordings/{new_recording_id()}", headers=harness.auth(TOKEN_B)
    )
    assert foreign.status_code == missing.status_code == 404
    # The two answers are the same answer. The correlation id and the
    # timestamp are per response by the frozen error shape; everything
    # else - the code, the category, the message, the retryability - is
    # identical, so the answer cannot reveal whether the recording exists.
    foreign_body = foreign.json()
    missing_body = missing.json()
    for key in ("correlationId", "occurredAt"):
        foreign_body.pop(key, None)
        missing_body.pop(key, None)
    assert foreign_body == missing_body
    assert foreign.headers["content-type"] == missing.headers["content-type"]


def test_a_recording_id_that_cannot_exist_is_a_missing_recording(harness) -> None:
    for recording_id in ("../../etc/passwd", "not-a-recording-id", "rec_../../x"):
        response = harness.client.get(
            f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
        )
        assert response.status_code == 404, recording_id


def test_the_owner_can_delete_their_recording(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    response = harness.client.delete(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
    )
    assert response.status_code == 204
    assert response.content == b""


def test_a_repeated_delete_is_a_missing_recording(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    first = harness.client.delete(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
    )
    second = harness.client.delete(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
    )
    assert first.status_code == 204
    assert second.status_code == 404


def test_another_user_cannot_delete_a_recording(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    response = harness.client.delete(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_B)
    )
    assert response.status_code == 404
    # The recording is still there for its owner.
    still_there = harness.client.get(
        f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
    )
    assert still_there.status_code == 200


def test_a_guest_cannot_read_or_delete_a_recording(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    assert harness.client.get(f"/api/recordings/{recording_id}").status_code == 401
    assert (
        harness.client.delete(f"/api/recordings/{recording_id}").status_code == 401
    )


# ---------------------------------------------------------------------------
# what a response may never contain
# ---------------------------------------------------------------------------


def test_no_response_echoes_a_token_a_path_or_a_bucket_key(harness) -> None:
    recording_id = _save_recording(harness, USER_A, "ses_a1b2c3d4")
    assert recording_id is not None
    responses = [
        harness.client.get("/api/history", headers=harness.auth(TOKEN_A)),
        harness.client.get("/api/history"),
        harness.client.post("/api/consent", json=consent_body(True)),
        harness.client.get(
            f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_B)
        ),
        harness.client.delete(
            f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_B)
        ),
        harness.client.get(
            f"/api/recordings/{recording_id}", headers=harness.auth(TOKEN_A)
        ),
    ]
    for response in responses:
        text = response.text
        assert TOKEN_A not in text
        assert TOKEN_B not in text
        assert "recordings/" not in text, "no bucket key may be echoed"
        assert "/storage/v1" not in text
        assert "sb_fake" not in text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _document(session_id: str, recorded_at: str) -> dict:
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
                        "audioSourceClassification": "learner-audio",
                    }
                ],
            }
        ],
        "totals": {"turnCount": 1, "speakingTimeMs": 30000},
    }


def _save_session(harness, user_id: str, session_id: str, recorded_at: str) -> None:
    import asyncio

    asyncio.run(
        harness.sessions.save_metrics_for(user_id, _document(session_id, recorded_at))
    )


def _save_recording(harness, user_id: str, session_id: str) -> str | None:
    import asyncio

    asyncio.run(
        harness.consent.set_state(user_id, consent_version="0.1", granted=True)
    )
    reference = asyncio.run(
        harness.recordings.save_recording(
            user_id,
            session_id,
            b"RIFF-fake-wav-bytes",
            duration_ms=1000,
        )
    )
    return reference.recording_id
