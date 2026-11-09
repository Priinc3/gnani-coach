"""The transport contract of ``/ws/call``, over a real in-process socket.

What is under test:

* the handshake: the origin policy, the start event, the error shape and
  the close codes;
* the frame rules: exactly 1,024 bytes, and a bounded message size;
* the sequence counter, the heartbeat, the idle close and the call cap;
* the token: a missing token is a guest, an unverifiable token is a
  guest, and a guest writes nothing.
"""

from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from gnani_coach.conversation import runtime as runtime_module
from gnani_coach.conversation.config import MAX_JSON_MESSAGE_BYTES
from phase05_support import (
    FakeAnalysis,
    FakeIdentity,
    FakeReasoning,
    FakeSessionStore,
    FakeSttPort,
    FakeTtsPort,
    Harness,
    build_options,
    control_event,
    loud_frame,
    silent_frame,
    start_event,
)

ALLOWED_ORIGIN = "http://localhost:3000"
FOREIGN_ORIGIN = "https://evil.example"


def _options(
    *,
    identity: FakeIdentity | None = None,
    analysis: FakeAnalysis | None = None,
    stt: FakeSttPort | None = None,
    tts: FakeTtsPort | None = None,
    reasoning: FakeReasoning | None = None,
    session_store: FakeSessionStore | None = None,
    **kwargs,
):
    return build_options(
        identity=identity or FakeIdentity(),
        analysis=analysis or FakeAnalysis(),
        stt=stt or FakeSttPort(),
        tts=tts or FakeTtsPort(),
        reasoning=reasoning or FakeReasoning(),
        session_store=session_store,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# the happy path
# ---------------------------------------------------------------------------


def test_the_happy_path_over_a_real_websocket(harness) -> None:
    """A call runs from the start event to the clean end."""
    options = _options()
    call = harness(options)
    try:
        first = call.next_event()
        assert first["type"] == "status"
        assert first["payload"]["state"] == "connecting"

        call.start()
        ready = call.events_until({"status"}, limit=4)
        states = [event["payload"]["state"] for event in ready if event["type"] == "status"]
        assert "ready" in states

        call.speech(8)
        call.silence(45)

        # Phase 19: an acknowledgement may arrive before the real reply, so
        # read until the coach text, then until the reply's audio.
        events = call.events_until({"coach_text"}, limit=80)
        events += call.events_until({"__binary__"}, limit=20)
        kinds = [event["type"] for event in events]
        assert "coach_text" in kinds
        assert "audio.frame.descriptor" in kinds
        assert "__binary__" in kinds

        sequences = [event["sequence"] for event in events if "sequence" in event]
        assert sequences == sorted(sequences), "the sequence must be monotonic"

        call.send(control_event("end", {"reason": "learner_ended"}))
        ended = call.wait_for_state("ended", limit=20)
        assert any(
            event["type"] == "status" and event["payload"]["state"] == "ended"
            for event in ended
        )
    finally:
        call.close()


def test_the_coach_text_carries_the_turn_id(harness) -> None:
    """Every coach event belongs to a turn."""
    options = _options()
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=60)
        coach = next(event for event in events if event["type"] == "coach_text")
        assert coach["turnId"].startswith("trn_")
        assert coach["payload"]["text"]
    finally:
        call.close()


def test_the_transcript_is_reported_to_the_client(harness) -> None:
    """A recognised segment is reported as a final transcript."""
    options = _options()
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=60)
        transcripts = [
            event for event in events if event["type"] == "transcript_final"
        ]
        assert transcripts, "the recognised segment must be reported"
        assert transcripts[0]["payload"]["text"]
    finally:
        call.close()


# ---------------------------------------------------------------------------
# the first message
# ---------------------------------------------------------------------------


def test_a_malformed_first_message_is_refused(harness) -> None:
    """A first message that is not a start event ends the call."""
    options = _options()
    call = harness(options)
    try:
        call.socket.send_text("this is not json")
        event = call.next_event()
        while event["type"] == "status":
            event = call.next_event()
        assert event["type"] == "error"
        assert event["payload"]["category"] == "invalid_request"
        assert event["payload"]["retryable"] is False
        with pytest.raises(WebSocketDisconnect) as closed:
            call.next_event()
        assert closed.value.code == 1008
    finally:
        call.close()


