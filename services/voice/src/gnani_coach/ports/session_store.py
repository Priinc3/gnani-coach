"""The session-store port: metrics-only persistence.

What may be written is exactly the durable-metrics shape: numbers,
controlled identifiers and method metadata. What may never be written is
content — transcripts, quoted mistakes, model text, audio references
other than an opted-in recording id, or embeddings.

The port therefore takes the *already validated* durable record, so the
schema is the boundary: the store never has to decide what is acceptable.

Recording retention is a separate decision. A record with
``recordingId: null`` is a metrics-only record and is complete on its own;
a record with a recording id references a recording the learner opted
into.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from gnani_coach.ports.types import RecordingId, ScenarioId, SessionId, UserId


@dataclass(frozen=True)
class SessionSummary:
    """One row of the history list.

    A summary carries numbers and controlled identifiers only. It has no
    free-text field, so a transcript or a model sentence cannot reach it.
    """

    session_id: SessionId
    recorded_at: str
    practice_language_id: str
    scenario_id: ScenarioId
    recording_id: RecordingId | None
    turn_count: int
    speaking_time_ms: int


@runtime_checkable
class SessionStorePort(Protocol):
    """The application-facing metrics store."""

    async def save_metrics(self, record: dict[str, Any]) -> None:
        """Persist one durable-metrics record.

        ``record`` is the validated durable-metrics document. The store
        writes numbers and controlled identifiers; it never enriches a
        record with content.
        """
        ...

    async def list_sessions(
        self, user_id: UserId, *, limit: int = 20
    ) -> list[SessionSummary]:
        """List the caller's sessions, newest first."""
        ...

    async def get_session(self, user_id: UserId, session_id: SessionId) -> dict[str, Any] | None:
        """Return one record, or ``None`` when it is not the caller's."""
        ...
