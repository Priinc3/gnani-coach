"""The local sign-in routes: register, login, logout, me, delete account.

The routes are mounted by ``gnani_coach.main`` with one
``app.include_router(...)`` line. They are excluded from the generated
OpenAPI document, keeping the Phase 01 invariant that ``/health`` is the
only documented route.

The rules:

* the bearer token is the only credential; there are no cookies;
* register and login are throttled per client address at 10 per minute;
* a login failure is the **same plain message** for an unknown email and
  a wrong password;
* request bodies are size-capped before they are parsed;
* no token and no password is ever logged or echoed.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response

from gnani_coach.identity import get_identity
from gnani_coach.identity.local import (
    EmailAlreadyRegisteredError,
    InvalidEmailError,
    InvalidPasswordError,
    LocalIdentity,
)
from gnani_coach.ports.error_shape import error_payload, not_available_error
from gnani_coach.ports.identity import IdentityPort
from gnani_coach.security import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter()

#: The largest request body these routes read.
MAX_BODY_BYTES = 8192

#: The status of an oversized body. Written out because the named
#: constant moved between Starlette versions.
HTTP_TOO_LARGE = 413

#: Ten register/login attempts per client address per minute.
auth_limiter = RateLimiter(10)

_BEARER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,512}$")


def _error(
    status_code: int,
    *,
    code: str,
    category: str,
    message: str,
    retryable: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(
            code=code,
            category=category,  # type: ignore[arg-type]
            message=message,
            retryable=retryable,
        ),
    )


def _not_available() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=not_available_error(),
    )


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token if _BEARER_PATTERN.match(token) else None


async def _read_json_body(request: Request) -> tuple[dict | None, JSONResponse | None]:
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > MAX_BODY_BYTES:
                return None, _error(
                    HTTP_TOO_LARGE,
                    code="invalid_request",
                    category="invalid_request",
                    message="That request was too large.",
                )
        except ValueError:
            return None, _error(
                status.HTTP_400_BAD_REQUEST,
                code="invalid_request",
                category="invalid_request",
                message="That request could not be read.",
            )

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            return None, _error(
                HTTP_TOO_LARGE,
                code="invalid_request",
                category="invalid_request",
                message="That request was too large.",
            )
        chunks.append(chunk)
    if not chunks:
        return None, _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That request was missing a body.",
        )
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That request could not be read.",
        )
    if not isinstance(payload, dict):
        return None, _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That request could not be read.",
        )
    return payload, None


def _address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _throttled() -> JSONResponse:
    return _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        code="rate_limited",
        category="rate_limited",
        message="Too many attempts. Please wait a minute and try again.",
        retryable=True,
    )


def _session_body(session: object) -> dict[str, str]:
    return {
        "token": str(getattr(session, "token")),
        "userId": str(getattr(session, "user_id")),
        "expiresAt": str(getattr(session, "expires_at")),
    }


@router.post("/api/auth/register", include_in_schema=False)
async def register(
    request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """Create an account and return its first session token."""
    if not auth_limiter.allow(_address(request)):
        return _throttled()
    if not isinstance(identity, LocalIdentity):
        return _not_available()
    payload, refusal = await _read_json_body(request)
    if refusal is not None:
        return refusal
    assert payload is not None
    try:
        session = await identity.register(
            payload.get("email"), payload.get("password")
        )
    except EmailAlreadyRegisteredError:
        return _error(
            status.HTTP_409_CONFLICT,
            code="conflict",
            category="conflict",
            message="That account could not be created. Try signing in instead.",
        )
    except (InvalidEmailError, InvalidPasswordError) as error:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message=str(error),
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=_session_body(session))


@router.post("/api/auth/login", include_in_schema=False)
async def login(
    request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """Check an email and password and return a session token."""
    if not auth_limiter.allow(_address(request)):
        return _throttled()
    if not isinstance(identity, LocalIdentity):
        return _not_available()
    payload, refusal = await _read_json_body(request)
    if refusal is not None:
        return refusal
    assert payload is not None
    session = await identity.authenticate(
        payload.get("email"), payload.get("password")
    )
    if session is None:
        # The same message and the same status for an unknown email and a
        # wrong password.
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            category="unauthenticated",
            message="That email or password is not correct.",
        )
    return JSONResponse(content=_session_body(session))


@router.post("/api/auth/logout", include_in_schema=False)
async def logout(
    request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """Revoke the caller's token. Idempotent."""
    if not isinstance(identity, LocalIdentity):
        return _not_available()
    token = _bearer_token(request)
    if token is not None:
        try:
            await identity.logout(token)
        except Exception:
            # Logout must not fail the browser; the token expires anyway.
            logger.warning("a local session token could not be revoked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/auth/me", include_in_schema=False)
async def me(
    request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """The verified caller's opaque user id, or ``401`` for a guest."""
    if not isinstance(identity, LocalIdentity):
        return _not_available()
    token = _bearer_token(request)
    user_id = await identity.verify_token(token) if token else None
    if user_id is None:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            category="unauthenticated",
            message="Sign in to continue.",
        )
    return JSONResponse({"userId": user_id})


@router.delete("/api/auth/account", include_in_schema=False)
async def delete_account(
    request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """Delete the account, every row and every recording file.

    The password is required again, so a stolen token alone cannot erase
    the account.
    """
    if not isinstance(identity, LocalIdentity):
        return _not_available()
    token = _bearer_token(request)
    user_id = await identity.verify_token(token) if token else None
    if user_id is None:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            category="unauthenticated",
            message="Sign in to delete your account.",
        )
    payload, refusal = await _read_json_body(request)
    if refusal is not None:
        return refusal
    assert payload is not None
    deleted = await identity.delete_account(user_id, payload.get("password"))
    if not deleted:
        return _error(
            status.HTTP_403_FORBIDDEN,
            code="forbidden",
            category="forbidden",
            message="That password is not correct.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["auth_limiter", "router"]
