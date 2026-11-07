"""The origin policy — the one place that answers "may this client?".

The call socket is reachable from a browser, so the handshake has to be
checked against an explicit allowlist. The OWASP WebSocket Security
Cheat Sheet is explicit about it: "Validate the Origin header on every
handshake. Always use an explicit allowlist of trusted origins. Browsers
include this header and malicious JavaScript cannot override it."
(<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
checked 2026-10-20).

The same list governs the CORS headers of the HTTP routes, so the origin
that may call ``GET /api/history`` is exactly the origin that may open
``/ws/call``. The list itself lives in the configuration boundary
(``SPEAKING_COACH_ALLOWED_ORIGINS``); this module only owns the *rule*.

The rule, in full
-----------------

* **An ``Origin`` header that is on the allowlist → allowed.** The
  comparison is exact, after normalisation (lower-cased scheme and host,
  the default port dropped, no trailing ``/``).
* **An ``Origin`` header that is not on the allowlist → refused.** The
  socket is closed with the policy-violation code **1008** before the
  handshake completes, so a real client sees HTTP 403.
* **A malformed ``Origin`` header → refused.** A value that is not a
  plain ``http(s)`` origin cannot be trusted.
* **No ``Origin`` header at all → allowed.** A browser *always* sends
  ``Origin`` on a WebSocket handshake and JavaScript cannot remove or
  override it, so a missing header cannot come from a browser — it
  identifies a **non-browser client** (a server-side probe, a native
  client, a test client). Such a client has no ambient cookie and no
  ambient credential to steal, and the caller's own token still travels
  in the first ``start`` event, so allowing it does not weaken the
  browser threat model (cross-site WebSocket hijacking).

This module is part of the frozen seam: Phase 05's ``/ws/call`` router
calls :func:`origin_allowed` **before** ``accept()`` and keeps the same
rule.
"""

from __future__ import annotations

from gnani_coach.settings import load_settings, normalize_origin


def allowed_origins() -> tuple[str, ...]:
    """The configured origin allowlist for this process.

    The list is read from the configuration boundary on every call. The
    process environment does not change while the service runs, so this
    is always the same list the CORS middleware was built with.
    """
    return tuple(load_settings().allowed_origins)


def origin_allowed(origin: str | None) -> bool:
    """May a client with this ``Origin`` header open the call socket?

    ``origin`` is the raw header value, or ``None`` when the header is
    absent. The rules are the ones written down in the module docstring;
    in short: an allowlisted origin passes, a foreign or malformed origin
    is refused, and a missing header identifies a non-browser client and
    passes.
    """
    if origin is None or not origin.strip():
        # No Origin header: a non-browser client. See the module docstring.
        return True
    try:
        candidate = normalize_origin(origin)
    except ValueError:
        # A malformed origin is not a trusted origin.
        return False
    return candidate in allowed_origins()
