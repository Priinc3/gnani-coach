"""The in-memory implementations of the storage ports.

They exist for two reasons:

* the G1 composition tests need a store that behaves exactly like the
  real one, with no project and no network;
* a service without a Supabase configuration still needs a coherent
  behaviour rather than a crash.

The semantics are **identical** to the Supabase-backed stores: the same
metrics-only guard, the same owner scoping, the same consent re-check at
write time, the same fence against a late write, the same expiry. A test
that passes against these stores is a statement about the behaviour, not
about the backend.

The in-memory stores are process-local. They are not a persistence
backend for production; they are the reference implementation of the
semantics.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from gnani_coach.persistence.consent import (
    CONSENT_VERSION,
    ConsentState,
    isoformat,
    utc_now,
)
from gnani_coach.persistence.errors import (
    ConsentRequiredError,
    ContentRejectedError,
    RecordingFencedError,
)
from gnani_coach.persistence.metrics import assert_metrics_only
from gnani_coach.ports.recording_store import RecordingRef
from gnani_coach.ports.session_store import SessionSummary
from gnani_coach.ports.types import RecordingId, SessionId, UserId

#: How long a retained recording lives: 30 days.
RETENTION_DAYS = 30

#: The owner of a write. The frozen port does not carry the owner in the
#: document (the durable-metrics schema has no user field and forbids
#: unknown ones), so the owner is resolved from the request context.
OwnerResolver = Callable[[], Awaitable[UserId | None]]


async def current_owner() -> UserId | None:
    """The user id verified in the current request context, or ``None``."""
    from gnani_coach.identity import get_identity

    identity = get_identity()
    return await identity.current_user()


@dataclass
class _RecordingRow:
    """One retained recording."""

    recording_id: str
    user_id: UserId
    session_id: str
    audio: bytes
    created_at: datetime
    expires_at: datetime
    duration_ms: int
    size_bytes: int
    content_type: str
    state: str = "retained"
    deleted_at: datetime | None = None


@dataclass
class InMemoryConsentStore:
    """The consent state, in this process."""

    states: dict[UserId, ConsentState] = field(default_factory=dict)

    async def get_state(self, user_id: UserId) -> ConsentState:
        return self.states.get(user_id, ConsentState.not_granted())

    async def set_state(
        self, user_id: UserId, *, consent_version: str, granted: bool
    ) -> ConsentState:
        moment = utc_now()
        state = ConsentState(
            consent_version=consent_version,
            recording_retention_granted=granted,
            recording_retention_granted_at=isoformat(moment) if granted else None,
            updated_at=isoformat(moment),
        )
        self.states[user_id] = state
        return state


class InMemorySessionStore:
    """The metrics-only session store, in this process."""

    def __init__(
        self,
        *,
        owner_resolver: OwnerResolver | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._records: dict[tuple[UserId, str], dict] = {}
        self._owner_resolver = owner_resolver or current_owner
        self._clock = clock or utc_now
        self._lock = asyncio.Lock()

    async def save_metrics(self, record: dict) -> None:
        """Persist one durable-metrics record for the current owner.

        A **guest writes nothing**: the call is a no-op, because a guest
        has no saved history. A document that carries content is refused
        loudly, because dropping it silently would lose a session.
        """
        assert_metrics_only(record)
        owner = await self._resolve_owner()
        if owner is None:
            return
        session_id = record.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ContentRejectedError("a durable record needs a session id")
        async with self._lock:
            self._records[(owner, session_id)] = dict(record)

    async def save_metrics_for(self, user_id: UserId, record: dict) -> None:
        """Persist one durable-metrics record for an explicit owner."""
        assert_metrics_only(record)
        session_id = record.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ContentRejectedError("a durable record needs a session id")
        async with self._lock:
            self._records[(user_id, session_id)] = dict(record)

    async def list_sessions(
        self, user_id: UserId, *, limit: int = 20
    ) -> list[SessionSummary]:
        """List the caller's sessions, newest first."""
        rows = [record for (owner, _), record in self._records.items() if owner == user_id]
        rows.sort(key=lambda record: str(record.get("recordedAt", "")), reverse=True)
        return [_summary(record) for record in rows[: max(0, limit)]]

    async def get_session(self, user_id: UserId, session_id: SessionId) -> dict | None:
        """Return one record, or ``None`` when it is not the caller's."""
        return self._records.get((user_id, session_id))

    async def _resolve_owner(self) -> UserId | None:
        return await self._owner_resolver()


