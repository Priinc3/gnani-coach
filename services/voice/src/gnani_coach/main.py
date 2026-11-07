"""HTTP entry point for the voice service.

What exists today (Phase 03, contract freeze):

* ``GET /health`` — process readiness only, unchanged since Phase 01;
* ``WS  /ws/call`` — the conversation socket, mounted from
  ``gnani_coach.conversation.router`` (Phase 05 owns the implementation;
  the mounted stub answers with the frozen ``not_available`` behaviour);
* ``GET  /api/history``, ``POST /api/consent`` and
  ``GET/DELETE /api/recordings/{recording_id}`` — mounted from
  ``gnani_coach.persistence.router`` (Phase 06 owns the implementation;
  the mounted stubs answer ``503`` with the frozen error shape).

The identity and analysis ports are injected as FastAPI dependencies.
Their implementations live in ``gnani_coach.identity`` (Phase 06) and
``gnani_coach.analysis`` (Phase 05); this module only wires them.

The placeholder routes are excluded from the generated OpenAPI document
(``include_in_schema=False``): a stub is not a published interface, and
the Phase 01 invariant that ``/health`` is the only documented route
stays true until the real implementations land.

Phase 03 FIX-1: the origin allowlist
-------------------------------------

The browser origin allowlist (``SPEAKING_COACH_ALLOWED_ORIGINS``) is one
list with two jobs: it is the CORS allowlist of the HTTP routes and the
allowlist of the WebSocket handshake. The CORS middleware is configured
with exactly that list, and the reusable check
``origin_allowed(origin)`` is re-exported here so that the seam has one
obvious import path in either place:

    from gnani_coach.ports import origin_allowed
    from gnani_coach.main import origin_allowed
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gnani_coach import __version__
from gnani_coach.analysis import get_analysis
from gnani_coach.conversation import connections
from gnani_coach.conversation.router import router as conversation_router
from gnani_coach.identity import get_identity
from gnani_coach.observability.latency import registry as latency
from gnani_coach.persistence.router import router as persistence_router
from gnani_coach.ports.analysis import AnalysisPort
from gnani_coach.ports.error_shape import error_payload
from gnani_coach.ports.identity import IdentityPort
from gnani_coach import security

# The one reusable origin check. It lives in ``gnani_coach.ports`` (the
# frozen seam package) and is re-exported here for convenience.
from gnani_coach.ports.origins import origin_allowed
from gnani_coach.settings import load_settings

__all__ = [
    "app",
    "analysis_dependency",
    "identity_dependency",
    "origin_allowed",
    "settings",
]


def identity_dependency() -> IdentityPort:
    """FastAPI dependency: the identity port for the current request.

    The implementation lives in ``gnani_coach.identity`` (Phase 06). The
    Phase 03 stub returns the anonymous guest, so a request without a
    verified token is a guest and nothing else happens.
    """
    return get_identity()


def analysis_dependency() -> AnalysisPort:
    """FastAPI dependency: the analysis port for the current process.

    The implementation lives in ``gnani_coach.analysis`` (Phase 05). The
    Phase 03 stub returns ``insufficient_evidence`` for every metric.
    """
    return get_analysis()


#: The configuration snapshot for this process.
#:
#: It is parsed **once, at import**, because the CORS middleware needs
#: the origin allowlist before the application can serve a request, and
#: a middleware cannot be added after the application has started. The
#: lifespan publishes the same object on ``app.state.settings``.
settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Publish the configuration boundary and configure the guards.

    Missing provider credentials are expected in this phase and
    must not crash startup; settings validation is centralized in
    ``gnani_coach.settings``. The settings themselves are parsed once at
    import time (see the module docstring).

    Phase 07: the connection caps and the two rate limiters are applied
    from the same settings object at startup, so an operator changes one
    environment value and both the middleware and the router agree.
    Guards are per process; a multi-worker deployment multiplies the
    effective budget by the worker count (stated in
    ``docs/operations/RUNBOOK.md``).
    """
    app.state.settings = settings
    connections.registry.configure(
        per_address=settings.max_connections_per_address,
        per_user=settings.max_connections_per_user,
        per_process=settings.max_connections_per_process,
    )
    security.configure(settings)
    app.state.latency = latency
    yield


