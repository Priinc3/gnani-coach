"""The origin allowlist, the CORS middleware and the handshake check.

Phase 03 FIX-1. The rules under test are the ones frozen in
``docs/contracts/seams.md`` §8:

* an allowlisted origin may open ``/ws/call`` and may read the CORS
  headers of the HTTP routes;
* a foreign origin may do neither — the CORS preflight is refused and
  the WebSocket handshake is refused with the policy-violation close
  code **1008**;
* the wildcard ``*`` is refused **while the settings parse**, so it can
  never reach the middleware;
* a **missing** ``Origin`` header identifies a non-browser client and is
  allowed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from gnani_coach.main import app
from gnani_coach.main import settings as app_settings
from gnani_coach.ports.origins import allowed_origins, origin_allowed
from gnani_coach.settings import load_settings, normalize_origin

#: The origin the browser sends while the web app runs on the developer
#: machine. It is the first entry of the allowlist the running service
#: was built with, so the test follows the configuration instead of
#: assuming it.
ALLOWED_ORIGIN = app_settings.allowed_origins[0]

#: An origin that is on nobody's allowlist.
FOREIGN_ORIGIN = "https://evil.example"

ALLOWED_ORIGIN_ENV = "SPEAKING_COACH_ALLOWED_ORIGINS"


def start_event(*, sample_rate_hz: int = 16000) -> dict[str, object]:
    """A minimal valid ``start`` event, except for the rate under test."""
    return {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": "start",
        "sessionId": "ses_abcdef12",
        "connectionId": "con_abcdef12",
        "sequence": 0,
        "emittedAt": "2026-10-22T00:00:00Z",
        "payload": {
            "audio": {
                "sampleRateHz": sample_rate_hz,
                "channels": 1,
                "sampleFormat": "s16le",
            },
            "settings": {
                "settingsVersion": "0.1",
                "practiceLanguageId": "english",
                "coachingLanguageId": "english",
                "scenarioId": "everyday",
                "level": "beginner",
                "coachingRoundTurns": 4,
                "sessionLimitSeconds": 60,
                "recordingRetention": False,
                "consent": {
                    "consentVersion": "0.1",
                    "recordingRetentionGranted": False,
                    "recordingRetentionGrantedAt": None,
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# the setting
# ---------------------------------------------------------------------------


def test_the_default_allowlist_is_the_local_web_origin(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Nothing configured means the local web origin only."""
    monkeypatch.delenv(ALLOWED_ORIGIN_ENV, raising=False)
    settings = load_settings(env_file=tmp_path / "missing.env")
    assert settings.allowed_origins == ["http://localhost:3000"]


