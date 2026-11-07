"""Boot the real voice app against the fake providers for Python tests.

This is the same assembly as ``launcher.py``: a fake Supabase HTTP service,
the fake speech/reasoning/analysis ports, and the **real** FastAPI app with
its real lifespan, runtime, router and stores. No live provider is
contacted and no credential is read.

Run this directory with its own configuration root so the parent
integration conftest does not import the app before the environment is
set::

    uv run --project services/voice python -m pytest \
        tests/integration/assembled --confcutdir=tests/integration/assembled
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import io
import json
import secrets
import struct
import sys
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

import harness

harness.configure_environment()

from fake_supabase import (  # noqa: E402 - after the environment
    TEST_ISSUER,
    TEST_JWT_SECRET,
    FakeDatabase,
    start_fake_supabase,
)

#: A test fixture secret for the in-process fake, never a credential.
database = FakeDatabase()
_supabase = start_fake_supabase(database, port=harness.FAKE_SUPABASE_PORT)

fake_stack = harness.patch_ports()

from fastapi.testclient import TestClient  # noqa: E402

from gnani_coach.main import app  # noqa: E402

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"

FRAME_BYTES = 1024
SPEECH_FRAMES = 42
SILENCE_FRAMES = 45


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_token(subject: str = USER_A, *, ttl_seconds: int = 24 * 60 * 60) -> str:
    """Mint the HS256 token the fake Auth server accepts."""
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": subject,
                "aud": "authenticated",
                "iss": TEST_ISSUER,
                "role": "authenticated",
                "iat": now,
                # A per-token nonce keeps two tokens minted in the same
                # second distinct, so a cached negative answer cannot leak
                # from one test into the next.
                "jti": secrets.token_hex(8),
                "exp": now + ttl_seconds,
            }
        ).encode()
    )
    signature = _b64url(
        hmac.new(
            TEST_JWT_SECRET.encode(),
            f"{header}.{payload}".encode(),
            hashlib.sha256,
        ).digest()
    )
    return f"{header}.{payload}.{signature}"


def start_event(
    *,
    token: str | None = None,
    recording: bool = False,
    consent: bool = False,
    session_limit_seconds: int = 600,
    practice_language_id: str = "english",
    scenario_id: str = "interview",
    custom_topic: str | None = None,
) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "settingsVersion": "0.1",
        "practiceLanguageId": practice_language_id,
        "coachingLanguageId": "english",
        "scenarioId": scenario_id,
        "level": "beginner",
        "coachingRoundTurns": 4,
        "sessionLimitSeconds": session_limit_seconds,
        "recordingRetention": recording,
        "consent": {
            "consentVersion": "0.1",
            "recordingRetentionGranted": consent,
            "recordingRetentionGrantedAt": (
                "2026-10-20T10:00:00Z" if consent else None
            ),
        },
    }
    if custom_topic is not None:
        settings["customTopic"] = {
            "topic": custom_topic,
            "persisted": False,
        }
    payload: dict[str, Any] = {
        "audio": {"sampleRateHz": 16000, "channels": 1, "sampleFormat": "s16le"},
        "settings": settings,
    }
    if token is not None:
        payload["auth"] = {"token": token}
    return {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": "start",
        "sessionId": None,
        "connectionId": None,
        "roundId": None,
        "turnId": None,
        "sequence": 0,
        "sampleTimeMs": None,
        "emittedAt": "2026-10-20T10:00:00Z",
        "payload": payload,
    }


def control_event(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": kind,
        "sessionId": None,
        "connectionId": None,
        "roundId": None,
        "turnId": None,
        "sequence": 0,
        "sampleTimeMs": None,
        "emittedAt": "2026-10-20T10:00:00Z",
        "payload": payload or {},
    }


_SPEECH_FRAME = struct.pack(
    "<512h", *(int(12000 * (1 if index % 8 < 4 else -1)) for index in range(512))
)
_SILENCE_FRAME = b"\x00" * FRAME_BYTES


def speech_frame() -> bytes:
    return _SPEECH_FRAME


def silence_frame() -> bytes:
    return _SILENCE_FRAME


def events_of(events: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == kind]


def status_states(events: list[dict[str, Any]]) -> list[str]:
    return [
        event["payload"]["state"]
        for event in events_of(events, "status")
        if isinstance(event.get("payload"), dict)
    ]


def read_until(
    ws: Any,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    limit: int = 800,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Read messages until ``predicate`` matches, or the socket closes.

    A closed socket is returned as a synthetic ``__close__`` event so the
    caller can distinguish "the service ended" from "the test gave up".
    """
    events: list[dict[str, Any]] = []
    for _ in range(limit):
        message = ws.receive()
        if message.get("type") == "websocket.close":
            return events, {"type": "__close__", "code": message.get("code")}
        if message.get("bytes") is not None:
            event = {"type": "__binary__", "data": message["bytes"]}
            events.append(event)
            if predicate(event):
                return events, None
            continue
        text = message.get("text")
        if text is None:
            continue
        event = json.loads(text)
        events.append(event)
        if predicate(event):
            return events, None
    raise AssertionError(f"no matching event after {limit} messages")


