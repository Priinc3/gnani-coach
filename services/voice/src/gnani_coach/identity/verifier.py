"""The Supabase-backed identity verifier.

**Phase 06 owns this file.** It replaces the anonymous guest stub with a
real verifier, without changing the exported name ``get_identity``.

How a bearer token is verified
------------------------------

The token is **verified, never decoded and trusted**. The authority is the
Supabase Auth server:

.. code-block:: http

    GET https://<project>.supabase.co/auth/v1/user
    apikey: <publishable key>
    Authorization: Bearer <the caller's access token>

A ``200`` means the Auth server accepted the token; anything else means
"not verified". This is the check the Supabase JWT guide documents for the
shared-secret (HS256) case
(<https://supabase.com/docs/guides/auth/jwts>, checked 2026-10-20) and it
is valid for asymmetric-key projects too. It was chosen over a local JWKS
verification because it needs **no new cryptographic dependency** and no
key-rotation handling in this process; the cost is one HTTPS round trip,
which the short-TTL cache below amortises.

Before the round trip the token is screened locally, and every screen
**rejects** (never accepts):

* a malformed token (not three dot-separated parts, or an unreadable
  payload) — the Auth server would reject it as well, but there is no
  reason to spend a round trip on it;
* an expired token (``exp`` in the past);
* a token whose audience is not ``authenticated``;
* a token whose issuer is not this project's Auth server.

The decoded claims are used **only to reject**. Acceptance always comes
from the Auth server, so a forged payload can never produce a user id.

Rules this module keeps
------------------------

* an absent, malformed, expired, wrong-audience, wrong-issuer or unknown
  token yields ``None`` — guest — and never raises;
* the returned id is opaque (``usr_`` plus the hexadecimal form of the
  subject) and is never an email, a phone number or a display name;
* a token is **never logged**, never stored and never echoed. The cache is
  keyed by a SHA-256 **hash** of the token, so the key itself is not the
  credential;
* with no Supabase URL or no key the verifier fails closed: the guest
  implementation is returned instead.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from typing import Any

import httpx

from gnani_coach.ports.identity import IdentityPort
from gnani_coach.ports.types import UserId
from gnani_coach.settings import AppSettings, load_settings

logger = logging.getLogger(__name__)

#: The longest token this module will even look at. A real Supabase access
#: token is a few hundred bytes; anything longer is refused before a
#: network call is made.
MAX_TOKEN_LENGTH = 8192

#: The audience a Supabase Auth access token carries.
EXPECTED_AUDIENCE = "authenticated"

#: How long a successful verification is trusted, in seconds.
DEFAULT_TTL_SECONDS = 60.0

#: How long a *failed* verification is remembered, in seconds. It is short
#: on purpose: a transient network failure must not lock a caller out for
#: long.
DEFAULT_NEGATIVE_TTL_SECONDS = 5.0

#: The largest number of remembered tokens. The cache is bounded so a
#: flood of distinct tokens cannot grow it without limit.
DEFAULT_MAX_ENTRIES = 256

#: The timeout of one Auth-server round trip, in seconds.
DEFAULT_TIMEOUT_SECONDS = 5.0

#: The user id verified in the current request context.
#:
#: ``verify_token`` sets it, ``current_user`` reads it. Each request runs
#: in its own task and therefore in its own context, so one caller's id
#: can never be read by another caller's request.
_current_user: ContextVar[UserId | None] = ContextVar(
    "gnani_coach_current_user", default=None
)


# ---------------------------------------------------------------------------
# the user id
# ---------------------------------------------------------------------------


def user_id_from_subject(subject: str) -> UserId | None:
    """Turn an Auth-server subject into the opaque user id.

    The subject is the Auth server's user id. It is returned in the
    ``usr_`` form the identity port documents: the prefix says "this is a
    user id", and the rest is the hexadecimal form of the subject, so the
    id is opaque and carries no personal information.

    ``None`` when the subject is not a UUID: an id that is not a UUID is
    not one of ours, and guessing would be worse than refusing.
    """
    if not isinstance(subject, str) or not subject:
        return None
    try:
        parsed = uuid.UUID(subject)
    except (ValueError, AttributeError, TypeError):
        return None
    return f"usr_{parsed.hex}"


def subject_from_user_id(user_id: str) -> str | None:
    """Turn an opaque user id back into the Auth-server subject.

    This is the inverse of :func:`user_id_from_subject` and exists so a
    store can address a row that is owned by a UUID column (which is what
    ``auth.uid()`` returns in a row-level-security policy). ``None`` when
    the id is not one of ours.
    """
    if not isinstance(user_id, str) or not user_id.startswith("usr_"):
        return None
    raw = user_id[4:]
    if len(raw) != 32:
        return None
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# the token cache
# ---------------------------------------------------------------------------


class _TokenCache:
    """A bounded, short-TTL cache of verification outcomes.

    The key is a SHA-256 hash of the token, so the credential itself is
    never held in memory by the cache. The cache is bounded, so a flood of
    distinct tokens cannot grow it without limit.
    """

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        negative_ttl_seconds: float = DEFAULT_NEGATIVE_TTL_SECONDS,
    ) -> None:
        self._entries: dict[str, tuple[float, UserId | None]] = {}
        self._max_entries = max(1, int(max_entries))
        self._ttl_seconds = float(ttl_seconds)
        self._negative_ttl_seconds = float(negative_ttl_seconds)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> tuple[bool, UserId | None]:
        """Return ``(hit, user_id)`` for a cached key."""
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return (False, None)
            expires_at, user_id = entry
            if expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return (False, None)
            return (True, user_id)

    async def put(self, key: str, user_id: UserId | None) -> None:
        """Remember one verification outcome."""
        async with self._lock:
            now = time.monotonic()
            ttl = self._ttl_seconds if user_id is not None else self._negative_ttl_seconds
            self._entries.pop(key, None)
            self._entries[key] = (now + ttl, user_id)
            while len(self._entries) > self._max_entries:
                # ``dict`` keeps insertion order, so the first key is the
                # oldest one.
                self._entries.pop(next(iter(self._entries)))

    async def clear(self) -> None:
        """Forget everything. Used by tests."""
        async with self._lock:
            self._entries.clear()


def token_fingerprint(token: str) -> str:
    """The cache key for a token: the hex SHA-256 of its UTF-8 bytes.

    A hash, not the token. The cache never holds the credential.
    """
    return hashlib.sha256(token.encode("utf-8", "ignore")).hexdigest()


# ---------------------------------------------------------------------------
# the local screen
# ---------------------------------------------------------------------------


def decode_claims(token: str) -> dict[str, Any] | None:
    """Decode the payload of a JWT **without verifying it**.

    The result is used only to *reject* a token. It is never used to
    accept one: acceptance is the Auth server's decision. ``None`` when
    the token is not a readable three-part JWT.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
    except (binascii.Error, ValueError):
        return None
    try:
        claims = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    return claims


