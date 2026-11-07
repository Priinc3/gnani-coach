"""A5's 20-trial stop-time measurement.

The browser test proves that the page stops the audio and that late audio
never arrives. This test measures the **service-side** stop: from the last
coach audio byte read off the fake transport to the ``status listening``
that follows the interruption.

What this number is: the fake stack (in-process TTS, in-process runtime,
in-process client). What it is **not**: the real provider or real network
target. The evidence file says so in its ``label`` field.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from conftest import (
    closing,
    end_call,
    open_call,
    read_until,
    speech_frame,
    status_states,
)

TRIALS = 20
#: A generous sanity ceiling, not a product target. The real target is
#: measured against the live providers, which this suite never calls.
SANITY_CEILING_MS = 5_000


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[rank]


def test_the_service_stops_the_coach_promptly_over_twenty_fake_trials(client):
    samples: list[float] = []

    for _ in range(TRIALS):
        ws, _opening = open_call(client)
        with closing(ws):
            for _ in range(42):
                ws.send_bytes(speech_frame())
            for _ in range(45):
                ws.send_bytes(b"\x00" * 1024)
            _events, close = read_until(
                ws,
                lambda event: event.get("type") == "status"
                and event["payload"].get("state") == "speaking",
            )
            assert close is None, "the call closed before the coach spoke"
            _events, close = read_until(
                ws, lambda event: event.get("type") == "__binary__"
            )
            assert close is None, "no coach audio byte arrived"
            last_audio_at = time.monotonic()
            # 10 frames = 320 ms of learner speech; the hang-over is
            # shorter than that, so this is an interruption, not noise.
            for _ in range(10):
                ws.send_bytes(speech_frame())
            stopped, close = read_until(
                ws,
                lambda event: event.get("type") == "status"
                and event["payload"].get("state") == "listening",
            )
            assert close is None, "the call closed during the interruption"
            elapsed_ms = (time.monotonic() - last_audio_at) * 1000.0
            samples.append(elapsed_ms)
            assert "listening" in status_states(stopped)
            ended = end_call(ws)
            assert "ended" in status_states(ended)

    assert len(samples) == TRIALS
    assert all(sample >= 0 for sample in samples)
    p95 = _percentile(samples, 0.95)
    assert p95 < SANITY_CEILING_MS, f"p95 {p95:.0f} ms exceeds the sanity ceiling"

    # The evidence file is what REPORT.md cites. It is deliberately explicit
    # that this is the fake stack, not the real target.
    evidence = {
        "label": "fake stack; not the real target",
        "trials": TRIALS,
        "unit": "milliseconds",
        "definition": (
            "last coach audio byte read off the fake transport to the "
            "status listening that follows the interruption"
        ),
        "samplesMs": [round(sample, 1) for sample in samples],
        "p50Ms": round(statistics.median(samples), 1),
        "p95Ms": round(p95, 1),
        "maxMs": round(max(samples), 1),
        "sanityCeilingMs": SANITY_CEILING_MS,
    }
    path = (
        Path(__file__).resolve().parents[3]
        / "prompts"
        / "phase-07-resilience"
        / "evidence"
        / "interrupt-latency-20-trials.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
