"""The Phase 07 guards: caps, rate limits, the health endpoint and settings.

These are unit-level proofs of the bounded resources. The assembled suite
proves the same code under a real call; these tests make each arithmetic
bound exact without a browser.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from gnani_coach.conversation.connections import ConnectionRegistry
from gnani_coach.main import app, settings
from gnani_coach.observability.latency import LatencyRegistry
from gnani_coach.security import RateLimiter
from gnani_coach.settings import AppSettings


def test_the_process_cap_refuses_the_eleventh_connection() -> None:
    registry = ConnectionRegistry(per_address=100, per_user=100, per_process=10)
    assert all(registry.reserve_address(f"10.0.0.{index}") for index in range(10))
    assert registry.reserve_address("10.0.0.11") is False
    assert registry.counts()["connections"] == 10
    registry.release_address("10.0.0.3")
    assert registry.reserve_address("10.0.0.11") is True


def test_the_address_cap_is_four_and_releases_exactly_one() -> None:
    registry = ConnectionRegistry(per_address=4, per_user=100, per_process=100)
    for _ in range(4):
        assert registry.reserve_address("127.0.0.1")
    assert registry.reserve_address("127.0.0.1") is False
    assert registry.reserve_address("127.0.0.2") is True
    registry.release_address("127.0.0.1")
    assert registry.reserve_address("127.0.0.1") is True


def test_the_user_cap_is_two_and_is_independent_of_the_address() -> None:
    registry = ConnectionRegistry(per_address=100, per_user=2, per_process=100)
    assert registry.reserve_user("usr_a")
    assert registry.reserve_user("usr_a")
    assert registry.reserve_user("usr_a") is False
    assert registry.reserve_user("usr_b") is True
    registry.release_user("usr_a")
    assert registry.reserve_user("usr_a") is True


def test_the_window_refuses_after_the_limit_and_resets() -> None:
    now = [0.0]
    limiter = RateLimiter(3, window_seconds=60.0, clock=lambda: now[0])
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("b") is True
    now[0] = 60.0
    assert limiter.allow("a") is True


def test_the_latency_window_is_bounded_and_reports_numbers_only() -> None:
    registry = LatencyRegistry(window=3)
    assert registry.snapshot() == {"turns": 0, "p50Ms": 0, "p95Ms": 0}
    for value in (10, 20, 30, 40):
        registry.record(value)
    snapshot = registry.snapshot()
    assert snapshot == {"turns": 3, "p50Ms": 30, "p95Ms": 40}
    assert set(snapshot) == {"turns", "p50Ms", "p95Ms"}


def test_the_production_boundary_refuses_a_loopback_origin() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        AppSettings(
            environment="production",
            allowed_origins=["http://localhost:3000"],
        )


def test_the_production_boundary_refuses_a_key_without_a_url() -> None:
    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        AppSettings(
            environment="production",
            allowed_origins=["https://coach.example"],
            supabase={"service_role_key": "configured"},
        )


def test_the_latency_endpoint_is_hidden_without_a_configured_token(monkeypatch, client) -> None:
    monkeypatch.setattr(settings, "health_token", None)
    response = client.get("/health/latency")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_the_latency_endpoint_needs_its_bearer_token(monkeypatch, client) -> None:
    monkeypatch.setattr(settings, "health_token", SecretStr("phase07-health"))
    assert client.get("/health/latency").status_code == 401
    assert (
        client.get(
            "/health/latency", headers={"authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    response = client.get(
        "/health/latency", headers={"authorization": "Bearer phase07-health"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"turns", "p50Ms", "p95Ms"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client
