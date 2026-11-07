"""The identity port.

One job: turn a caller's credential into a user id, or into nothing.

The rules:

* a bearer token is verified, never decoded and trusted;
* an absent, malformed, expired or unknown token yields ``None``, which
  means *guest* — it never raises and never blocks the call;
* the returned id is opaque (``usr_`` prefix) and is never an email, a
  phone number or a display name.

Guest access is a product decision, not a security hole: the guest has no
saved history and no retained audio, because the storage port only writes
for an identified owner.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gnani_coach.ports.types import UserId


@runtime_checkable
class IdentityPort(Protocol):
    """The application-facing identity boundary."""

    async def verify_token(self, token: str | None) -> UserId | None:
        """Verify a bearer token and return the user id, or ``None``."""
        ...

    async def current_user(self) -> UserId | None:
        """The user id of the current request, or ``None`` for a guest."""
        ...