def open_call(
    client: TestClient,
    *,
    token: str | None = None,
    recording: bool = False,
    consent: bool = False,
    session_limit_seconds: int = 600,
    scenario_id: str = "interview",
    custom_topic: str | None = None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Open one call and return the socket plus its opening events."""
    ws = client.websocket_connect(
        "/ws/call", headers={"origin": harness.WEB_ORIGIN}
    )
    ws.__enter__()
    ws.send_json(
        start_event(
            token=token,
            recording=recording,
            consent=consent,
            session_limit_seconds=session_limit_seconds,
            scenario_id=scenario_id,
            custom_topic=custom_topic,
        )
    )
    events, close = read_until(
        ws,
        lambda event: event.get("type") == "status"
        and event["payload"].get("state") == "listening",
    )
    if close is not None:
        raise AssertionError(f"the call closed before it was ready: {close}")
    return ws, events


def send_frames(
    ws: Any,
    *,
    speech_frames: int = SPEECH_FRAMES,
    silence_frames: int = SILENCE_FRAMES,
) -> None:
    for _ in range(speech_frames):
        ws.send_bytes(speech_frame())
    for _ in range(silence_frames):
        ws.send_bytes(silence_frame())


def speak_one_turn(ws: Any) -> list[dict[str, Any]]:
    """Send one learner turn and read until the coach has finished it.

    The call is already ``listening`` when this is called; waiting for that
    state again would return immediately on the opening status. Thinking is
    the proof that the turn actually closed.
    """
    send_frames(ws)
    first, close = read_until(
        ws,
        lambda event: event.get("type") == "status"
        and event["payload"].get("state") == "thinking",
    )
    if close is not None:
        raise AssertionError(f"the call closed during a turn: {close}")
    second, close = read_until(
        ws,
        lambda event: event.get("type") == "status"
        and event["payload"].get("state") == "listening",
    )
    if close is not None:
        raise AssertionError(f"the call closed during a turn: {close}")
    return first + second


def end_call(ws: Any) -> list[dict[str, Any]]:
    ws.send_json(control_event("end"))
    events, close = read_until(
        ws,
        lambda event: event.get("type") == "status"
        and event["payload"].get("state") == "ended",
    )
    if close is not None:
        raise AssertionError(f"the call closed without an ended status: {close}")
    return events


@contextlib.contextmanager
def closing(ws: Any) -> Iterator[Any]:
    try:
        yield ws
    finally:
        with contextlib.suppress(Exception):
            ws.__exit__(None, None, None)


def grant_consent(client: TestClient, token: str) -> None:
    response = client.post(
        "/api/consent",
        json={"consentVersion": "0.1", "recordingRetentionGranted": True},
        headers={"authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text


def withdraw_consent(client: TestClient, token: str) -> None:
    response = client.post(
        "/api/consent",
        json={"consentVersion": "0.1", "recordingRetentionGranted": False},
        headers={"authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text


def wav_duration_seconds(data: bytes) -> float:
    import wave

    with wave.open(io.BytesIO(data), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    database.reset()
    fake_stack.BEHAVIOUR.reset()
    yield
    database.reset()
    fake_stack.BEHAVIOUR.reset()


@pytest.fixture()
def db() -> FakeDatabase:
    return database


@pytest.fixture(scope="session", autouse=True)
def _stop_fake_supabase() -> Iterator[None]:
    yield
    _supabase.shutdown()
    _supabase.server_close()


def pytest_configure(config: pytest.Config) -> None:
    if "gnani_coach.main" in sys.modules and not any(
        arg.startswith("--confcutdir=tests/integration/assembled")
        for arg in sys.argv
    ):
        raise pytest.UsageError(
            "run the assembled tests with "
            "--confcutdir=tests/integration/assembled so the app is imported "
            "after the fake environment is set"
        )
