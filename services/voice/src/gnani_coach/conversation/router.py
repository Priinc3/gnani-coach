"""The conversation WebSocket — **Phase 05 owns this file**.

The router keeps the frozen seam: the export name ``router``, the path
``/ws/call`` and the origin check **before** ``accept()``. The origin
rule itself is frozen in ``docs/contracts/seams.md`` §8 and is not
re-implemented here: ``origin_allowed(...)`` is the only answer to "may
this client open the call socket?".

What the endpoint does now
--------------------------

* it refuses a foreign origin with the policy-violation close **1008**,
  before the handshake completes (so a real client sees HTTP 403);
* it refuses a connection that would exceed the per-address bound, also
  before the handshake completes;
* it accepts the socket, answers ``status connecting`` and waits for the
  ``start`` event;
* it hands the call to :class:`gnani_coach.conversation.runtime.CallRuntime`,
  which owns the state machine, the turn controller, the coaching break
  and the durable metrics.

The transport contract (event names, ids, heartbeat, stale-turn
suppression and caps) is frozen in ``docs/contracts/call-transport.md``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket

from gnani_coach import security
from gnani_coach.conversation import catalog, logging_setup
from gnani_coach.conversation.connections import registry
from gnani_coach.conversation.providers import build_call_providers
from gnani_coach.conversation.runtime import CallOptions, CallRuntime
from gnani_coach.ports.origins import origin_allowed

# Phase 19: make the call path visible in the journal at INFO. The root
# logger is at WARNING in production, so every call-path ``LOGGER.info``
# was dropped there; this configures the ``gnani_coach`` family only.
logging_setup.configure()

LOGGER = logging.getLogger("gnani_coach.conversation")

#: WebSocket close code used when the handshake is refused by the origin
#: policy (RFC 6455 §7.4.1: "policy violation"). The close is sent
#: *before* the handshake completes, so a real client sees HTTP 403.
CLOSE_POLICY_VIOLATION = 1008

router = APIRouter()


def _session_store() -> Any | None:
    """The metrics store, when Phase 06 has configured one.

    The import is lazy and a missing name is treated as "no store": the
    runtime then writes nothing rather than guessing.
    """
    try:
        from gnani_coach.persistence import get_session_store
    except ImportError:
        return None
    try:
        return get_session_store()
    except Exception:  # noqa: BLE001 - an unconfigured store is not a failure
        return None


def _recording_store() -> Any | None:
    """The recording store, when Phase 06 has configured one."""
    try:
        from gnani_coach.persistence import get_recording_store
    except ImportError:
        return None
    try:
        return get_recording_store()
    except Exception:  # noqa: BLE001 - an unconfigured store is not a failure
        return None


def _client_address(websocket: WebSocket) -> str:
    """The caller's address, for the per-address bound.

    **The host only, never the source port.** A per-address cap keyed by
    ``host:port`` would give every new socket its own bucket and bound
    nothing. The port is deliberately dropped; the host is the unit the
    OWASP resource-limit guidance means
    (<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
    checked 2026-10-23).
    """
    client = websocket.client
    if client is None:
        return "unknown"
    return str(getattr(client, "host", None) or "unknown")


def _settings(websocket: WebSocket) -> Any:
    """The configuration of the running service."""
    state = getattr(websocket.app, "state", None)
    settings = getattr(state, "settings", None)
    if settings is not None:
        return settings
    from gnani_coach.settings import load_settings

    return load_settings()


@router.websocket("/ws/call")
async def call_socket(websocket: WebSocket) -> None:
    """Accept the call socket and run the call.

    The origin is checked first: a client from an origin that is not on
    the allowlist never gets an accepted socket.
    """
    origin = websocket.headers.get("origin")
    if not origin_allowed(origin):
        await websocket.close(
            code=CLOSE_POLICY_VIOLATION, reason="origin_not_allowed"
        )
        return

    address = _client_address(websocket)
    if not security.handshake_limiter.allow(address):
        await websocket.close(
            code=CLOSE_POLICY_VIOLATION, reason="rate_limited"
        )
        return
    if not registry.reserve_address(address):
        await websocket.close(
            code=CLOSE_POLICY_VIOLATION, reason="connection_limit"
        )
        return

    try:
        await websocket.accept()
        options = _build_options(websocket)
        runtime = CallRuntime(websocket, options)
        await runtime.run()
    finally:
        registry.release_address(address)


def _consent_checker(recording_store: Any | None):
    """The write-time consent lookup, bound to the real consent store.

    The runtime calls this with the verified user id at write time, so a
    withdrawal between the ``start`` event and the end of the call stops
    the recording. When storage is not configured the caller falls back
    to the consent captured in the ``start`` event.
    """
    consent_store = getattr(recording_store, "consent_store", None)
    if consent_store is None:
        return None

    async def _check(user_id: str) -> bool:
        state = await consent_store.get_state(user_id)
        return bool(getattr(state, "recording_retention_granted", False))

    return _check


def _build_options(websocket: WebSocket) -> CallOptions:
    """The options one call needs."""
    from gnani_coach.analysis import get_analysis
    from gnani_coach.identity import get_identity

    settings = _settings(websocket)
    names = catalog.language_names()
    recording_store = _recording_store()
    return CallOptions(
        identity=get_identity(),
        analyzer=get_analysis(),
        providers=None,
        providers_factory=lambda practice_language_id: build_call_providers(
            settings, practice_language_id=practice_language_id
        ),
        practice_language=names.get("english", "English"),
        coaching_language=names.get("english", "English"),
        session_store=_session_store(),
        recording_store=recording_store,
        consent_checker=_consent_checker(recording_store),
        connections=registry,
        backchannel_enabled=bool(
            getattr(settings, "backchannel_enabled", True)
        ),
    )
