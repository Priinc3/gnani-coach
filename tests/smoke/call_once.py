#!/usr/bin/env python3
"""One real voice turn through the public ``/ws/call`` socket.

The learner audio is **synthetic**: a short sentence rendered once by the
live text-to-speech provider and saved to
``fixtures/synthetic/audio/spoken-smoke.wav`` (16 kHz mono s16le). No real
person's voice or personal data is used. The fixture is git-ignored, like
every other WAV in the repo; the committed recipes describe how to make a
spoken fixture.

The script prints only event **types**, counts and timings. It never
prints a transcript, coach text, audio or token.

It runs three scenarios:

1. **H** — one real turn: stream the clip at real-time pace, wait for the
   first coach audio byte, send ``end``.
2. **E1** — three seconds of digital silence: no crash, no coach turn and
   no fake score.
3. **E2** — drop the socket mid-turn, then make a clean second call and
   get first audio again.

Usage:

    services/voice/.venv/bin/python tests/smoke/call_once.py

The budget is reported at the end. A "provider turn" here is one coach
reply (one reasoning call); the learner clips submitted and the coach
replies are both counted so the cost is visible. The server's internal
wire-attempt budget is not exposed to a client.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import websockets

VOICE_BASE = "https://13-205-26-178.sslip.io"
WS_URL = VOICE_BASE.replace("https://", "wss://") + "/ws/call"
ORIGIN = "https://gnani-coach.vercel.app"
FRAME_BYTES = 1024
FRAME_SECONDS = FRAME_BYTES / (16000 * 2)  # 32 ms
SPEECH_END_PAD_FRAMES = 40  # 1.28 s of silence to close the learner's turn
MAX_COACH_TURNS = 6

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/synthetic/audio/spoken-smoke.wav"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def start_event() -> dict:
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
        "emittedAt": now_iso(),
        "payload": {
            "audio": {"sampleRateHz": 16000, "channels": 1, "sampleFormat": "s16le"},
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


def control_event(kind: str) -> dict:
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
        "emittedAt": now_iso(),
        "payload": {},
    }


def load_frames(path: Path) -> list[bytes]:
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
            raise SystemExit(
                f"{path} must be 16 kHz mono s16le; got "
                f"{wav.getnchannels()}ch/{wav.getsampwidth()*8}bit/{wav.getframerate()}Hz"
            )
        pcm = wav.readframes(wav.getnframes())
    usable = len(pcm) - (len(pcm) % FRAME_BYTES)
    return [pcm[i : i + FRAME_BYTES] for i in range(0, usable, FRAME_BYTES)]


class Collector:
    """Reads server messages and records only types and timings."""

    def __init__(self) -> None:
        self.types: Counter[str] = Counter()
        self.first_audio_at: float | None = None
        self.coach_turns = 0
        self.errors = 0
        self.transcript_segments = 0
        self.closed = False

    async def run(self, ws) -> None:  # type: ignore[no-untyped-def]
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    self.types["binary"] += 1
                    if self.first_audio_at is None:
                        self.first_audio_at = time.monotonic()
                    continue
                try:
                    event = json.loads(message)
                except json.JSONDecodeError:
                    self.types["unparseable"] += 1
                    continue
                kind = str(event.get("type"))
                self.types[kind] += 1
                if kind == "coach_text":
                    self.coach_turns += 1
                elif kind == "error":
                    self.errors += 1
                elif kind == "transcript_final":
                    self.transcript_segments += 1
        except Exception:  # noqa: BLE001 - a closed socket ends the reader
            self.closed = True

    def summary(self) -> str:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(self.types.items()))
        return f"events[{parts}]"


async def stream_frames(ws, frames: list[bytes], *, pace: bool = True) -> None:  # type: ignore[no-untyped-def]
    for frame in frames:
        await ws.send(frame)
        if pace:
            await asyncio.sleep(FRAME_SECONDS)


async def wait_for(predicate, *, timeout: float) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.1)
    return False


async def scenario_happy(frames: list[bytes]) -> dict:
    collector = Collector()
    speech_end: float | None = None
    async with websockets.connect(WS_URL, origin=ORIGIN, open_timeout=20, max_size=None) as ws:
        await ws.send(json.dumps(start_event()))
        await asyncio.sleep(0.4)
        reader = asyncio.create_task(collector.run(ws))
        await stream_frames(ws, frames)
        speech_end = time.monotonic()
        await stream_frames(ws, [b"\x00" * FRAME_BYTES] * SPEECH_END_PAD_FRAMES)
        got_audio = await wait_for(lambda: collector.first_audio_at is not None, timeout=30)
        await ws.send(json.dumps(control_event("end")))
        await asyncio.sleep(0.5)
        reader.cancel()
    latency_ms = (
        int((collector.first_audio_at - speech_end) * 1000)
        if collector.first_audio_at is not None and speech_end is not None
        else None
    )
    return {
        "name": "H one real turn",
        "pass": got_audio and collector.coach_turns >= 1,
        "detail": f"{collector.summary()} coach_turns={collector.coach_turns} "
        f"first_audio={got_audio} latency_ms_from_end_of_speech={latency_ms}",
        "latency_ms": latency_ms,
        "coach_turns": collector.coach_turns,
        "submitted": 1,
    }


async def scenario_silence() -> dict:
    collector = Collector()
    async with websockets.connect(WS_URL, origin=ORIGIN, open_timeout=20, max_size=None) as ws:
        await ws.send(json.dumps(start_event()))
        await asyncio.sleep(0.4)
        reader = asyncio.create_task(collector.run(ws))
        await stream_frames(ws, [b"\x00" * FRAME_BYTES] * 94)  # 3 s
        await asyncio.sleep(6)
        await ws.send(json.dumps(control_event("end")))
        await asyncio.sleep(0.5)
        reader.cancel()
    passed = (
        collector.coach_turns == 0
        and collector.first_audio_at is None
        and collector.errors == 0
    )
    return {
        "name": "E1 three seconds of silence",
        "pass": passed,
        "detail": f"{collector.summary()} coach_turns={collector.coach_turns} "
        f"no_fake_score={collector.coach_turns == 0} no_crash={collector.errors == 0}",
        "coach_turns": collector.coach_turns,
        "submitted": 1,
    }


async def scenario_drop_then_clean(frames: list[bytes]) -> dict:
    # First socket: speak, then drop while the coach turn is in flight.
    dropped = Collector()
    ws = await websockets.connect(WS_URL, origin=ORIGIN, open_timeout=20, max_size=None)
    await ws.send(json.dumps(start_event()))
    await asyncio.sleep(0.4)
    reader = asyncio.create_task(dropped.run(ws))
    await stream_frames(ws, frames)
    await stream_frames(ws, [b"\x00" * FRAME_BYTES] * 20)
    await asyncio.sleep(0.5)
    await ws.close()
    reader.cancel()

    # Second socket: a clean call must still get first audio.
    clean = await scenario_happy(frames)
    return {
        "name": "E2 drop mid-turn then a clean second call",
        "pass": clean["pass"],
        "detail": f"dropped_after={dropped.summary()} then {clean['detail']}",
        "coach_turns": dropped.coach_turns + clean["coach_turns"],
        "submitted": 2,
    }


async def main_async(args: argparse.Namespace) -> int:
    fixture = Path(args.audio).expanduser().resolve()
    if not fixture.exists():
        print(f"FAIL fixture missing: {fixture}")
        print(
            "Make one with the live TTS provider (synthetic, no real voice) and "
            "save it as 16 kHz mono s16le WAV."
        )
        return 1
    frames = load_frames(fixture)
    print(f"fixture={fixture.name} frames={len(frames)} duration_s={len(frames)*FRAME_SECONDS:.2f}")
    print(f"voice={VOICE_BASE} origin={ORIGIN}")

    results = []
    results.append(await scenario_happy(frames))
    results.append(await scenario_silence())
    results.append(await scenario_drop_then_clean(frames))

    print()
    for result in results:
        print(f"[{'PASS' if result['pass'] else 'FAIL'}] {result['name']}: {result['detail']}")

    coach_turns = sum(r["coach_turns"] for r in results)
    submitted = sum(r["submitted"] for r in results)
    print()
    print(
        f"budget: coach_turns={coach_turns} (limit {MAX_COACH_TURNS}); "
        f"learner_clips_submitted={submitted}; "
        "server-side wire attempts are not exposed to the client"
    )
    failures = [r for r in results if not r["pass"]]
    if coach_turns > MAX_COACH_TURNS:
        failures.append({"name": "budget", "detail": f"{coach_turns} > {MAX_COACH_TURNS}"})
        print(f"[FAIL] budget: {coach_turns} coach turns exceeds {MAX_COACH_TURNS}")
    print(f"SUMMARY pass={len(results)-len(failures)} fail={len(failures)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", default=str(DEFAULT_FIXTURE))
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
