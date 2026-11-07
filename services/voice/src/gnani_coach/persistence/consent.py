"""Recording-retention consent.

Consent is a **separate decision** from the consent to process speech
live. The contract says it plainly: "Recording retention is off by default
and is a separate decision from the consent to process speech live.
Permission to keep audio is not permission to keep a transcript."

The rules this module encodes:

* a consent write records the **version** of the consent and the **time**
  of the write;
* a withdrawal stops **future** retention. It never silently deletes what
  was already retained: deletion is an explicit action with its own
  route, its own confirmation and its own audit record;
* the consent state is re-read **at write time**, so a job that was
  already in flight when the learner withdrew consent cannot write an
  audio file afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from gnani_coach.ports.types import UserId

#: The consent version this service writes and understands.
CONSENT_VERSION = "0.1"

#: The consent versions a client may send. A version this service does
#: not know is refused rather than stored: a consent record nobody can
#: interpret is worse than a rejected request.
SUPPORTED_CONSENT_VERSIONS: frozenset[str] = frozenset({CONSENT_VERSION})


def utc_now() -> datetime:
    """The current time, in UTC."""
    return datetime.now(timezone.utc)


def isoformat(moment: datetime) -> str:
    """An RFC 3339 timestamp, the format the contract uses everywhere."""
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ConsentState:
    """The current consent state of one user."""

    consent_version: str
    recording_retention_granted: bool
    recording_retention_granted_at: str | None
    updated_at: str

    @classmethod
    def not_granted(cls, *, consent_version: str = CONSENT_VERSION) -> "ConsentState":
        """The state of a user who never granted recording retention."""
        return cls(
            consent_version=consent_version,
            recording_retention_granted=False,
            recording_retention_granted_at=None,
            updated_at=isoformat(utc_now()),
        )


@runtime_checkable
class ConsentStore(Protocol):
    """The consent boundary.

    It is not one of the frozen service ports: the frozen ports describe
    the session store and the recording store, and consent is the state
    those two share.
    """

    async def get_state(self, user_id: UserId) -> ConsentState:
        """The current consent state of a user."""
        ...

    async def set_state(
        self, user_id: UserId, *, consent_version: str, granted: bool
    ) -> ConsentState:
        """Record a consent write and return the new state."""
        ...
