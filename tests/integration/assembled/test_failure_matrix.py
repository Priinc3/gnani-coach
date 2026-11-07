"""The Phase 07 failure matrix (B) against the assembled service.

Every test boots the real FastAPI app with its real lifespan and drives it
through an in-process WebSocket. Only the provider ports and Supabase are
doubles. The labels in REPORT.md say so.

These tests run in their own pytest process (``--confcutdir``), because
the environment has to be set before ``gnani_coach.main`` is imported.
"""

from __future__ import annotations

import time

import pytest
from starlette.websockets import WebSocketDisconnect

import harness
from conftest import (
    FRAME_BYTES,
    USER_A,
    closing,
    control_event,
    database,
    end_call,
    events_of,
    fake_stack,
    grant_consent,
    mint_token,
    open_call,
    read_until,
    send_frames,
    speak_one_turn,
    speech_frame,
    start_event,
    status_states,
    wav_duration_seconds,
    withdraw_consent,
)
from gnani_coach.conversation.connections import registry as connections_registry


def _error_codes(events):
    return [
        event["payload"]["code"]
        for event in events_of(events, "error")
        if isinstance(event.get("payload"), dict)
    ]


def _ending_notice(events) -> str | None:
    for event in events_of(events, "status"):
        if event["payload"].get("state") == "ended":
            return event["payload"].get("detail")
    return None


def test_a_guest_call_writes_nothing_and_ends_cleanly(client):
    ws, opening = open_call(client)
    with closing(ws):
        assert "ready" in status_states(opening)
        speak_one_turn(ws)
        ended = end_call(ws)
    assert "ended" in status_states(ended)
    assert database.sessions == {}
    assert database.recordings == {}
    assert database.objects == {}


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("network", "provider_unavailable"),
        ("auth", "provider_rejected_request"),
        ("throttle", "provider_rate_limited"),
    ],
)
def test_a_recognition_failure_keeps_the_call_alive(client, mode, expected_code):
    """Gnani STT down, auth rejected and throttled are distinct, named errors."""
    fake_stack.BEHAVIOUR.stt_mode = mode
    ws, _opening = open_call(client)
    with closing(ws):
        send_frames(ws)
        events, close = read_until(
            ws,
            lambda event: event.get("type") == "error",
        )
        assert close is None
        assert expected_code in _error_codes(events)
        # The call survives: recognition reopens with the same VAD and the
        # learner may keep talking. The status was already ``listening``, so
        # there is no new status event to wait for. A clean end proves the
        # runtime is still alive.
        ended = end_call(ws)
        assert "ended" in status_states(ended)


def test_a_tts_failure_mid_sentence_is_named_and_the_call_survives(client):
    fake_stack.BEHAVIOUR.tts_fail_after = 5
    ws, _opening = open_call(client)
    with closing(ws):
        events = speak_one_turn(ws)
        assert "provider_unavailable" in _error_codes(events)
        assert "listening" in status_states(events)
        ended = end_call(ws)
        assert "ended" in status_states(ended)


def test_a_reasoning_timeout_is_named_and_the_call_survives(client):
    fake_stack.BEHAVIOUR.reasoning_mode = "timeout"
    ws, _opening = open_call(client)
    with closing(ws):
        events = speak_one_turn(ws)
        assert "provider_timeout" in _error_codes(events)
        assert "listening" in status_states(events)
        assert end_call(ws)


def test_a_malformed_feedback_document_falls_back_to_the_facts(client):
    fake_stack.BEHAVIOUR.reasoning_mode = "malformed"
    ws, _opening = open_call(client)
    with closing(ws):
        for _ in range(3):
            send_frames(ws)
            read_until(
                ws,
                lambda event: event.get("type") == "status"
                and event["payload"].get("state") == "listening",
            )
        send_frames(ws)
        events, close = read_until(
            ws,
            lambda event: event.get("type") == "round_feedback",
        )
        assert close is None
        feedback = events_of(events, "round_feedback")[0]["payload"]
        # The facts-only fallback invents no strength, improvement or note;
        # the measured evidence is still there. Filler stays
        # ``insufficient_evidence`` rather than becoming a count.
        assert feedback["strengths"] == []
        assert feedback["improvements"] == []
        assert feedback["languageNotes"] == []
        assert feedback["evidence"]
        filler = [
            item
            for item in feedback["evidence"]
            if item.get("metricKey") == "filler.count"
        ]
        assert filler and filler[0]["status"] == "insufficient_evidence"
        ended = end_call(ws)
        assert "ended" in status_states(ended)


def test_supabase_auth_down_continues_as_a_guest_with_a_notice(client):
    database.failures.add("auth")
    ws, opening = open_call(client, token=mint_token())
    with closing(ws):
        ready = [
            event
            for event in events_of(opening, "status")
            if event["payload"].get("state") == "ready"
        ]
        assert ready, "a ready status is still sent"
        detail = ready[0]["payload"].get("detail") or ""
        assert detail.startswith("notice:")
        assert "guest" in detail
        speak_one_turn(ws)
        end_call(ws)
    assert database.sessions == {}


def test_supabase_rest_down_at_the_end_says_not_saved(client):
    database.failures.add("rest")
    ws, _opening = open_call(client, token=mint_token())
    with closing(ws):
        speak_one_turn(ws)
        ended = end_call(ws)
    detail = _ending_notice(ended) or ""
    assert "notice:" in detail
    assert "not saved" in detail
    assert database.sessions == {}


