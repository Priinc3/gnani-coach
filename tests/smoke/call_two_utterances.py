#!/usr/bin/env python3
"""Two real learner utterances through the public ``/ws/call`` socket.

This is the Phase 16 reproduction of the reported phone bug: a short
"Hello." followed by two seconds of silence, then one long utterance
(8-12 s, several sentences) followed by three seconds of silence. Audio is
**synthetic**: both clips are rendered once by the live text-to-speech
provider and kept under ``fixtures/synthetic/audio/`` (git-ignored). No real
person's voice or personal data is used.

The script prints only event **types**, counts and timings. It never prints
a transcript, coach text, audio or token. It also reports the longest gap
between any two server messages, which is what the browser's 45 s idle
timer actually observes.

Usage (a local throw-away server on port 8100)::

    services/voice/.venv/bin/python tests/smoke/call_two_utterances.py \
        --url ws://127.0.0.1:8100/ws/call

The transport is the same one ``tests/smoke/call_once.py`` uses.
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

FRAME_BYTES = 1024
FRAME_SECONDS = FRAME_BYTES / (16000 * 2)  # 32 ms
ORIGIN = "https://gnani-coach.vercel.app"
DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/synthetic/audio"
DEFAULT_HELLO = DEFAULT_FIXTURES / "two-utterance-hello.wav"
DEFAULT_LONG = DEFAULT_FIXTURES / "two-utterance-long.wav"
SILENCE_AFTER_HELLO_FRAMES = round(2.0 / FRAME_SECONDS)
SILENCE_AFTER_LONG_FRAMES = round(3.0 / FRAME_SECONDS)
MAX_WAIT_SECONDS = 60.0


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
    """Reads server messages and records only types, counts and timings."""

    def __init__(self, started: float) -> None:
        self.started = started
        self.arrivals: list[tuple[float, str]] = []
        self.types: Counter[str] = Counter()
        self.closed = False
        self.ended_by_client = False
        self.transcript_chars = 0
        self.long_transcript_chars = 0
        self.long_end_at: float | None = None
        self.coach_after_long = 0
        self.first_audio_after_long: float | None = None
        self.errors = 0
        #: Phase 19: which descriptor the next binary belongs to.
        self.descriptor_kind = "reply"
        self.backchannel_count = 0
        #: (arrival, kind) for every binary chunk.
        self.audio_kinds: list[tuple[float, str]] = []

    async def run(self, ws) -> None:  # type: ignore[no-untyped-def]
        try:
            async for message in ws:
                at = time.monotonic() - self.started
                if isinstance(message, bytes):
                    self.types["binary"] += 1
                    self.audio_kinds.append((at, self.descriptor_kind))
                    self.arrivals.append(
                        (at, f"binary bytes={len(message)} kind={self.descriptor_kind}")
                    )
                    continue
                try:
                    event = json.loads(message)
                except json.JSONDecodeError:
                    self.types["unparseable"] += 1
                    self.arrivals.append((at, "unparseable"))
                    continue
                kind = str(event.get("type"))
                self.types[kind] += 1
                detail = kind
                if kind == "status":
                    state = (event.get("payload") or {}).get("state")
                    detail = f"status state={state}"
                elif kind == "transcript_final":
                    text = str((event.get("payload") or {}).get("text") or "")
                    chars = len(text)
                    words = len(text.split())
                    self.transcript_chars += chars
                    detail = f"transcript_final chars={chars} words={words}"
                elif kind == "coach_text":
                    if self.long_end_at is not None and at >= self.long_end_at:
                        self.coach_after_long += 1
                elif kind == "audio.frame.descriptor":
                    payload = event.get("payload") or {}
                    self.descriptor_kind = str(payload.get("kind") or "reply")
                    if self.descriptor_kind == "backchannel":
                        self.backchannel_count += 1
                    detail = f"descriptor kind={self.descriptor_kind}"
                elif kind == "error":
                    self.errors += 1
                self.arrivals.append((at, detail))
        except Exception:  # noqa: BLE001 - a closed socket ends the reader
            self.closed = True
        else:
            self.closed = not self.ended_by_client

    def longest_gap_s(self) -> float:
        times = [at for at, _ in self.arrivals]
        if len(times) < 2:
            return 0.0
        return max(b - a for a, b in zip(times, times[1:]))


async def stream_frames(ws, frames: list[bytes]) -> None:  # type: ignore[no-untyped-def]
    for frame in frames:
        await ws.send(frame)
        await asyncio.sleep(FRAME_SECONDS)


async def wait_until(predicate, *, timeout: float) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.1)
    return False


async def run(args: argparse.Namespace) -> int:
    hello = load_frames(Path(args.hello).expanduser().resolve())
    long_clip = load_frames(Path(args.long).expanduser().resolve())
    print(f"url={args.url} origin={args.origin}")
    print(
        f"hello_frames={len(hello)} hello_s={len(hello)*FRAME_SECONDS:.2f} "
        f"long_frames={len(long_clip)} long_s={len(long_clip)*FRAME_SECONDS:.2f}"
    )

    started = time.monotonic()
    collector = Collector(started)
    long_started_at: float | None = None
    long_end_at: float | None = None
    reader = None
    try:
        async with websockets.connect(
            args.url, origin=args.origin, open_timeout=20, max_size=None
        ) as ws:
            await ws.send(json.dumps(start_event()))
            await asyncio.sleep(0.4)
            reader = asyncio.create_task(collector.run(ws))

            await stream_frames(ws, hello)
            await stream_frames(ws, [b"\x00" * FRAME_BYTES] * SILENCE_AFTER_HELLO_FRAMES)
            long_started_at = time.monotonic() - started
            await stream_frames(ws, long_clip)
            long_end_at = time.monotonic() - started
            collector.long_end_at = long_end_at
            await stream_frames(ws, [b"\x00" * FRAME_BYTES] * SILENCE_AFTER_LONG_FRAMES)

            # The long utterance may close more than one VAD segment. Wait
            # for the coach line that follows the long turn, not merely for
            # the reply to "Hello.".
            await wait_until(
                lambda: collector.coach_after_long >= 1 or collector.closed,
                timeout=MAX_WAIT_SECONDS,
            )
            await asyncio.sleep(0.5)
            collector.ended_by_client = True
            await ws.send(json.dumps(control_event("end")))
            await asyncio.sleep(0.5)
    except Exception as exc:  # noqa: BLE001 - report, do not trace
        print(f"connect_failed={type(exc).__name__}")
        return 1
    finally:
        if reader is not None:
            reader.cancel()

    # The second coach line is the one after the long turn. Re-derive it
    # from the arrival times so the count is not a guess.
    coach_times = [
        at
        for at, detail in collector.arrivals
        if detail.startswith("coach_text")
    ]
    coach_after_long = (
        sum(1 for at in coach_times if long_end_at is not None and at >= long_end_at)
        if long_end_at is not None
        else 0
    )
    long_transcript_chars = sum(
        int(detail.split("chars=")[1].split()[0])
        for at, detail in collector.arrivals
        if detail.startswith("transcript_final")
        and long_started_at is not None
        and at >= long_started_at
    )
    first_audio_after_long = next(
        (
            at
            for at, kind in collector.audio_kinds
            if long_end_at is not None and at >= long_end_at
        ),
        None,
    )
    first_audio_after_long_ms = (
        int((first_audio_after_long - long_end_at) * 1000)
        if first_audio_after_long is not None and long_end_at is not None
        else None
    )
    # (ii) the first word of the *real reply*: the first binary whose
    # descriptor carried kind=reply (a backchannel has its own turn).
    first_reply_audio_after_long = next(
        (
            at
            for at, kind in collector.audio_kinds
            if kind == "reply" and long_end_at is not None and at >= long_end_at
        ),
        None,
    )
    first_reply_audio_after_long_ms = (
        int((first_reply_audio_after_long - long_end_at) * 1000)
        if first_reply_audio_after_long is not None and long_end_at is not None
        else None
    )

    print()
    print("event arrivals (seconds relative to call start):")
    for at, detail in collector.arrivals:
        print(f"  +{at:8.3f}  {detail}")

    longest_gap = collector.longest_gap_s()
    transcript_finals = collector.types.get("transcript_final", 0)
    coach_texts = collector.types.get("coach_text", 0)
    passed = (
        transcript_finals >= 2
        and long_transcript_chars > 0
        and coach_after_long >= 1
        and longest_gap <= 15.0
        and collector.errors == 0
        and not collector.closed
    )
    print()
    print(f"transcript_final_count={transcript_finals}")
    print(f"long_transcript_chars={long_transcript_chars}")
    print(f"coach_text_count={coach_texts} coach_after_long={coach_after_long}")
    print(f"longest_gap_between_server_messages_ms={int(longest_gap*1000)}")
    print(
        "end_of_long_speech_to_first_coach_audio_ms="
        f"{first_audio_after_long_ms}"
    )
    print(
        "end_of_long_speech_to_first_sound_of_any_kind_ms="
        f"{first_audio_after_long_ms}"
    )
    print(
        "end_of_long_speech_to_first_word_of_real_reply_ms="
        f"{first_reply_audio_after_long_ms}"
    )
    print(f"backchannel_count={collector.backchannel_count}")
    print(f"errors={collector.errors} socket_closed_early={collector.closed}")
    print(f"RESULT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8100/ws/call")
    parser.add_argument("--origin", default=ORIGIN)
    parser.add_argument("--hello", default=str(DEFAULT_HELLO))
    parser.add_argument("--long", default=str(DEFAULT_LONG))
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
