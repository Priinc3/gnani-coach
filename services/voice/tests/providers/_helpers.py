"""Offline helpers for provider tests.

Builds documented provider messages so each test states exactly which wire
frame it is exercising. Nothing here opens a socket or needs a credential.
"""

from __future__ import annotations

import asyncio
import base64
import json

#: Obviously fake. Never a real key; never used against a live endpoint.
DUMMY_GNANI_KEY = "dummy-gnani-key-not-a-credential"
DUMMY_GEMINI_KEY = "dummy-gemini-key-not-a-credential"


def run(coro):
    """Run one coroutine on a fresh loop (the suite stays synchronous)."""
    return asyncio.run(coro)


# -- STT frames -----------------------------------------------------------


def stt_connected_message(sample_rate: int = 16000) -> str:
    return json.dumps(
        {
            "type": "connected",
            "message": "STT service ready — VAD service connected",
            "timestamp": "2024-01-15T10:30:00.000Z",
            "config": {"sample_rate": sample_rate, "chunk_size": 512},
        }
    )


def stt_transcript(
    text: str = "hello",
    *,
    segment_id: str = "seg-1",
    segment_index: int = 0,
    duration_ms: int = 900,
    latency_ms: int = 210,
) -> str:
    return json.dumps(
        {
            "type": "transcript",
            "timestamp": "2024-01-15T10:30:05.987Z",
            "text": text,
            "audio_duration_ms": duration_ms,
            "segment_id": segment_id,
            "segment_index": segment_index,
            "latency": latency_ms,
        }
    )


def stt_error(message: str = "STT engine failed to initialize") -> str:
    return json.dumps(
        {"type": "error", "timestamp": "2024-01-15T10:30:10.000Z", "message": message}
    )


# -- TTS frames -----------------------------------------------------------


def tts_start(request_id: str = "req_abc123") -> str:
    return json.dumps(
        {"type": "start", "message": "Streaming started", "request_id": request_id}
    )


def tts_audio(payload: bytes, chunk_index: int = 0, is_final: bool = False) -> str:
    return json.dumps(
        {
            "type": "audio",
            "data": {
                "chunk_index": chunk_index,
                "audio": base64.b64encode(payload).decode("ascii"),
                "is_final": is_final,
            },
        }
    )


def tts_complete(chunk_index: int = 3) -> str:
    return json.dumps(
        {
            "type": "complete",
            "data": {"chunk_index": chunk_index, "audio": "", "is_final": True},
        }
    )


def tts_error(message: str = "Invalid text or audio configuration.") -> str:
    return json.dumps({"type": "error", "message": message})
