"""Opt-in live latency harness (Phase 07 E; Phase 08 and the final test).

Skipped unless **all** of these are configured:

    GNANI_LIVE_TESTS=1
    GNANI_API_KEY=...
    GEMINI_API_KEY=...
    GEMINI_MODEL=...

It drives the **real** speech and reasoning providers through the real
runtime and measures, per turn,

    end of the learner's turn  ->  first coach audio byte

for 30 turns, then prints p50/p95 and writes a JSON file. Nothing here runs
in the default suite: a live call is billable and needs credentials.

What is still synthetic: the "learner" audio is synthesised by the live TTS
provider and replayed as frames, not captured from a microphone. The
number therefore includes the model and the first TTS chunk, but not a real
browser, a real microphone or the public network. Say so when quoting it.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from pathlib import Path

import pytest

ENABLED = (
    os.environ.get("GNANI_LIVE_TESTS") == "1"
    and bool(os.environ.get("GNANI_API_KEY", "").strip())
    and bool(os.environ.get("GEMINI_API_KEY", "").strip())
    and bool(os.environ.get("GEMINI_MODEL", "").strip())
)

pytestmark = pytest.mark.skipif(
    not ENABLED,
    reason=(
        "opt-in live harness: set GNANI_LIVE_TESTS=1, GNANI_API_KEY, "
        "GEMINI_API_KEY and GEMINI_MODEL"
    ),
)

TURNS = 30
FRAME_BYTES = 1024
SENTENCE = "I practised describing my weekend to a friend."


def _start_event() -> dict:
    return {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": "start",
        "sessionId": None,
        "connectionId": None,
        "roundId": None,
        "turnId": None,
        "sequence": 0,
        "sampleTimeMs": None,
        "emittedAt": "2026-10-23T00:00:00Z",
        "payload": {
            "audio": {
                "sampleRateHz": 16000,
                "channels": 1,
                "sampleFormat": "s16le",
            },
            "settings": {
                "settingsVersion": "0.1",
                "practiceLanguageId": "english",
                "coachingLanguageId": "english",
                "scenarioId": "everyday",
                "level": "beginner",
                "coachingRoundTurns": 4,
                "sessionLimitSeconds": 600,
                "recordingRetention": False,
                "consent": {
                    "consentVersion": "0.1",
                    "recordingRetentionGranted": False,
                    "recordingRetentionGrantedAt": None,
                },
            },
        },
    }


def _control(kind: str, payload: dict | None = None) -> dict:
    return {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": kind,
        "sessionId": None,
        "connectionId": None,
        "roundId": None,
        "turnId": None,
        "sequence": 0,
        "sampleTimeMs": None,
        "emittedAt": "2026-10-23T00:00:00Z",
        "payload": payload or {},
    }


def _frames(pcm: bytes) -> list[bytes]:
    usable = len(pcm) - (len(pcm) % FRAME_BYTES)
    return [pcm[index : index + FRAME_BYTES] for index in range(0, usable, FRAME_BYTES)]


async def _learner_audio() -> bytes:
    """Synthesise the learner line with the live TTS port, once."""
    import importlib

    settings = importlib.import_module("gnani_coach.settings").load_settings()
    providers_module = importlib.import_module("gnani_coach.conversation.providers")
    providers = providers_module.build_call_providers(
        settings, practice_language_id="english"
    )
    assert providers is not None, "the live providers did not build"
    from gnani_coach.ports.text_to_speech import TtsOpenRequest

    session = providers.tts.open_session(
        TtsOpenRequest(
            text=SENTENCE,
            voice=providers.tts_voice,
            model=providers.tts_model,
            language=providers.tts_language,
        )
    )
    chunks = await session.synthesize()
    await session.aclose(reason="harness")
    return b"".join(chunk.data for chunk in chunks)


def test_the_live_latency_harness_runs_thirty_turns(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from gnani_coach.main import app

    pcm = asyncio.run(_learner_audio())
    frames = _frames(pcm)
    assert frames, "the live synthesiser returned no audio"
    silence = [b"\x00" * FRAME_BYTES for _ in range(45)]

    samples: list[float] = []
    with TestClient(app) as client:
        with client.websocket_connect("/ws/call") as socket:
            socket.send_json(_start_event())
            # Wait for listening.
            while True:
                message = socket.receive()
                if message.get("type") == "websocket.close":
                    pytest.fail("the live call closed before it started")
                if message.get("text"):
                    event = json.loads(message["text"])
                    if (
                        event.get("type") == "status"
                        and event["payload"].get("state") == "listening"
                    ):
                        break

            for _ in range(TURNS):
                for frame in frames:
                    socket.send_bytes(frame)
                for frame in silence:
                    socket.send_bytes(frame)
                ended_at = time.monotonic()
                first_audio_at: float | None = None
                while True:
                    message = socket.receive()
                    if message.get("type") == "websocket.close":
                        pytest.fail("the live call closed during a turn")
                    if message.get("bytes") is not None:
                        if first_audio_at is None:
                            first_audio_at = time.monotonic()
                        continue
                    text = message.get("text")
                    if not text:
                        continue
                    event = json.loads(text)
                    if event.get("type") == "round_feedback":
                        # Keep the call going across the round boundary.
                        socket.send_json(
                            _control(
                                "coaching_choice", {"choice": "keep_talking"}
                            )
                        )
                    if (
                        event.get("type") == "status"
                        and event["payload"].get("state") == "listening"
                        and first_audio_at is not None
                    ):
                        break
                assert first_audio_at is not None, "no coach audio arrived"
                samples.append((first_audio_at - ended_at) * 1000.0)
                # Let the coach's audio finish before the next turn.
                time.sleep(0.2)

    assert len(samples) == TURNS
    p50 = statistics.median(samples)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    evidence = {
        "label": "live providers; synthetic learner audio; not a real browser or microphone",
        "turns": TURNS,
        "unit": "milliseconds",
        "definition": "end of the replayed learner turn to the first coach audio byte",
        "samplesMs": [round(sample, 1) for sample in samples],
        "p50Ms": round(p50, 1),
        "p95Ms": round(p95, 1),
        "maxMs": round(max(samples), 1),
    }
    output = tmp_path / "live-latency.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
