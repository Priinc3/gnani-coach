"""Local email/password identity, backed by the embedded SQLite database.

The deployment has no Supabase project. This module is the whole sign-in
provider: it stores a scrypt hash of each password, issues opaque session
tokens and verifies them, and nothing else.

Password storage
----------------

The parameters are fixed by the build brief: ``hashlib.scrypt`` with
``n=2**14``, ``r=8``, ``p=1``, a 16-byte random salt and a 32-byte key.
They follow the Python documentation for :func:`hashlib.scrypt`
(https://docs.python.org/3/library/hashlib.html#hashlib.scrypt, checked
2026-11-07) and OWASP's password-storage guidance, which asks for a
memory-hard KDF, a unique salt per password and a constant-time compare
(https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html,
checked 2026-11-07).

Only one scrypt calculation runs at a time (a process-wide
``threading.Semaphore``). The box has 2 GB of RAM, and ``n=2**14, r=8``
needs about 16 MiB per calculation; serialising the work keeps a burst of
sign-ins from exhausting the box.

Token storage
-------------

A token is ``secrets.token_urlsafe(32)``. Only its SHA-256 hex digest is
stored. The token itself is never logged and never written to the
database. A token expires after 30 days and can be revoked by logout.
``verify_token`` never raises: absent, malformed, expired, revoked and
unknown tokens all return ``None`` (a guest).

Email enumeration
-----------------

Login does the same scrypt work for an unknown email as for a known one
and answers with the same plain message. Registration refuses a duplicate
with a generic message; the per-address throttle keeps the two paths from
becoming a useful oracle.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta

from gnani_coach.persistence.consent import isoformat, utc_now
from gnani_coach.persistence.stores.sqlite import (
    SQLiteDatabase,
    database_from_environment,
)
from gnani_coach.ports.identity import IdentityPort
from gnani_coach.ports.types import UserId

logger = logging.getLogger(__name__)

#: The scrypt cost parameters. See the module docstring for the sources.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_SALT_BYTES = 16
SCRYPT_KEY_BYTES = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024

#: Password length bounds.
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128

#: Email length bound and the simple shape check.
MAX_EMAIL_LENGTH = 254
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: How long a session token lives.
TOKEN_TTL_DAYS = 30

#: The longest token this module will look at.
MAX_TOKEN_LENGTH = 512

#: One scrypt calculation at a time. A thread semaphore, not an asyncio
#: one, so it survives repeated ``asyncio.run`` calls in the tests.
_HASH_SEMAPHORE = threading.Semaphore(1)

#: The user id verified in the current request context.
_current_user: ContextVar[UserId | None] = ContextVar(
    "gnani_coach_local_current_user", default=None
)


class EmailAlreadyRegisteredError(Exception):
    """A registration used an email that already has an account."""


class InvalidEmailError(ValueError):
    """The email is not a simple, usable address."""


class InvalidPasswordError(ValueError):
    """The password is outside the accepted length bounds."""


@dataclass(frozen=True)
class LocalSession:
    """The result of a successful register or login."""

    user_id: UserId
    token: str
    expires_at: str


def normalize_email(value: object) -> str:
    """Lowercase and trim an email, or raise :class:`InvalidEmailError`."""
    if not isinstance(value, str):
        raise InvalidEmailError("Enter an email address.")
    email = value.strip().lower()
    if not email or len(email) > MAX_EMAIL_LENGTH:
        raise InvalidEmailError("That email address is not valid.")
    if not _EMAIL_PATTERN.match(email):
        raise InvalidEmailError("That email address is not valid.")
    return email


def validate_password(value: object) -> str:
    """Check the password length, or raise :class:`InvalidPasswordError`."""
    if not isinstance(value, str):
        raise InvalidPasswordError("Enter a password.")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"Use a password of at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(value) > MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"Use a password of at most {MAX_PASSWORD_LENGTH} characters."
        )
    return value


def _scrypt_blocking(password: str, salt: bytes) -> bytes:
    with _HASH_SEMAPHORE:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_KEY_BYTES,
            maxmem=SCRYPT_MAXMEM,
        )


def _encode_hash(salt: bytes, key: bytes) -> str:
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}"
        f"${salt.hex()}${key.hex()}"
    )


async def hash_password(password: str) -> str:
    """Hash one password off the event loop."""
    salt = os.urandom(SCRYPT_SALT_BYTES)
    key = await asyncio.to_thread(_scrypt_blocking, password, salt)
    return _encode_hash(salt, key)


async def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against its stored hash, in constant time."""
    try:
        scheme, n, r, p, salt_hex, key_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
        if (
            int(n) != SCRYPT_N
            or int(r) != SCRYPT_R
            or int(p) != SCRYPT_P
            or len(salt) != SCRYPT_SALT_BYTES
            or len(expected) != SCRYPT_KEY_BYTES
        ):
            return False
    except (ValueError, TypeError):
        return False
    actual = await asyncio.to_thread(_scrypt_blocking, password, salt)
    return hmac.compare_digest(actual, expected)


