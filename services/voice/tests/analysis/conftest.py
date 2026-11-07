"""Shared setup for the analysis tests.

The fakes and the audio helpers live in :mod:`phase05_analysis_support`,
a uniquely named module: a test module that does ``from conftest
import ...`` picks up *whichever* ``conftest`` was imported first, and
this repository has several of them.

Nothing here reaches the network: the VAD asset is either the prepared
local file or an explicitly absent one.
"""

from __future__ import annotations

from phase05_analysis_support import (  # noqa: F401 - the fixtures are collected here
    MissingEngine,
    StubEngine,
    missing_engine,
    silence,
    stub_engine,
    tone,
    tone_frame,
)

__all__ = [
    "MissingEngine",
    "StubEngine",
    "missing_engine",
    "silence",
    "stub_engine",
    "tone",
    "tone_frame",
]
