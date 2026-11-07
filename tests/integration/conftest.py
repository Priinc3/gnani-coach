"""Shared fixtures for the Phase 03 integration smoke test.

The suite checks the **frozen seams**, not the product: every mounted seam
must answer with its stated unavailable behaviour, the health endpoint must
work, and the identity/analysis ports must behave as the frozen contract
says. Batch B2 extends this file with the real end-to-end call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gnani_coach.main import app


def repo_root() -> Path:
    """The repository root (the directory that holds ``packages/``)."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "packages" / "contracts" / "schemas").is_dir():
            return candidate
    raise RuntimeError("repository root not found")


@pytest.fixture(scope="session")
def contracts_dir() -> Path:
    return repo_root() / "packages" / "contracts"


@pytest.fixture(scope="session")
def client() -> TestClient:
    """A booted service: the ASGI application with its lifespan run."""
    with TestClient(app) as test_client:
        yield test_client


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
