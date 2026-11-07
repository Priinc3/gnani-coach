"""The shared names of the Phase 05 analysis tests.

**Phase 05 owns this file.** It is a plain module (not a ``conftest``)
because a test module that does ``from conftest import ...`` picks up
*whichever* ``conftest`` was imported first, and this repository has
several of them. A uniquely named module has no such ambiguity.

The analysis is measured on **real** audio bytes, but the VAD engine is
replaceable, so the tests are deterministic: a stub engine reports the
speech regions it was told to report, and the real engine is exercised
separately for the "asset missing" and "asset present" cases.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Any

import pytest

from gnani_coach.analysis.vad import SpeechRegion, VadResult

#: The test directory goes on ``sys.path`` so a test module can import
#: this module by its own name.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def tone_frame(value: int = 8000, samples: int = 512) -> bytes:
    """One frame of a constant-amplitude s16le signal."""
    return struct.pack("<%dh" % samples, *([value] * samples))


def tone(seconds: float, *, sample_rate: int = 16000, value: int = 8000) -> bytes:
    """A constant-amplitude s16le signal of the given length."""
    count = int(seconds * sample_rate)
    return struct.pack("<%dh" % count, *([value] * count))


def silence(seconds: float, *, sample_rate: int = 16000) -> bytes:
    """Digital silence."""
    return tone(seconds, sample_rate=sample_rate, value=0)


class StubEngine:
    """A VAD engine with scripted speech regions.

    ``regions`` is a list of ``(start_ms, end_ms)`` pairs on the learner
    audio sample clock.
    """

    def __init__(self, regions: list[tuple[int, int]] | None = None) -> None:
        self.regions = regions or []
        self.calls: list[tuple[int, int]] = []

    def analyse(self, pcm: bytes, sample_rate: int) -> VadResult:
        self.calls.append((len(pcm), sample_rate))
        speech_regions = [
            SpeechRegion(
                start_sample=int(start_ms * sample_rate / 1000),
                end_sample=int(end_ms * sample_rate / 1000),
                sample_rate=sample_rate,
            )
            for start_ms, end_ms in self.regions
        ]
        return VadResult(
            regions=speech_regions,
            sample_rate=sample_rate,
            total_samples=len(pcm) // 2,
        )


class MissingEngine:
    """A VAD engine whose asset is absent: it reports nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def analyse(self, pcm: bytes, sample_rate: int) -> Any:
        self.calls.append((len(pcm), sample_rate))
        return None


@pytest.fixture
def stub_engine() -> StubEngine:
    return StubEngine()


@pytest.fixture
def missing_engine() -> MissingEngine:
    return MissingEngine()
