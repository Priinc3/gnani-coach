"""Shared setup for provider/transport tests.

Two responsibilities, both deliberate:

1. Put the repository root and this directory on ``sys.path`` so the tests
   can reach ``tools.probes`` (probe tooling lives outside the installed
   package by design — it is not importable application code).
2. Re-export the offline helpers from :mod:`_helpers` so test modules have
   one obvious import site.

Every test in this package runs **offline**: no socket, no inference, no
model download. Transport failures are exercised with ``FakeTransport``
and an obviously fake credential.

Live checks are opt-in only; see ``test_live_optional.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROVIDERS_DIR = Path(__file__).resolve().parent
# providers -> tests -> voice -> services -> <repo root>
_REPO_ROOT = _PROVIDERS_DIR.parents[3]

for _path in (str(_REPO_ROOT), str(_PROVIDERS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Re-exported so test modules import everything from one place.
from _helpers import (  # noqa: E402
    DUMMY_GEMINI_KEY,
    DUMMY_GNANI_KEY,
    run,
    stt_connected_message,
    stt_error,
    stt_transcript,
    tts_audio,
    tts_complete,
    tts_error,
    tts_start,
)

__all__ = [
    "DUMMY_GEMINI_KEY",
    "DUMMY_GNANI_KEY",
    "run",
    "stt_connected_message",
    "stt_error",
    "stt_transcript",
    "tts_audio",
    "tts_complete",
    "tts_error",
    "tts_start",
]


@pytest.fixture
def dummy_gnani_key() -> str:
    return DUMMY_GNANI_KEY


@pytest.fixture
def dummy_gemini_key() -> str:
    return DUMMY_GEMINI_KEY
