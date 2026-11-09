#!/usr/bin/env python3
"""One long synthetic monologue with two real pauses (Phase 19).

It streams two copies of the synthetic 9.12 s clip with a 600 ms silence
between them, then a short clip. The pauses are real learner-audio silence,
so a mid-sentence backchannel must be triggered by the endpointing gate,
not by a timer. Only counts and timings are printed: no transcript, no
coach text, no audio, no token.

Usage::

    services/voice/.venv/bin/python tests/smoke/long_monologue.py \
        --url ws://127.0.0.1:8100/ws/call --origin http://localhost:3000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from pathlib import Path

import websockets

FRAME_BYTES = 1024
FRAME_SECONDS = FRAME_BYTES / (16000 * 2)
PAUSE_SECONDS = 0.66
PAUSE_FRAMES = round(PAUSE_SECONDS / FRAME_SECONDS)
START_GRACE_S = 3.0
MAX_WAIT_SECONDS = 90.0

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/synthetic/audio"
LONG = FIXTURES / "two-utterance-long.wav"
SHORT = FIXTURES / "clear-utterance.wav"


def now_iso() -> str:
    from datetime import datetime, timezone

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


def end_event() -> dict:
    return {
        "envelopeVersion": "0.1",
        "direction": "client_to_server",
        "type": "end",
        "sessionId": None,
        "connectionId": None,
        "roundId": None,
        "turnId": None,
        "sequence": 0,
        "sampleTimeMs": None,
        "emittedAt": now_iso(),
        "payload": {"reason": "learner_ended"},
    }


def is_loud(frame: bytes) -> bool:
    """The same cheap energy gate the server uses, for the test timeline."""
    import math

    count = len(frame) // 2
    if count == 0:
        return False
    total = 0
    for index in range(0, len(frame) - 1, 2):
        sample = int.from_bytes(frame[index : index + 2], "little", signed=True)
        total += sample * sample
    rms = math.sqrt(total / count)
    return rms > 0 and 20.0 * math.log10(rms / 32768.0) >= -45.0


def load_frames(path: Path) -> list[bytes]:
    with wave.open(str(path), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    usable = len(pcm) - (len(pcm) % FRAME_BYTES)
    return [pcm[i : i + FRAME_BYTES] for i in range(0, usable, FRAME_BYTES)]


def compact(frames: list[bytes]) -> list[bytes]:
    """Remove long internal silences, keeping a short natural bridge.

    The fixture is a natural utterance with pauses of its own. This test
    needs a continuous run of speech before each scripted pause, so a run
    of more than three silent frames is cut to three (96 ms).
    """
    out: list[bytes] = []
    silent_run = 0
    for frame in frames:
        if is_loud(frame):
            silent_run = 0
            out.append(frame)
            continue
        silent_run += 1
        if silent_run <= 3:
            out.append(frame)
    # Trim leading and trailing silence, so the only gap between two clips
    # is the scripted pause.
    while out and not is_loud(out[0]):
        out.pop(0)
    while out and not is_loud(out[-1]):
        out.pop()
    return out


class Collector:
    def __init__(self, started: float) -> None:
        self.started = started
        self.backchannels: list[float] = []
        self.coach_text_at: float | None = None
        self.closed = False

    async def run(self, ws) -> None:  # type: ignore[no-untyped-def]
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    continue
                try:
                    event = json.loads(message)
                except json.JSONDecodeError:
                    continue
                at = time.monotonic() - self.started
                kind = event.get("type")
                if kind == "audio.frame.descriptor":
                    payload = event.get("payload") or {}
                    if payload.get("kind") == "backchannel":
                        self.backchannels.append(at)
                elif kind == "coach_text" and self.coach_text_at is None:
                    self.coach_text_at = at
        except Exception:  # noqa: BLE001 - a closed socket ends the reader
            self.closed = True


async def stream(ws, frames: list[bytes]) -> None:  # type: ignore[no-untyped-def]
    for frame in frames:
        await ws.send(frame)
        await asyncio.sleep(FRAME_SECONDS)


async def run(args: argparse.Namespace) -> int:
    long_frames = compact(load_frames(Path(args.long).expanduser().resolve()))
    short_frames = compact(load_frames(Path(args.short).expanduser().resolve()))
    silence = [b"\x00" * FRAME_BYTES] * PAUSE_FRAMES
    started = time.monotonic()
    collector = Collector(started)
    speech_windows: list[tuple[float, float]] = []
    frame_timeline: list[tuple[float, bool]] = []

    try:
        async with websockets.connect(
            args.url, origin=args.origin, open_timeout=20, max_size=None
        ) as ws:
            await ws.send(json.dumps(start_event()))
            await asyncio.sleep(0.4)
            reader = asyncio.create_task(collector.run(ws))

            async def speak(frames: list[bytes]) -> None:
                begin = time.monotonic() - started
                for frame in frames:
                    await ws.send(frame)
                    frame_timeline.append(
                        (time.monotonic() - started, is_loud(frame))
                    )
                    await asyncio.sleep(FRAME_SECONDS)
                speech_windows.append((begin, time.monotonic() - started))

            await speak(long_frames)
            await stream(ws, silence)
            await speak(long_frames)
            await stream(ws, silence)
            await speak(short_frames)
            # Real trailing silence: the endpointing clock advances only on
            # frames, so the turn cannot close without them.
            await stream(ws, [b"\x00" * FRAME_BYTES] * round(3.0 / FRAME_SECONDS))

            deadline = time.monotonic() + MAX_WAIT_SECONDS
            while time.monotonic() < deadline and collector.coach_text_at is None:
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.5)
            await ws.send(json.dumps(end_event()))
            await asyncio.sleep(0.5)
            reader.cancel()
    except Exception as exc:  # noqa: BLE001 - report, do not trace
        print(f"connect_failed={type(exc).__name__}")
        return 1

    # A run of loud frames is "the learner is speaking". Merge gaps shorter
    # than the 240 ms hangover, exactly as the server's gate does.
    loud_runs: list[list[float]] = []
    for at, loud in frame_timeline:
        if not loud:
            continue
        if loud_runs and at - loud_runs[-1][1] <= 0.24:
            loud_runs[-1][1] = at
        else:
            loud_runs.append([at, at])
    # The 150 ms guard is allowed to land at the very start of resumed
    # speech; only a reaction that arrives well into a loud run is "while
    # the learner speaks".
    during_speech = [
        at
        for at in collector.backchannels
        if any(begin + 0.15 <= at <= end + 0.05 for begin, end in loud_runs)
    ]
    last_loud = loud_runs[-1][1] if loud_runs else 0.0
    mid_turn = [at for at in collector.backchannels if at <= last_loud]
    in_grace = [at for at in collector.backchannels if at < START_GRACE_S]
    print(f"url={args.url} origin={args.origin}")
    print(
        f"speech_s={sum(end - begin for begin, end in speech_windows):.2f} "
        f"pauses={len(speech_windows) - 1} pause_ms={PAUSE_FRAMES * FRAME_SECONDS * 1000:.0f}"
    )
    print(f"backchannel_count={len(collector.backchannels)}")
    print(
        "backchannel_times_s="
        + ",".join(f"{at:.2f}" for at in collector.backchannels)
    )
    print(
        "loud_runs_s="
        + ";".join(f"{begin:.2f}-{end:.2f}" for begin, end in loud_runs)
    )
    print(f"mid_turn_backchannels={len(mid_turn)}")
    print(f"backchannels_during_speech={len(during_speech)}")
    print(f"backchannels_in_first_3s={len(in_grace)}")
    print(f"coach_text_at_s={collector.coach_text_at}")
    passed = (
        1 <= len(mid_turn) <= 2
        and len(during_speech) == 0
        and len(in_grace) == 0
        and collector.coach_text_at is not None
    )
    print(f"RESULT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8100/ws/call")
    parser.add_argument("--origin", default="http://localhost:3000")
    parser.add_argument("--long", default=str(LONG))
    parser.add_argument("--short", default=str(SHORT))
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
