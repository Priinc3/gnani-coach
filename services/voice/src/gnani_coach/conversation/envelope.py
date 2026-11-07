"""Opaque identifiers and the per-connection event envelope.

The id prefixes and the clock rules are frozen in
``docs/contracts/call-transport.md`` §3:

* ``ses_`` — one practice session;
* ``con_`` — one transport connection (a reconnect gets a new one, so
  stale events can be fenced);
* ``rnd_`` — one coaching round;
* ``trn_`` — one conversational turn.

Two clocks, never mixed:

* ``sampleTimeMs`` — the position on the **learner-audio sample clock**
  when the event's content occurred, when that is known. It is the only
  clock that may anchor an evidence span.
* ``emittedAt`` — the producer's wall clock. It is not a word timing and
  not an alignment.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from gnani_coach.ports.types import ConnectionId, RoundId, SessionId, TurnId


def new_session_id() -> SessionId:
    """A fresh session id (``ses_`` + 16 lowercase hex chars)."""
    return f"ses_{secrets.token_hex(8)}"


def new_connection_id() -> ConnectionId:
    """A fresh connection id (``con_`` + 16 lowercase hex chars)."""
    return f"con_{secrets.token_hex(8)}"


def new_round_id() -> RoundId:
    """A fresh round id (``rnd_`` + 16 lowercase hex chars)."""
    return f"rnd_{secrets.token_hex(8)}"


def new_turn_id() -> TurnId:
    """A fresh turn id (``trn_`` + 16 lowercase hex chars)."""
    return f"trn_{secrets.token_hex(8)}"


def utc_now_iso() -> str:
    """The wall clock, in the contract's ISO-8601 ``...Z`` spelling."""
    moment = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return moment


def server_envelope(
    event_type: str,
    payload: dict[str, Any],
    *,
    session_id: SessionId,
    connection_id: ConnectionId,
    sequence: int,
    round_id: RoundId | None = None,
    turn_id: TurnId | None = None,
    sample_time_ms: int | None = None,
    emitted_at: str | None = None,
) -> dict[str, Any]:
    """Build one server-to-client envelope.

    The shape is the frozen ``event-envelope`` v0.1 object: every field is
    present, ``direction`` is always ``server_to_client`` and ``sequence``
    is the producer's monotonic per-connection counter.
    """
    return {
        "envelopeVersion": "0.1",
        "direction": "server_to_client",
        "type": event_type,
        "sessionId": session_id,
        "connectionId": connection_id,
        "roundId": round_id,
        "turnId": turn_id,
        "sequence": sequence,
        "sampleTimeMs": sample_time_ms,
        "emittedAt": emitted_at or utc_now_iso(),
        "payload": payload,
    }