class InMemoryRecordingStore:
    """The opt-in recording store, in this process."""

    def __init__(
        self,
        consent_store: InMemoryConsentStore | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self._consent = consent_store or InMemoryConsentStore()
        self._records: dict[str, _RecordingRow] = {}
        self._clock = clock or utc_now
        self._retention = timedelta(days=retention_days)
        self._lock = asyncio.Lock()
        # The fence. A deleted recording can never be recreated, not by a
        # late job and not by a retry of the same request.
        self._fenced_sessions: set[tuple[UserId, str]] = set()
        self._fenced_recordings: set[tuple[UserId, str]] = set()

    @property
    def consent_store(self) -> InMemoryConsentStore:
        """The consent state this store re-reads at write time."""
        return self._consent

    async def save_recording(
        self,
        user_id: UserId,
        session_id: SessionId,
        audio: bytes,
        *,
        duration_ms: int,
        content_type: str = "audio/wav",
        recording_id: RecordingId | None = None,
    ) -> RecordingRef:
        """Retain one recording for an owner who has opted in."""
        state = await self._consent.get_state(user_id)
        if not state.recording_retention_granted:
            raise ConsentRequiredError(
                "recording retention is not granted for this account"
            )

        async with self._lock:
            if (user_id, str(session_id)) in self._fenced_sessions:
                raise RecordingFencedError(
                    "the recording of this session was deleted and may not be recreated"
                )
            identifier = str(recording_id) if recording_id else f"rec_{uuid.uuid4().hex}"
            if (user_id, identifier) in self._fenced_recordings:
                raise RecordingFencedError(
                    "the recording was deleted and may not be recreated"
                )
            existing = self._records.get(identifier)
            if existing is not None:
                if existing.state == "deleted":
                    raise RecordingFencedError(
                        "the recording was deleted and may not be recreated"
                    )
                raise RecordingFencedError(
                    "a recording with this id already exists"
                )

            moment = self._clock()
            row = _RecordingRow(
                recording_id=identifier,
                user_id=user_id,
                session_id=str(session_id),
                audio=bytes(audio),
                created_at=moment,
                expires_at=moment + self._retention,
                duration_ms=int(duration_ms),
                size_bytes=len(audio),
                content_type=content_type,
            )
            self._records[identifier] = row
            return RecordingRef(
                recording_id=identifier,
                session_id=str(session_id),
                created_at=isoformat(moment),
                duration_ms=row.duration_ms,
                size_bytes=row.size_bytes,
                content_type=content_type,
            )

    async def get_recording(self, user_id: UserId, recording_id: RecordingId) -> bytes | None:
        """Read a recording, or ``None`` when it is not the caller's."""
        row = self._records.get(str(recording_id))
        if row is None or row.user_id != user_id:
            return None
        if row.state == "deleted":
            return None
        if self._clock() >= row.expires_at:
            # The expiry cleanup job would have removed it; until it runs,
            # an expired recording is already gone.
            row.state = "deleted"
            row.deleted_at = row.expires_at
            return None
        return row.audio

    async def delete_recording(self, user_id: UserId, recording_id: RecordingId) -> bool:
        """Delete a recording. ``True`` when something was deleted."""
        async with self._lock:
            row = self._records.get(str(recording_id))
            if row is None or row.user_id != user_id:
                return False
            if row.state == "deleted":
                return False
            row.state = "deleted"
            row.deleted_at = self._clock()
            self._fenced_sessions.add((user_id, row.session_id))
            self._fenced_recordings.add((user_id, row.recording_id))
            return True


def _summary(record: dict) -> SessionSummary:
    """Build the history row of one durable record.

    A summary carries numbers and controlled identifiers only. It has no
    free-text field, so a transcript or a model sentence cannot reach it.
    """
    totals = record.get("totals") if isinstance(record.get("totals"), dict) else {}
    recording_id = record.get("recordingId")
    return SessionSummary(
        session_id=str(record.get("sessionId", "")),
        recorded_at=str(record.get("recordedAt", "")),
        practice_language_id=str(record.get("practiceLanguageId", "")),
        scenario_id=str(record.get("scenarioId", "")),
        recording_id=str(recording_id) if isinstance(recording_id, str) else None,
        turn_count=int(totals.get("turnCount", 0) or 0),
        speaking_time_ms=int(totals.get("speakingTimeMs", 0) or 0),
    )


__all__ = [
    "CONSENT_VERSION",
    "RETENTION_DAYS",
    "InMemoryConsentStore",
    "InMemoryRecordingStore",
    "InMemorySessionStore",
    "OwnerResolver",
    "current_owner",
]
