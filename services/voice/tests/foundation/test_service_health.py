"""Startup and health-endpoint behavior of the foundation skeleton.

Health proves process readiness only. It must contain no configuration values
and must not expose any live-capability route.
"""

from fastapi.testclient import TestClient

from gnani_coach.main import app

EXPECTED_HEALTH_BODY = {
    "status": "ok",
    "service": "gnani-coach-voice",
    "version": "0.1.0",
    "phase": "foundation",
    "liveCallingImplemented": False,
    "detail": (
        "Process readiness only. No live provider connection is implemented or verified."
    ),
}


def test_app_starts_without_provider_credentials() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == EXPECTED_HEALTH_BODY


def test_startup_parses_the_configuration_boundary() -> None:
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert hasattr(app.state, "settings")


def test_health_is_the_only_route() -> None:
    schema = app.openapi()
    assert sorted(schema["paths"].keys()) == ["/health"]


def test_health_accepts_get_only() -> None:
    with TestClient(app) as client:
        assert client.post("/health").status_code == 405


def test_health_leaks_no_configuration_values() -> None:
    with TestClient(app) as client:
        raw = client.get("/health").text.lower()
    for needle in ("wss://", "https://", "supabase", "gnani_api", "gemini", "token", "secret"):
        assert needle not in raw