async def _equal_work(password: str) -> None:
    """Do the work of a password check without comparing anything.

    An unknown email costs the same scrypt calculation as a known one, so
    the response time does not say whether the account exists.
    """
    await asyncio.to_thread(_scrypt_blocking, password, os.urandom(SCRYPT_SALT_BYTES))


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "ignore")).hexdigest()


def _parse_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=utc_now().tzinfo)
    return parsed


class LocalIdentity:
    """The local identity port: a token becomes a user id, or nothing."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = database
        self._clock = clock or utc_now

    @property
    def database(self) -> SQLiteDatabase:
        return self._db

    async def register(self, email: object, password: object) -> LocalSession:
        """Create an account and issue its first token."""
        normalized = normalize_email(email)
        checked = validate_password(password)
        # Hash before the uniqueness check: a duplicate costs the same
        # work as a fresh account.
        encoded = await hash_password(checked)
        user_id = f"usr_{uuid.uuid4().hex}"
        created_at = isoformat(self._clock())
        created = await self._db.create_user(
            user_id, normalized, encoded, created_at
        )
        if not created:
            raise EmailAlreadyRegisteredError(
                "that email cannot be used for a new account"
            )
        token, expires_at = await self._issue_token(user_id)
        return LocalSession(user_id=user_id, token=token, expires_at=expires_at)

    async def authenticate(self, email: object, password: object) -> LocalSession | None:
        """Check an email and password, and issue a token on success."""
        if not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
            return None
        try:
            normalized = normalize_email(email)
        except InvalidEmailError:
            # Still do the work: an invalid email must not be cheaper.
            await _equal_work(password)
            return None
        row = await self._db.get_user_by_email(normalized)
        if row is None:
            await _equal_work(password)
            return None
        if not await verify_password(password, str(row["password_hash"])):
            return None
        token, expires_at = await self._issue_token(str(row["user_id"]))
        return LocalSession(
            user_id=str(row["user_id"]), token=token, expires_at=expires_at
        )

    async def verify_token(self, token: str | None) -> UserId | None:
        """Verify a bearer token. Never raises; a bad token is a guest."""
        user_id: UserId | None = None
        if isinstance(token, str) and 0 < len(token) <= MAX_TOKEN_LENGTH:
            try:
                row = await self._db.get_token(_token_digest(token))
            except Exception:
                row = None
            if row is not None and row.get("revoked_at") is None:
                expires_at = _parse_timestamp(str(row.get("expires_at") or ""))
                if expires_at is not None and expires_at > self._clock():
                    user_id = str(row["user_id"])
        _current_user.set(user_id)
        return user_id

    async def current_user(self) -> UserId | None:
        """The user id verified in the current request context."""
        return _current_user.get()

    async def logout(self, token: str | None) -> bool:
        """Revoke one token. A missing or unknown token is not an error."""
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
            return False
        return await self._db.revoke_token(
            _token_digest(token), isoformat(self._clock())
        )

    async def get_user(self, user_id: UserId) -> dict[str, object] | None:
        """The public fields of one account, or ``None``."""
        row = await self._db.get_user(user_id)
        if row is None:
            return None
        return {"userId": row["user_id"], "email": row["email"]}

    async def delete_account(self, user_id: UserId, password: object) -> bool:
        """Delete an account, its rows and its recording files.

        The password is checked again: a stolen token alone cannot erase
        the account. ``False`` means the password was wrong or the account
        was gone.
        """
        if not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
            return False
        row = await self._db.get_user(user_id)
        if row is None:
            await _equal_work(password)
            return False
        if not await verify_password(password, str(row["password_hash"])):
            return False
        return await self._db.delete_user(user_id)

    async def _issue_token(self, user_id: UserId) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        moment = self._clock()
        expires_at = moment + timedelta(days=TOKEN_TTL_DAYS)
        await self._db.insert_token(
            _token_digest(token),
            user_id,
            isoformat(moment),
            isoformat(expires_at),
        )
        return token, isoformat(expires_at)


#: The process-wide local identity, so the current-user context and the
#: database connection are shared by every request.
_instance: LocalIdentity | None = None
_instance_lock = threading.Lock()


def local_identity_from_environment() -> IdentityPort:
    """The local identity for this process, or the guest when the DB fails.

    **Fail closed.** A database that cannot be opened turns sign-in off;
    a guest call still works. The log line names no path and no content.
    """
    from gnani_coach.identity.verifier import GuestIdentity

    database = database_from_environment()
    if database is None:
        return GuestIdentity()
    global _instance
    with _instance_lock:
        if _instance is None or _instance.database is not database:
            _instance = LocalIdentity(database)
        return _instance


def reset_local_identity() -> None:
    """Forget the process-wide local identity. Used by tests."""
    global _instance
    with _instance_lock:
        _instance = None


__all__ = [
    "EmailAlreadyRegisteredError",
    "InvalidEmailError",
    "InvalidPasswordError",
    "LocalIdentity",
    "LocalSession",
    "MAX_PASSWORD_LENGTH",
    "MIN_PASSWORD_LENGTH",
    "TOKEN_TTL_DAYS",
    "hash_password",
    "local_identity_from_environment",
    "normalize_email",
    "reset_local_identity",
    "validate_password",
    "verify_password",
]