app = FastAPI(
    title="Speaking Coach voice service",
    version=__version__,
    description=(
        "Contract-freeze build: process health, the frozen call and history "
        "seams, and the injected identity and analysis ports. The live "
        "provider path is not implemented."
    ),
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# Frozen seams. The routers are mounted here and nowhere else.
app.include_router(conversation_router)
app.include_router(persistence_router)

# The CORS middleware, configured with **exactly** the configured origin
# allowlist — the same list the WebSocket handshake is checked against.
#
# * ``allow_origins``: the allowlist, never a wildcard. The wildcard ``*``
#   is refused while the settings parse (see ``gnani_coach.settings``),
#   and the OWASP WebSocket Security Cheat Sheet asks for an explicit
#   allowlist of trusted origins.
# * ``allow_methods``: only the methods the mounted routes use — ``GET``
#   (``/health``, ``/api/history``, ``/api/recordings/{id}``), ``POST``
#   (``/api/consent``), ``DELETE`` (``/api/recordings/{id}``) and the
#   ``OPTIONS`` preflight itself.
# * ``allow_headers``: ``Authorization`` (the caller's own bearer token)
#   and ``Content-Type``. Nothing else is needed.
# * ``allow_credentials``: **off**. The history routes authenticate with a
#   bearer token in the ``Authorization`` header, never with a cookie, so
#   credentialed CORS would widen the attack surface for no benefit. With
#   credentials off the middleware echoes the exact allowed origin
#   instead of the wildcard.
#
# Sources: the FastAPI CORS documentation
# (<https://fastapi.tiangolo.com/tutorial/cors/>, checked 2026-10-20) and
# the OWASP WebSocket Security Cheat Sheet
# (<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
# checked 2026-10-20).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

@app.middleware("http")
async def http_rate_limit(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Admit a bounded number of HTTP requests per client address.

    The counter is a fixed 60-second window and lives in this process. A
    refused request is answered with the frozen ``rate_limited`` error
    shape and ``429``; nothing about the caller is echoed. The guard is a
    resource bound, not a security boundary; see ``security.py`` for the
    worker caveat and the OWASP sources.
    """
    address = request.client.host if request.client is not None else "unknown"
    if not security.http_limiter.allow(address):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=error_payload(
                code="rate_limited",
                category="rate_limited",
                message=(
                    "Too many requests arrived from this device. Please wait "
                    "a moment and try again."
                ),
                retryable=True,
            ),
        )
    return await call_next(request)


# The two injected ports, exposed as the single place a route can reach
# them. Phase 05 and Phase 06 use them as FastAPI dependencies:
#
#     @router.get("/api/history")
#     async def history(identity: IdentityPort = Depends(identity_dependency)):
#         ...
app.state.identity_dependency = identity_dependency
app.state.analysis_dependency = analysis_dependency


@app.get("/health")
def health() -> dict[str, object]:
    """Process-readiness probe.

    Contains no configuration values and proves nothing about providers:
    live calling is not implemented, so readiness is reported truthfully as
    unavailable rather than healthy or live.
    """
    return {
        "status": "ok",
        "service": "gnani-coach-voice",
        "version": __version__,
        "phase": "foundation",
        "liveCallingImplemented": False,
        "detail": (
            "Process readiness only. No live provider connection is implemented "
            "or verified."
        ),
    }


@app.get("/health/latency", include_in_schema=False)
def health_latency(request: Request):
    """Percentiles of end-of-turn to first-coach-audio latency.

    **Protected and opt-in.** The route answers ``404`` unless
    ``SPEAKING_COACH_HEALTH_TOKEN`` is configured, and it then requires
    ``Authorization: Bearer <token>``. The body is numbers only:
    ``{"turns": n, "p50Ms": x, "p95Ms": y}``. It carries no transcript, no
    reply, no user id and no session id, so it can be scraped without
    leaking learner content.

    Percentiles are nearest-rank over the last
    :data:`gnani_coach.observability.latency.WINDOW` measured turns of
    this process. A multi-worker deployment reports one worker's window;
    the caveat is stated in ``docs/operations/RUNBOOK.md``.
    """
    configured = settings.health_token
    if configured is None or not configured.get_secret_value().strip():
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_payload(
                code="not_found",
                category="invalid_request",
                message="This endpoint is not available.",
                retryable=False,
            ),
        )
    expected = configured.get_secret_value().strip()
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or presented.strip() != expected:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=error_payload(
                code="unauthenticated",
                category="unauthenticated",
                message="This endpoint needs its own access token.",
                retryable=False,
            ),
        )
    return latency.snapshot()