def test_an_oversized_first_message_is_refused(harness) -> None:
    """A first message over 16 KiB is a message-too-big close."""
    options = _options()
    call = harness(options)
    try:
        payload = json.dumps({"padding": "x" * (MAX_JSON_MESSAGE_BYTES + 10)})
        call.socket.send_text(payload)
        event = call.next_event()
        while event["type"] == "status":
            event = call.next_event()
        assert event["type"] == "error"
        assert event["payload"]["code"] == "message_too_large"
        with pytest.raises(WebSocketDisconnect) as closed:
            call.next_event()
        assert closed.value.code == 1009
    finally:
        call.close()


def test_a_binary_first_message_is_refused(harness) -> None:
    """The first message must be the start event."""
    options = _options()
    call = harness(options)
    try:
        call.socket.send_bytes(loud_frame())
        event = call.next_event()
        while event["type"] == "status":
            event = call.next_event()
        assert event["type"] == "error"
        assert event["payload"]["code"] == "invalid_start"
    finally:
        call.close()


def test_a_wrong_sample_rate_is_refused(harness) -> None:
    """Only 16 kHz is accepted in this release."""
    options = _options()
    call = harness(options)
    try:
        event = start_event()
        event["payload"]["audio"]["sampleRateHz"] = 8000
        call.socket.send_json(event)
        seen = call.next_event()
        while seen["type"] == "status":
            seen = call.next_event()
        assert seen["type"] == "error"
        assert seen["payload"]["code"] == "unsupported_audio_format"
        assert seen["payload"]["category"] == "invalid_request"
    finally:
        call.close()


def test_an_unknown_setting_is_refused(harness) -> None:
    """The settings shape is closed."""
    options = _options()
    call = harness(options)
    try:
        event = start_event()
        event["payload"]["settings"]["unexpected"] = 1
        call.socket.send_json(event)
        seen = call.next_event()
        while seen["type"] == "status":
            seen = call.next_event()
        assert seen["type"] == "error"
        assert seen["payload"]["code"] == "invalid_start"
    finally:
        call.close()


def test_a_wrong_frame_size_is_refused(harness) -> None:
    """A binary frame is exactly 1,024 bytes."""
    options = _options()
    call = harness(options)
    try:
        call.start()
        call.next_event()
        call.socket.send_bytes(b"\x00" * 512)
        seen = call.next_event()
        while seen["type"] == "status":
            seen = call.next_event()
        assert seen["type"] == "error"
        assert seen["payload"]["code"] == "invalid_frame_size"
    finally:
        call.close()


# ---------------------------------------------------------------------------
# the handshake
# ---------------------------------------------------------------------------


def test_a_foreign_origin_is_refused(harness) -> None:
    """The origin is checked before the handshake completes."""
    options = _options()
    with pytest.raises(WebSocketDisconnect) as refused:
        harness(options, headers={"origin": FOREIGN_ORIGIN})
    assert refused.value.code == 1008


def test_an_allowed_origin_opens_the_call(harness) -> None:
    """An allowlisted origin may call."""
    options = _options()
    call = harness(options, headers={"origin": ALLOWED_ORIGIN})
    try:
        assert call.next_event()["payload"]["state"] == "connecting"
    finally:
        call.close()


# ---------------------------------------------------------------------------
# the token
# ---------------------------------------------------------------------------


def test_a_guest_call_writes_nothing(harness) -> None:
    """No token means a guest, and a guest writes nothing."""
    store = FakeSessionStore()
    options = _options(session_store=store)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        call.events_until({"coach_text"}, limit=60)
        call.send(control_event("end", {"reason": "learner_ended"}))
        call.events_until({"status"}, limit=20)
    finally:
        call.close()
    assert store.records == []