def _audience_is_ours(audience: Any) -> bool:
    """Whether an ``aud`` claim names the authenticated role."""
    if isinstance(audience, str):
        return audience == EXPECTED_AUDIENCE
    if isinstance(audience, list):
        return EXPECTED_AUDIENCE in audience
    return False


def _issuer_is_ours(issuer: Any, expected: str) -> bool:
    """Whether an ``iss`` claim names this project's Auth server."""
    if not isinstance(issuer, str):
        return False
    return issuer.rstrip("/") == expected.rstrip("/")


# ---------------------------------------------------------------------------
# the verifier
# ---------------------------------------------------------------------------


class SupabaseIdentity:
    """The real identity port: a bearer token becomes a user id, or nothing.

    The class never raises for a bad credential: an absent, malformed,
    expired, wrong-audience, wrong-issuer or unknown token is a *guest*,
    and a guest is a supported state.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        negative_ttl_seconds: float = DEFAULT_NEGATIVE_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._issuer = f"{self._base_url}/auth/v1"
        self._timeout = timeout_seconds
        self._cache = _TokenCache(
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
            negative_ttl_seconds=negative_ttl_seconds,
        )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            transport=transport,
            timeout=timeout_seconds,
            headers={"Accept": "application/json"},
        )

    # -- the port ---------------------------------------------------------

    async def verify_token(self, token: str | None) -> UserId | None:
        """Verify a bearer token and return the user id, or ``None``."""
        user_id = await self._verify(token)
        _current_user.set(user_id)
        return user_id

    async def current_user(self) -> UserId | None:
        """The user id verified in the current request context, or ``None``."""
        return _current_user.get()

    def cache_size(self) -> int:
        """How many verification outcomes the cache holds."""
        return len(self._cache._entries)  # noqa: SLF001 - the cache is ours

    def cache_keys(self) -> tuple[str, ...]:
        """The cache keys. They are hashes, never tokens."""
        return tuple(self._cache._entries)  # noqa: SLF001 - the cache is ours

    # -- the work ---------------------------------------------------------

    async def _verify(self, token: str | None) -> UserId | None:
        if not token or not isinstance(token, str):
            return None
        if len(token) > MAX_TOKEN_LENGTH:
            return None

        claims = decode_claims(token)
        if claims is None:
            return None
        if not self._claims_are_plausible(claims):
            return None

        key = token_fingerprint(token)
        hit, cached = await self._cache.get(key)
        if hit:
            return cached

        user_id = await self._verify_with_auth_server(token)
        await self._cache.put(key, user_id)
        return user_id

    def _claims_are_plausible(self, claims: dict[str, Any]) -> bool:
        """Screen the claims. Every check here can only *reject*."""
        expiry = claims.get("exp")
        if isinstance(expiry, (int, float)) and not isinstance(expiry, bool):
            if expiry <= time.time():
                return False
        audience = claims.get("aud")
        if audience is not None and not _audience_is_ours(audience):
            return False
        issuer = claims.get("iss")
        if issuer is not None and not _issuer_is_ours(issuer, self._issuer):
            return False
        return True

    async def _verify_with_auth_server(self, token: str) -> UserId | None:
        """Ask the Auth server whether the token is genuine."""
        url = f"{self._base_url}/auth/v1/user"
        headers = {
            "apikey": self._api_key,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        try:
            response = await self._client.get(url, headers=headers)
        except Exception:  # a transport failure is a failed verification
            logger.warning(
                "identity verification could not reach the auth server"
            )
            return None
        if response.status_code != 200:
            # A rejected token is an ordinary outcome, not an error. The
            # token itself is never logged.
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        subject = payload.get("id")
        if not isinstance(subject, str):
            return None
        return user_id_from_subject(subject)

    async def aclose(self) -> None:
        """Close the HTTP client this verifier owns."""
        if self._owns_client:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# the composition root
# ---------------------------------------------------------------------------


class GuestIdentity:
    """The anonymous guest identity.

    Every token is unverified and every caller is anonymous. A guest call
    still works: live processing does not need an account. A guest simply
    has no saved history and no retained audio, because the storage ports
    only write for an identified owner.
    """

    async def verify_token(self, token: str | None) -> UserId | None:
        """Always ``None``: no token can be verified without a provider."""
        return None

    async def current_user(self) -> UserId | None:
        """Always ``None``: the caller is a guest."""
        return None


def publishable_key_from_environment() -> str | None:
    """The Supabase publishable key, read straight from the environment.

    ADDENDUM section E: ``settings.supabase`` has no publishable-key
    field, and ``settings.py`` is Phase 03's, so the key is read here in
    the module that needs it. The Auth ``/user`` check needs it as the
    ``apikey`` header. ``None`` when it is not configured.
    """
    raw = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if raw is None:
        return None
    key = raw.strip()
    return key or None


#: The process-wide instances, so the verification cache is shared by
#: every request instead of being rebuilt per request.
_instances: dict[tuple[str, str], IdentityPort] = {}
_default_instance: IdentityPort | None = None


def _build_identity(settings: AppSettings) -> IdentityPort:
    """Build the identity port for a configuration.

    **Fail closed.** Without a Supabase URL and a key there is nothing to
    verify against, so the guest implementation is returned. A guest is
    the documented unavailable behaviour, not a failure.
    """
    url = (settings.supabase.url or "").strip()
    service_key = settings.supabase.service_role_key
    service_key_value = service_key.get_secret_value() if service_key else ""
    if not url or not service_key_value:
        return GuestIdentity()

    # The Auth ``/user`` check wants the publishable key as its ``apikey``
    # header. When it is not configured the service-role key is used
    # instead: it identifies the same project to the gateway.
    api_key = publishable_key_from_environment() or service_key_value

    key = (url, api_key)
    instance = _instances.get(key)
    if instance is None:
        instance = SupabaseIdentity(url, api_key)
        _instances[key] = instance
    return instance


def get_identity() -> IdentityPort:
    """The identity port for the current process.

    The real verifier when Supabase is configured, and the anonymous guest
    when it is not. The instance is shared by every request, so the
    verification cache is shared too.

    The signature is **empty on purpose**: this function is injected as a
    FastAPI dependency, and a parameter here would be read as a query
    parameter. Use :func:`get_identity_for` when a specific configuration
    is needed.
    """
    global _default_instance
    if _default_instance is None:
        _default_instance = _build_identity(load_settings())
    return _default_instance


def get_identity_for(settings: AppSettings) -> IdentityPort:
    """The identity port for one explicit configuration.

    Used by the tests and by any caller that needs to ask "what would the
    identity be with *this* configuration?".
    """
    return _build_identity(settings)


def reset_identity_cache() -> None:
    """Forget the process-wide instances. Used by tests."""
    global _default_instance
    _default_instance = None
    _instances.clear()
