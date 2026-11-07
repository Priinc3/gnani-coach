"""Shared setup for the persistence tests.

The test directory goes on ``sys.path`` so a test module can import the
fakes and the shared names with a plain import. The shared names live in
:mod:`phase06_support`, **not** in this file: a test module that does
``from conftest import ...`` picks up whichever ``conftest`` was
imported first, and this repository has several of them.

Nothing here reaches the network: the Supabase HTTP API is faked, the
stores are the in-memory ones with the semantics of the real ones, and
the tokens are obviously fake sentinels.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gnani_coach.identity import get_identity
from gnani_coach.main import app

_PERSISTENCE_DIR = Path(__file__).resolve().parent
#: persistence -> tests -> voice -> services -> <repo root>
_REPO_ROOT = _PERSISTENCE_DIR.parents[3]

if str(_PERSISTENCE_DIR) not in sys.path:
    sys.path.insert(0, str(_PERSISTENCE_DIR))

from phase06_support import (  # noqa: E402
    Harness,
    FakeIdentity,
    TOKEN_A,
    TOKEN_B,
    USER_A,
)

# The package re-exports the APIRouter under the name ``router``, so the
# module object has to be taken from ``sys.modules`` to be able to
# monkeypatch the store accessors the routes call.
import gnani_coach.persistence.router  # noqa: E402

persistence_router = sys.modules["gnani_coach.persistence.router"]


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Harness:
    """A booted service with the in-memory stores wired in."""
    from gnani_coach.persistence.stores.memory import (
        InMemoryConsentStore,
        InMemoryRecordingStore,
        InMemorySessionStore,
    )

    consent = InMemoryConsentStore()
    sessions = InMemorySessionStore()
    recordings = InMemoryRecordingStore(consent)

    monkeypatch.setattr(persistence_router, "get_session_store", lambda: sessions)
    monkeypatch.setattr(persistence_router, "get_recording_store", lambda: recordings)
    monkeypatch.setattr(persistence_router, "get_consent_store", lambda: consent)

    app.dependency_overrides[get_identity] = lambda: FakeIdentity(
        {TOKEN_A: USER_A, TOKEN_B: TOKEN_B}
    )
    with TestClient(app) as client:
        yield Harness(
            client=client, consent=consent, sessions=sessions, recordings=recordings
        )
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def contracts_dir() -> Path:
    """The shared contract directory (read-only)."""
    return _REPO_ROOT / "packages" / "contracts"


@pytest.fixture(scope="session")
def error_shape_schema(contracts_dir: Path) -> dict:
    """The frozen error shape."""
    return json.loads(
        (contracts_dir / "schemas" / "error-shape.schema.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="session")
def durable_metrics_schema(contracts_dir: Path) -> dict:
    """The frozen durable-metrics schema."""
    return json.loads(
        (contracts_dir / "schemas" / "durable-metrics.schema.json").read_text(
            encoding="utf-8"
        )
    )
