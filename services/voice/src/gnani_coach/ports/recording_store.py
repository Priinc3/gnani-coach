"""The recording-store port: opt-in audio retention.

Recording retention is **off by default** and is a separate decision from
the consent to process speech live. This port is only reachable when the
learner explicitly allowed saving the recording for replay.

The rules the port encodes:

* audio only. A recording store never holds a transcript, a quoted
  mistake, a model sentence or an embedding;
* owner-only access. Every read and every delete is scoped to the owner,
  so another user asking for a recording id gets nothing;
* deletion is a state, not an erasure of the fact. The metadata records
  that a recording existed and when it was deleted;
* a late job must never resurrect a deleted recording. The store fences
  pending writes, and the caller must check the consent state again at
  write time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from gnani_coach.ports.types import RecordingId, SessionId, UserId


@dataclass(frozen=True)
class RecordingRef:
    """A private, opaque reference to a retained recording.

    There is no URL and no object key: a stored URL becomes a shareable
    capability.
    """

    recording_id: RecordingId
    session_id: SessionId
    created_at: str
    duration_ms: int
    size_bytes: int
    content_type: str = "audio/wav"


@runtime_checkable
class RecordingStorePort(Protocol):
    """The application-facing recording store."""

    async def save_recording(
        self,
        user_id: UserId,
        session_id: SessionId,
        audio: bytes,
        *,
        duration_ms: int,
        content_type: str = "audio/wav",
    ) -> RecordingRef:
        """Retain one recording for an owner who has opted in."""
        ...

    async def get_recording(
        self, user_id: UserId, recording_id: RecordingId
    ) -> bytes | None:
        """Read a recording, or ``None`` when it is not the caller's."""
        ...

    async def delete_recording(
        self, user_id: UserId, recording_id: RecordingId
    ) -> bool:
        """Delete a recording. ``True`` when something was deleted."""
        ...
