"""Shared paths for the Phase 01 foundation tests.

The contracts live in the npm workspace at ``packages/contracts`` and are the
exact same files the web side validates with Ajv; see
``packages/contracts/scripts/test-examples.mjs``.
"""

from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "packages" / "contracts" / "schemas").is_dir():
            return candidate
    raise RuntimeError(
        "repository root not found (no packages/contracts/schemas above "
        f"{start})"
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _find_repo_root(Path(__file__).resolve())


@pytest.fixture(scope="session")
def contracts_dir(repo_root: Path) -> Path:
    return repo_root / "packages" / "contracts"
