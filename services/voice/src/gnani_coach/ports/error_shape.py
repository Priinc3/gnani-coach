"""The error shape, in one place.

Every failure the service reports to a client uses the frozen error-shape
contract (``packages/contracts/schemas/error-shape.schema.json``):

* ``code`` is a stable machine identifier, never shown to the learner;
* ``category`` is the stable machine category;
* ``message`` is plain-word, bounded and written for the learner;
* ``retryable`` is true only for genuinely transient conditions.

The frozen-but-unimplemented seam behaviour is ``not_available``: a code,
a category and a message that says the part of the service is not
available yet, with ``retryable`` false — retrying does not make a seam
exist.

Nothing here formats a secret, a provider payload or learner content into
a message.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from gnani_coach.ports.types import ErrorCategory

#: The message a frozen seam answers with. Plain-word, bounded, and true.
NOT_AVAILABLE_MESSAGE = (
    "This part of the service is not available yet. Nothing was saved."
)


def new_correlation_id() -> str:
    """A fresh opaque correlation id (``cor_`` + 32 lowercase hex chars)."""
    return f"cor_{uuid.uuid4().hex}"


def error_payload(
    *,
    code: str,
    category: ErrorCategory,
    message: str,
    retryable: bool,
    correlation_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, object]:
    """Build one error-shape payload."""
    moment = occurred_at or datetime.now(timezone.utc)
    return {
        "errorVersion": "0.1",
        "code": code,
        "category": category,
        "message": message[:300],
        "retryable": bool(retryable),
        "correlationId": correlation_id or new_correlation_id(),
        "occurredAt": moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def not_available_error(
    *,
    correlation_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, object]:
    """The frozen payload of a seam that is not implemented yet."""
    return error_payload(
        code="not_available",
        category="not_available",
        message=NOT_AVAILABLE_MESSAGE,
        retryable=False,
        correlation_id=correlation_id,
        occurred_at=occurred_at,
    )


def error_envelope(
    payload: dict[str, object],
    *,
    session_id: str,
    connection_id: str,
    sequence: int = 0,
    emitted_at: datetime | None = None,
) -> dict[str, object]:
    """Wrap an error payload in the frozen event envelope."""
    moment = emitted_at or datetime.now(timezone.utc)
    return {
        "envelopeVersion": "0.1",
        "direction": "server_to_client",
        "type": "error",
        "sessionId": session_id,
        "connectionId": connection_id,
        "roundId": None,
        "turnId": None,
        "sequence": sequence,
        "sampleTimeMs": None,
        "emittedAt": moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": payload,
    }
