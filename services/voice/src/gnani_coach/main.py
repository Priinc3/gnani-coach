"""HTTP entry point for the Phase 01 voice-service skeleton.

This service exposes exactly one route, ``GET /health``, proving process
readiness only. No live provider connectivity is implemented or verified, and
there is deliberately no speech relay, WebSocket stub, fake authentication or
session persistence. Unimplemented live behavior fails closed by not existing.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gnani_coach import __version__
from gnani_coach.settings import load_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Parse the configuration boundary once at startup.

    Missing provider credentials are expected in this foundation phase and
    must not crash startup; settings validation is centralized in
    ``gnani_coach.settings``.
    """
    app.state.settings = load_settings()
    yield


app = FastAPI(
    title="Speaking Coach voice service (foundation skeleton)",
    version=__version__,
    description=(
        "Phase 01 skeleton: process health and the configuration boundary only. "
        "No live speech provider, relay or analysis engine is implemented."
    ),
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


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