def test_an_unverifiable_token_is_a_guest(harness) -> None:
    """A token that cannot be verified means a guest, not a refusal."""
    identity = FakeIdentity(valid_token="good-token")
    store = FakeSessionStore()
    options = _options(identity=identity, session_store=store)
    call = harness(options)
    try:
        call.start(token="nope")
        call.speech(8)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=60)
        assert any(event["type"] == "coach_text" for event in events)
        call.send(control_event("end", {"reason": "learner_ended"}))
        call.events_until({"status"}, limit=20)
    finally:
        call.close()
    assert identity.seen == ["nope"]
    assert store.records == []


def test_a_verified_token_is_an_account(harness) -> None:
    """A verified token reaches the metrics store."""
    identity = FakeIdentity(valid_token="good-token")
    store = FakeSessionStore()
    options = _options(identity=identity, session_store=store)
    call = harness(options)
    try:
        call.start(token="good-token")
        call.speech(8)
        call.silence(45)
        call.events_until({"coach_text"}, limit=60)
        call.send(control_event("end", {"reason": "learner_ended"}))
        call.events_until({"status"}, limit=20)
    finally:
        call.close()
    assert len(store.records) == 1


def test_a_failing_identity_continues_as_a_guest_with_a_notice(harness) -> None:
    """A verification that raises does not take the call down (Phase 07).

    The Auth server being unavailable is a guest call with a clear notice:
    the product must stay usable, and nothing is saved. This replaced the
    Phase 05 behaviour (a hard ``unauthenticated`` close) because the
    Phase 07 failure matrix requires the call to continue.
    """
    identity = FakeIdentity(raises=True)
    options = _options(identity=identity)
    call = harness(options)
    try:
        call.start(token="good-token")
        events = call.wait_for_state("ready")
        ready = [e for e in events if e.get("type") == "status"][-1]
        detail = ready["payload"].get("detail", "")
        assert detail.startswith("notice:")
        assert "guest" in detail
        assert all(event["type"] != "error" for event in events)
    finally:
        call.close()


# ---------------------------------------------------------------------------
# the deadlines
# ---------------------------------------------------------------------------


def test_the_heartbeat_arrives_when_nothing_else_is_sent(
    harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A heartbeat goes out every 15 seconds of silence."""
    monkeypatch.setattr(runtime_module, "HEARTBEAT_INTERVAL_S", 0.2)
    options = _options()
    call = harness(options)
    try:
        call.start()
        events = call.wait_for_state("heartbeat", limit=20, timeout=5.0)
        heartbeats = [
            event
            for event in events
            if event["type"] == "status"
            and event["payload"]["state"] == "heartbeat"
        ]
        assert heartbeats, "a heartbeat must arrive"
        assert "elapsedMs" not in heartbeats[0]["payload"]
    finally:
        call.close()


def test_an_idle_connection_is_closed(harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connection with no client frame is closed with an announcement."""
    monkeypatch.setattr(runtime_module, "IDLE_TIMEOUT_S", 0.3)
    options = _options()
    call = harness(options)
    try:
        call.start()
        events = call.wait_for_state("ended", limit=20, timeout=5.0)
        ended = [
            event
            for event in events
            if event["type"] == "status" and event["payload"]["state"] == "ended"
        ]
        assert ended, "the idle close must be announced"
    finally:
        call.close()


def test_the_call_cap_ends_the_call_cleanly(harness) -> None:
    """The call ends cleanly at the cap."""
    options = _options(call_cap_seconds=0.4)
    call = harness(options)
    try:
        call.start()
        events = call.wait_for_state("ended", limit=20, timeout=5.0)
        ended = [
            event
            for event in events
            if event["type"] == "status" and event["payload"]["state"] == "ended"
        ]
        assert ended, "the cap must end the call"
        assert all(event["type"] != "error" for event in events)
    finally:
        call.close()


def test_the_connection_bound_is_enforced(harness) -> None:
    """A client address may hold only a bounded number of calls."""
    from gnani_coach.conversation.connections import registry

    calls = []
    try:
        for _ in range(registry.per_address):
            calls.append(harness(_options()))
        with pytest.raises(WebSocketDisconnect) as refused:
            harness(_options())
        assert refused.value.code == 1008
    finally:
        for call in calls:
            call.close()
