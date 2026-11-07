"""The identity verifier: the token matrix and the cache.

**Phase 06 owns this file.** The fake Auth server carries obviously fake
sentinels only; no real credential is used or needed.

There is no ``pytest-asyncio`` in this project, so the asynchronous
checks are driven with :func:`asyncio.run`, the same way the Phase 03
integration suite drives them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx
import pytest

from gnani_coach.identity import (
    GuestIdentity,
    get_identity,
    get_identity_for,
    subject_from_user_id,
    user_id_from_subject,
)
from gnani_coach.identity.verifier import SupabaseIdentity, decode_claims
from gnani_coach.ports.identity import IdentityPort
from gnani_coach.settings import load_settings

from fake_auth import FAKE_SUPABASE_URL, FakeAuthServer, make_token

T = TypeVar("T")


def run(coro: Awaitable[T]) -> T:
    """Run one coroutine to completion."""
    return asyncio.run(coro)  # type: ignore[arg-type]


SUBJECT = "11111111-1111-4111-8111-111111111111"
EXPECTED_USER_ID = f"usr_{SUBJECT.replace('-', '')}"


def build_identity(server: FakeAuthServer, **kwargs: Any) -> SupabaseIdentity:
    """A verifier that talks to the fake Auth server."""
    return SupabaseIdentity(
        FAKE_SUPABASE_URL,
        "sb_fake_key_for_tests_only",
        transport=httpx.MockTransport(server.handler),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# the token matrix
# ---------------------------------------------------------------------------


def test_a_missing_token_is_a_guest() -> None:
    server = FakeAuthServer()
    identity = build_identity(server)

    async def check() -> None:
        assert await identity.verify_token(None) is None
        assert await identity.verify_token("") is None

    run(check())
    assert server.call_count == 0, "a guest must not cost a network call"


def test_a_malformed_token_is_a_guest() -> None:
    server = FakeAuthServer()
    identity = build_identity(server)

    async def check() -> None:
        for token in ("not-a-jwt", "a.b", "a.b.c.d", "....", "%%%.", "a.!!!.c"):
            assert await identity.verify_token(token) is None

    run(check())
    assert server.call_count == 0


def test_an_expired_token_is_a_guest() -> None:
    server = FakeAuthServer(valid_tokens={"expired": SUBJECT})
    identity = build_identity(server)
    token = make_token(expires_at=int(time.time()) - 60)

    async def check() -> None:
        assert await identity.verify_token(token) is None

    run(check())
    assert server.call_count == 0, "an expired token is refused before the call"


def test_a_wrong_audience_token_is_a_guest() -> None:
    server = FakeAuthServer(valid_tokens={"wrong-audience": SUBJECT})
    identity = build_identity(server)
    token = make_token(audience="somebody-else")

    async def check() -> None:
        assert await identity.verify_token(token) is None

    run(check())
    assert server.call_count == 0


def test_a_wrong_issuer_token_is_a_guest() -> None:
    server = FakeAuthServer(valid_tokens={"wrong-issuer": SUBJECT})
    identity = build_identity(server)
    token = make_token(issuer="https://somewhere-else.example/auth/v1")

    async def check() -> None:
        assert await identity.verify_token(token) is None

    run(check())
    assert server.call_count == 0


def test_a_valid_token_is_the_subject() -> None:
    token = make_token()
    server = FakeAuthServer(valid_tokens={token: SUBJECT})
    identity = build_identity(server)

    async def check() -> None:
        assert await identity.verify_token(token) == EXPECTED_USER_ID

    run(check())
    assert server.call_count == 1


def test_a_token_the_auth_server_rejects_is_a_guest() -> None:
    server = FakeAuthServer(valid_tokens={})
    identity = build_identity(server)
    token = make_token()

    async def check() -> None:
        assert await identity.verify_token(token) is None

    run(check())
    assert server.call_count == 1


def test_a_transport_failure_is_a_guest_and_not_a_crash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network in this test")

    identity = SupabaseIdentity(
        FAKE_SUPABASE_URL,
        "sb_fake_key_for_tests_only",
        transport=httpx.MockTransport(handler),
    )

    async def check() -> None:
        assert await identity.verify_token(make_token()) is None

    run(check())


def test_a_forged_payload_never_produces_a_user_id() -> None:
    """A token the Auth server does not know is a guest.

    The payload of a token is never trusted: only the Auth server decides.
    """
    server = FakeAuthServer(valid_tokens={})
    identity = build_identity(server)

    async def check() -> None:
        assert await identity.verify_token(make_token()) is None

    run(check())


def test_the_verifier_never_raises_for_a_bad_credential() -> None:
    server = FakeAuthServer(valid_tokens={})
    identity = build_identity(server)

    async def check() -> None:
        for token in (None, "", "x", "a.b.c", "x" * 9000):
            assert await identity.verify_token(token) is None

    run(check())


def test_a_token_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    token = make_token()
    server = FakeAuthServer(valid_tokens={})
    identity = build_identity(server)
    with caplog.at_level(logging.DEBUG):
        run(identity.verify_token(token))
    assert token not in caplog.text
    assert "eyJ" not in caplog.text, "no part of a token may be logged"


# ---------------------------------------------------------------------------
# the cache
# ---------------------------------------------------------------------------


def test_the_cache_is_keyed_by_a_hash_and_saves_a_round_trip() -> None:
    token = make_token()
    server = FakeAuthServer(valid_tokens={token: SUBJECT})
    identity = build_identity(server)

    async def check() -> None:
        assert await identity.verify_token(token) == EXPECTED_USER_ID
        assert await identity.verify_token(token) == EXPECTED_USER_ID

    run(check())
    assert server.call_count == 1, "the second verification is served from the cache"


def test_the_cache_holds_a_hash_and_not_the_token() -> None:
    token = make_token()
    server = FakeAuthServer(valid_tokens={token: SUBJECT})
    identity = build_identity(server)
    run(identity.verify_token(token))
    keys = list(identity.cache_keys())
    assert keys, "the cache must hold the outcome"
    for key in keys:
        assert token not in key
        assert len(key) == 64, "the key is a sha-256 hex digest"


def test_the_cache_is_bounded() -> None:
    server = FakeAuthServer(valid_tokens={})
    identity = build_identity(server, max_entries=8)

    async def check() -> None:
        for index in range(40):
            token = make_token(subject=f"{index:08d}-1111-4111-8111-111111111111")
            await identity.verify_token(token)

    run(check())
    assert identity.cache_size() <= 8


def test_a_failed_verification_is_remembered_only_briefly() -> None:
    server = FakeAuthServer(valid_tokens={})
    identity = build_identity(server, negative_ttl_seconds=30.0)
    token = make_token()

    async def check() -> None:
        assert await identity.verify_token(token) is None
        assert await identity.verify_token(token) is None

    run(check())
    assert server.call_count == 1, "a failed verification is remembered briefly too"


def test_ten_concurrent_verifications_agree() -> None:
    token = make_token()
    server = FakeAuthServer(valid_tokens={token: SUBJECT})
    identity = build_identity(server)

    async def check() -> None:
        return await asyncio.gather(*[identity.verify_token(token) for _ in range(10)])

    assert run(check()) == [EXPECTED_USER_ID] * 10


def test_concurrent_verifications_of_many_tokens_do_not_break_the_cache() -> None:
    subjects = [f"{index:08d}-1111-4111-8111-111111111111" for index in range(20)]
    tokens = [make_token(subject=subject) for subject in subjects]
    server = FakeAuthServer(valid_tokens=dict(zip(tokens, subjects)))
    identity = build_identity(server, max_entries=4)

    async def check() -> list[Any]:
        return await asyncio.gather(*[identity.verify_token(token) for token in tokens])

    results = run(check())
    assert all(result is not None for result in results)
    assert identity.cache_size() <= 4


# ---------------------------------------------------------------------------
# the user id
# ---------------------------------------------------------------------------


def test_the_user_id_is_opaque_and_round_trips() -> None:
    user_id = user_id_from_subject(SUBJECT)
    assert user_id == EXPECTED_USER_ID
    assert user_id.startswith("usr_")
    assert "@" not in user_id
    assert subject_from_user_id(user_id) == SUBJECT


def test_a_subject_that_is_not_a_uuid_is_refused() -> None:
    assert user_id_from_subject("not-a-uuid") is None
    assert user_id_from_subject("") is None
    assert user_id_from_subject("someone@example.com") is None


def test_a_user_id_that_is_not_ours_is_refused() -> None:
    assert subject_from_user_id("usr_short") is None
    assert subject_from_user_id("ses_abc123456") is None
    assert subject_from_user_id("") is None


def test_the_payload_decoder_never_verifies_anything() -> None:
    claims = decode_claims(make_token())
    assert claims is not None
    assert claims["sub"] == SUBJECT
    assert decode_claims("not-a-jwt") is None
    assert decode_claims("a.!!!.c") is None


# ---------------------------------------------------------------------------
# the composition root
# ---------------------------------------------------------------------------


def test_without_a_supabase_url_the_identity_is_the_guest(tmp_path) -> None:
    settings = load_settings(env_file=tmp_path / "missing.env")
    identity = get_identity_for(settings)
    assert isinstance(identity, GuestIdentity)
    assert isinstance(identity, IdentityPort)


def test_without_a_key_the_identity_is_the_guest(tmp_path) -> None:
    env_file = tmp_path / "url-only.env"
    env_file.write_text("SUPABASE_URL=https://fake.supabase.co\n", encoding="utf-8")
    settings = load_settings(env_file=env_file)
    identity = get_identity_for(settings)
    assert isinstance(identity, GuestIdentity)


def test_with_a_url_and_a_key_the_identity_is_the_real_one(tmp_path) -> None:
    env_file = tmp_path / "configured.env"
    env_file.write_text(
        "SUPABASE_URL=https://fake.supabase.co\n"
        "SUPABASE_SERVICE_ROLE_KEY=sb_fake_service_role_key_for_tests_only\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file=env_file)
    identity = get_identity_for(settings)
    assert isinstance(identity, SupabaseIdentity)


def test_the_process_identity_is_a_guest_without_configuration() -> None:
    identity = get_identity()

    async def check() -> None:
        assert await identity.verify_token("any-token") is None
        assert await identity.current_user() is None

    run(check())
