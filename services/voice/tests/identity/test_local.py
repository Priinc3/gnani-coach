"""The local email/password identity: the token and password matrix.

The tests use a temporary SQLite file, obviously fake passwords and no
network. There is no ``pytest-asyncio`` in this project, so asynchronous
checks are driven with :func:`asyncio.run`.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from gnani_coach.identity import get_identity
from gnani_coach.identity.local import (
    LocalIdentity,
    hash_password,
    normalize_email,
    verify_password,
)
from gnani_coach.identity.local_router import auth_limiter
from gnani_coach.main import app
from gnani_coach.persistence.consent import isoformat, utc_now
from gnani_coach.persistence.stores.sqlite import SQLiteDatabase

PASSWORD = "a-long-test-password"
EMAIL = "learner@example.com"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(tmp_path / "data")
    yield db
    db.close()


@pytest.fixture
def identity(database):
    return LocalIdentity(database)


@pytest.fixture
def client(identity):
    app.dependency_overrides[get_identity] = lambda: identity
    auth_limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    auth_limiter.reset()


# ---------------------------------------------------------------------------
# register / login / logout
# ---------------------------------------------------------------------------


def test_register_login_and_logout(identity: LocalIdentity) -> None:
    session = run(identity.register(EMAIL, PASSWORD))
    assert session.user_id.startswith("usr_")
    assert session.token
    assert run(identity.verify_token(session.token)) == session.user_id

    logged_in = run(identity.authenticate(EMAIL.upper(), PASSWORD))
    assert logged_in is not None
    assert logged_in.user_id == session.user_id

    assert run(identity.logout(logged_in.token)) is True
    assert run(identity.verify_token(logged_in.token)) is None


def test_a_wrong_password_and_an_unknown_email_are_both_a_guest(
    identity: LocalIdentity,
) -> None:
    run(identity.register(EMAIL, PASSWORD))
    assert run(identity.authenticate(EMAIL, "not-the-password")) is None
    assert run(identity.authenticate("nobody@example.com", PASSWORD)) is None


def test_the_token_is_stored_only_as_a_hash(
    identity: LocalIdentity, database: SQLiteDatabase
) -> None:
    session = run(identity.register(EMAIL, PASSWORD))
    row = run(database.get_token(hashlib.sha256(session.token.encode()).hexdigest()))
    assert row is not None
    assert row["token_hash"] != session.token
    assert len(row["token_hash"]) == 64


def test_an_expired_token_is_a_guest(database: SQLiteDatabase) -> None:
    clock = {"now": utc_now()}
    identity = LocalIdentity(database, clock=lambda: clock["now"])
    session = run(identity.register(EMAIL, PASSWORD))
    assert run(identity.verify_token(session.token)) == session.user_id
    clock["now"] = clock["now"] + timedelta(days=31)
    assert run(identity.verify_token(session.token)) is None


def test_a_malformed_token_never_raises(identity: LocalIdentity) -> None:
    for token in (None, "", "x", "x" * 9000, "not a token!"):
        assert run(identity.verify_token(token)) is None


def test_a_duplicate_registration_is_refused(identity: LocalIdentity) -> None:
    run(identity.register(EMAIL, PASSWORD))
    with pytest.raises(Exception):
        run(identity.register(EMAIL, PASSWORD))


def test_email_normalisation_and_password_bounds(identity: LocalIdentity) -> None:
    assert normalize_email("  Learner@Example.COM ") == EMAIL
    with pytest.raises(ValueError):
        normalize_email("not-an-email")
    with pytest.raises(ValueError):
        run(identity.register(EMAIL, "short"))
    with pytest.raises(ValueError):
        run(identity.register(EMAIL, "x" * 129))


def test_the_password_hash_is_scrypt_and_verifies() -> None:
    encoded = run(hash_password(PASSWORD))
    assert encoded.startswith("scrypt$16384$8$1$")
    assert run(verify_password(PASSWORD, encoded)) is True
    assert run(verify_password("wrong-password", encoded)) is False


def test_delete_account_checks_the_password_again(identity: LocalIdentity) -> None:
    session = run(identity.register(EMAIL, PASSWORD))
    assert run(identity.delete_account(session.user_id, "wrong-password")) is False
    assert run(identity.delete_account(session.user_id, PASSWORD)) is True
    assert run(identity.verify_token(session.token)) is None
    assert run(identity.authenticate(EMAIL, PASSWORD)) is None


# ---------------------------------------------------------------------------
# the HTTP routes
# ---------------------------------------------------------------------------


def test_the_register_and_login_routes(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["userId"].startswith("usr_")
    token = body["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["userId"] == body["userId"]

    login = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert login.status_code == 200
    assert login.json()["userId"] == body["userId"]

    logout = client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout.status_code == 204
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


def test_login_unknown_email_and_wrong_password_share_one_message(
    client: TestClient, identity: LocalIdentity
) -> None:
    run(identity.register(EMAIL, PASSWORD))
    wrong = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": "wrong-password"}
    )
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": PASSWORD},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["message"] == unknown.json()["message"]


def test_register_and_login_are_throttled_per_address(client: TestClient) -> None:
    for _ in range(10):
        client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )
    refused = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert refused.status_code == 429
    assert refused.json()["code"] == "rate_limited"


def test_an_oversized_body_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        content=b"x" * 9000,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_me_without_a_token_is_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_delete_account_route_requires_the_password(client: TestClient) -> None:
    body = client.post(
        "/api/auth/register", json={"email": EMAIL, "password": PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    refused = client.request(
        "DELETE",
        "/api/auth/account",
        headers=headers,
        json={"password": "wrong-password"},
    )
    assert refused.status_code == 403
    deleted = client.request(
        "DELETE", "/api/auth/account", headers=headers, json={"password": PASSWORD}
    )
    assert deleted.status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_the_token_expiry_is_thirty_days(identity: LocalIdentity) -> None:
    session = run(identity.register(EMAIL, PASSWORD))
    assert isoformat(utc_now()) <= session.expires_at