def test_supabase_storage_down_keeps_the_metrics_and_says_the_audio_is_missing(client):
    token = mint_token()
    grant_consent(client, token)
    database.failures.add("storage")
    ws, _opening = open_call(client, token=token, recording=True, consent=True)
    with closing(ws):
        speak_one_turn(ws)
        ended = end_call(ws)
    detail = _ending_notice(ended) or ""
    assert "notice:" in detail
    assert "recording could not be saved" in detail
    rows = [
        row
        for (user_id, _session_id), row in database.sessions.items()
        if user_id == USER_A
    ]
    assert len(rows) == 1
    assert rows[0]["recording_id"] is None
    assert database.recordings == {}


def test_an_expired_token_mid_call_does_not_drop_or_re_key_the_session(client):
    """The token is verified once at start; expiry later does not move the data."""
    token = mint_token(ttl_seconds=3)
    ws, _opening = open_call(client, token=token)
    with closing(ws):
        speak_one_turn(ws)
        time.sleep(4)
        end_call(ws)
    rows = [
        row
        for (user_id, _session_id), row in database.sessions.items()
        if user_id == USER_A
    ]
    assert len(rows) == 1
    assert rows[0]["turn_count"] == 1


def test_a_recording_is_a_wav_that_parses_and_delete_removes_it(client):
    token = mint_token()
    grant_consent(client, token)
    ws, _opening = open_call(client, token=token, recording=True, consent=True)
    with closing(ws):
        speak_one_turn(ws)
        end_call(ws)

    rows = list(database.recordings.values())
    assert len(rows) == 1
    recording_id = rows[0]["recording_id"]
    key = next(iter(database.objects))
    payload = database.objects[key]
    assert payload[:4] == b"RIFF"
    assert payload[8:12] == b"WAVE"
    assert wav_duration_seconds(payload) > 0

    response = client.get(
        f"/api/recordings/{recording_id}",
        headers={"authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.content == payload
    assert wav_duration_seconds(response.content) > 0

    deleted = client.delete(
        f"/api/recordings/{recording_id}",
        headers={"authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204
    again = client.get(
        f"/api/recordings/{recording_id}",
        headers={"authorization": f"Bearer {token}"},
    )
    assert again.status_code == 404
    # The fake object store is the service's own delete path, not a DB flag.
    assert database.objects == {}


def test_withdrawing_consent_mid_call_keeps_metrics_and_drops_audio(client):
    token = mint_token()
    grant_consent(client, token)
    ws, _opening = open_call(client, token=token, recording=True, consent=True)
    with closing(ws):
        speak_one_turn(ws)
        withdraw_consent(client, token)
        end_call(ws)
    rows = list(database.sessions.values())
    assert len(rows) == 1
    assert rows[0]["recording_id"] is None
    assert database.recordings == {}
    assert database.objects == {}


def test_the_same_frame_size_is_enforced(client):
    """A frame that is not exactly 1,024 bytes closes with 1008."""
    ws, _opening = open_call(client)
    with closing(ws):
        ws.send_bytes(b"\x00" * (FRAME_BYTES - 1))
        events, close = read_until(ws, lambda _event: False, limit=20)
    assert close is not None
    assert close["code"] == 1008


def test_the_partial_turn_is_not_written_as_a_full_turn(client):
    """A turn with fewer than three words is not a completed turn."""
    token = mint_token()
    ws, _opening = open_call(client, token=token)
    with closing(ws):
        # Only a short burst and no silence: the turn never ends.
        ws.send_bytes(speech_frame())
        ws.send_json(control_event("end"))
        read_until(
            ws,
            lambda event: event.get("type") == "status"
            and event["payload"].get("state") == "ended",
        )
    rows = list(database.sessions.values())
    assert len(rows) == 1
    assert rows[0]["turn_count"] == 0


def test_ten_concurrent_calls_are_bounded_and_the_eleventh_is_refused(client):
    """The process bound is real, not only arithmetic.

    Ten live guest calls are held open. The eleventh handshake is refused
    before it is accepted (1008); no call and no memory grows for it.
    """
    connections_registry.configure(per_address=100, per_user=100, per_process=10)
    sockets = []
    try:
        for _ in range(10):
            ws, _opening = open_call(client)
            sockets.append(ws)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws/call", headers={"origin": harness.WEB_ORIGIN}
            ) as extra:
                extra.receive_json()
        assert connections_registry.counts()["connections"] == 10
    finally:
        for ws in sockets:
            with closing(ws):
                pass
        connections_registry.configure(per_address=4, per_user=2, per_process=10)


def test_the_user_cap_refuses_a_third_call_with_the_frozen_error_shape(client):
    """The account bound is announced after the token is verified."""
    connections_registry.configure(per_address=100, per_user=2, per_process=10)
    token = mint_token()
    first, _ = open_call(client, token=token)
    second, _ = open_call(client, token=token)
    try:
        ws = client.websocket_connect(
            "/ws/call", headers={"origin": harness.WEB_ORIGIN}
        )
        ws.__enter__()
        with closing(ws):
            ws.send_json(start_event(token=token))
            events, _close = read_until(
                ws, lambda event: event.get("type") == "error"
            )
            codes = [
                event["payload"]["code"]
                for event in events_of(events, "error")
                if isinstance(event.get("payload"), dict)
            ]
            _tail, close = read_until(ws, lambda _event: False, limit=10)
        assert "too_many_connections" in codes
        assert close is not None
        assert close["code"] == 1008
    finally:
        for ws in (first, second):
            with closing(ws):
                pass
        connections_registry.configure(per_address=4, per_user=2, per_process=10)