def test_a_wildcard_allowlist_is_refused_while_the_settings_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``*`` never reaches the middleware: the parse fails first."""
    for value in ("*", '["*"]', "http://localhost:3000,*"):
        monkeypatch.setenv(ALLOWED_ORIGIN_ENV, value)
        with pytest.raises(ValidationError):
            load_settings()


def test_a_malformed_allowlist_is_refused_while_the_settings_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ALLOWED_ORIGIN_ENV, "not-an-origin")
    with pytest.raises(ValidationError):
        load_settings()


def test_the_allowlist_accepts_a_json_array_and_a_comma_separated_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ALLOWED_ORIGIN_ENV, '["https://a.example","https://b.example"]')
    assert load_settings().allowed_origins == ["https://a.example", "https://b.example"]

    monkeypatch.setenv(ALLOWED_ORIGIN_ENV, "https://a.example,https://b.example")
    assert load_settings().allowed_origins == ["https://a.example", "https://b.example"]


def test_the_allowlist_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    """The comparison is exact, so both sides are normalised."""
    monkeypatch.setenv(ALLOWED_ORIGIN_ENV, "HTTP://Localhost:3000/")
    assert load_settings().allowed_origins == ["http://localhost:3000"]
    assert normalize_origin("HTTP://Localhost:3000/") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# the reusable check
# ---------------------------------------------------------------------------


def test_the_check_allows_the_configured_origin() -> None:
    assert origin_allowed(ALLOWED_ORIGIN) is True
    assert allowed_origins() == tuple(app_settings.allowed_origins)


def test_the_check_refuses_a_foreign_origin() -> None:
    assert origin_allowed(FOREIGN_ORIGIN) is False


def test_the_check_refuses_a_malformed_origin() -> None:
    assert origin_allowed("not-an-origin") is False
    assert origin_allowed("http://localhost:3000/path") is False


def test_the_check_allows_a_missing_origin() -> None:
    """A browser always sends ``Origin``; a missing header is a
    non-browser client, and it is allowed."""
    assert origin_allowed(None) is True
    assert origin_allowed("") is True


def test_the_check_follows_the_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ALLOWED_ORIGIN_ENV, "https://allowed.example")
    assert origin_allowed("https://allowed.example") is True
    assert origin_allowed("http://localhost:3000") is False


# ---------------------------------------------------------------------------
# the CORS middleware
# ---------------------------------------------------------------------------


def test_an_allowed_origin_passes_the_cors_preflight(client: TestClient) -> None:
    response = client.options(
        "/api/history",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    allowed_methods = response.headers["access-control-allow-methods"]
    for method in ("GET", "POST", "DELETE"):
        assert method in allowed_methods
    assert "PUT" not in allowed_methods
    assert "PATCH" not in allowed_methods


def test_a_foreign_origin_fails_the_cors_preflight(client: TestClient) -> None:
    response = client.options(
        "/api/history",
        headers={
            "Origin": FOREIGN_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_a_foreign_origin_gets_no_cors_headers_on_a_simple_request(
    client: TestClient,
) -> None:
    """The request still runs, but the browser is not allowed to read it."""
    response = client.get("/api/history", headers={"Origin": FOREIGN_ORIGIN})
    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers


def test_the_cors_middleware_does_not_send_credentials(client: TestClient) -> None:
    """The history routes use a bearer token, never a cookie."""
    response = client.options(
        "/api/history",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-credentials" not in response.headers


# ---------------------------------------------------------------------------
# the handshake
# ---------------------------------------------------------------------------


def test_an_allowed_origin_opens_the_call_socket(client: TestClient) -> None:
    """A trusted origin is accepted and the first message is the state."""
    with client.websocket_connect("/ws/call", headers={"origin": ALLOWED_ORIGIN}) as socket:
        message = socket.receive_json()
    assert message["type"] == "status"
    assert message["payload"]["state"] == "connecting"


def test_an_allowed_origin_with_an_invalid_start_is_closed_1008(
    client: TestClient,
) -> None:
    """The handshake succeeds, but a bad first event is a policy failure."""
    with client.websocket_connect("/ws/call", headers={"origin": ALLOWED_ORIGIN}) as socket:
        assert socket.receive_json()["payload"]["state"] == "connecting"
        socket.send_json({"type": "not-a-start"})
        error = socket.receive_json()
        assert error["type"] == "error"
        assert error["payload"]["code"] == "invalid_start"
        assert error["payload"]["category"] == "invalid_request"
        assert error["payload"]["retryable"] is False
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 1008


def test_an_allowed_origin_with_a_wrong_sample_rate_is_refused(
    client: TestClient,
) -> None:
    """Only 16 kHz mono s16le is accepted, and the refusal says so."""
    with client.websocket_connect("/ws/call", headers={"origin": ALLOWED_ORIGIN}) as socket:
        assert socket.receive_json()["payload"]["state"] == "connecting"
        socket.send_json(start_event(sample_rate_hz=44100))
        error = socket.receive_json()
        assert error["type"] == "error"
        assert error["payload"]["code"] == "unsupported_audio_format"
        assert error["payload"]["category"] == "invalid_request"
        assert error["payload"]["retryable"] is False
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 1008


def test_a_foreign_origin_is_refused_the_handshake(client: TestClient) -> None:
    """The socket is never accepted: the close is a policy violation."""
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect("/ws/call", headers={"origin": FOREIGN_ORIGIN}):
            pass
    assert refused.value.code == 1008
    assert refused.value.reason == "origin_not_allowed"


def test_a_missing_origin_opens_the_call_socket(client: TestClient) -> None:
    """A non-browser client (no ``Origin`` header) is allowed."""
    with client.websocket_connect("/ws/call") as socket:
        message = socket.receive_json()
    assert message["type"] == "status"
    assert message["payload"]["state"] == "connecting"


def test_the_openapi_document_is_still_only_health() -> None:
    """The CORS middleware must not publish a route."""
    assert sorted(app.openapi()["paths"].keys()) == ["/health"]
