"""Shared setup for the coaching-runtime tests.

The fakes and the harness live in :mod:`phase05_support`, a uniquely
named module: a test module that does ``from conftest import ...`` picks
up *whichever* ``conftest`` was imported first, and this repository has
several of them.

Nothing here reaches the network: the recogniser, the synthesiser, the
model, the identity and the stores are all fakes.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from gnani_coach.conversation.connections import registry
from gnani_coach.conversation.runtime import CallOptions
from phase05_support import (
    FRAME_BYTES,
    FakeAnalysis,
    FakeIdentity,
    FakeReasoning,
    FakeRecordingStore,
    FakeSessionStore,
    FakeSttPort,
    FakeTtsPort,
    Harness,
    Timeout,
    build_options,
    control_event,
    is_loud,
    loud_frame,
    silent_frame,
    start_event,
)

__all__ = [
    "FRAME_BYTES",
    "FakeAnalysis",
    "FakeIdentity",
    "FakeReasoning",
    "FakeRecordingStore",
    "FakeSessionStore",
    "FakeSttPort",
    "FakeTtsPort",
    "Harness",
    "Timeout",
    "build_options",
    "control_event",
    "is_loud",
    "loud_frame",
    "silent_frame",
    "start_event",
]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_connection_registry() -> None:
    """Every test starts with an empty connection registry."""
    registry.reset()


@pytest.fixture
def fake_identity() -> FakeIdentity:
    return FakeIdentity()


@pytest.fixture
def fake_analysis() -> FakeAnalysis:
    return FakeAnalysis()


@pytest.fixture
def fake_tts() -> FakeTtsPort:
    return FakeTtsPort()


@pytest.fixture
def fake_reasoning() -> FakeReasoning:
    return FakeReasoning()


@pytest.fixture
def fake_stt() -> FakeSttPort:
    return FakeSttPort()


@pytest.fixture
def fake_session_store() -> FakeSessionStore:
    return FakeSessionStore()


@pytest.fixture
def fake_recording_store() -> FakeRecordingStore:
    return FakeRecordingStore()


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Open a call socket with the fakes wired into the real router."""
    import importlib

    from fastapi.testclient import TestClient

    from gnani_coach.main import app

    # ``gnani_coach.conversation.router`` is the APIRouter inside the
    # package namespace, so the module itself is fetched by name.
    conversation_router = importlib.import_module("gnani_coach.conversation.router")

    clients: list[TestClient] = []
    sessions: list[Any] = []

    def open(options: CallOptions, **connect_kwargs: Any) -> Harness:
        monkeypatch.setattr(
            conversation_router, "_build_options", lambda websocket: options
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        socket = client.websocket_connect("/ws/call", **connect_kwargs)
        socket.__enter__()
        sessions.append(socket)
        return Harness(socket, client)

    yield open

    for socket in sessions:
        with contextlib.suppress(Exception):
            socket.__exit__(None, None, None)
    for client in clients:
        with contextlib.suppress(Exception):
            client.__exit__(None, None, None)
