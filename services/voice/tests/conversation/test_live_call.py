"""The opt-in live chain: real speech in, a real coach line out.

This test is **skipped by default**. It runs only when

* ``GNANI_LIVE_TESTS=1`` is set, and
* ``GNANI_API_KEY``, ``GEMINI_API_KEY`` and ``GEMINI_MODEL`` are all
  present in the environment.

Otherwise it is skipped with the reason
``BLOCKED: credentials not configured``, which is the result the phase
report records.

The chain is short and bounded: **at most 16 wire attempts** for the
whole test, enforced by a :class:`ProbeBudget` whose counters the test
asserts on. The chain is:

1. the real synthesiser says one short sentence (1 wire attempt);
2. that audio is sent to the real recogniser as the learner's frames
   (1 wire attempt), and the real turn controller ends the turn;
3. the real reasoning model answers the turn (1 wire attempt);
4. the real synthesiser speaks the answer (1 wire attempt).

Nothing is mocked. The point is to prove that the ports, the adapters
and the runtime work against the real providers — not that the output
is good.
"""

from __future__ import annotations

import importlib
import json
import os
from typing import Any

import pytest

from gnani_coach.conversation.config import BINARY_FRAME_BYTES
from gnani_coach.ports.text_to_speech import TtsOpenRequest

pytestmark = pytest.mark.live

#: The environment the live chain needs.
REQUIRED_ENV = ("GNANI_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL")

#: The ceiling on the wire attempts of the whole chain.
MAX_LIVE_WIRE_ATTEMPTS = 16

#: The sentence the synthesiser says, and the learner "speaks".
THE_SENTENCE = "Hello, I am practising a short introduction."


def _missing_credentials() -> list[str]:
    return [name for name in REQUIRED_ENV if not os.environ.get(name)]


@pytest.fixture
def live_budget() -> Any:
    """The allowance of the live chain.

    Skips with the recorded reason when the chain may not run.
    """
    if os.environ.get("GNANI_LIVE_TESTS") != "1":
        pytest.skip(
            "live provider checks are opt-in: set GNANI_LIVE_TESTS=1 to run them"
        )
    missing = _missing_credentials()
    if missing:
        pytest.skip(
            "BLOCKED: credentials not configured (" + ", ".join(missing) + " missing)"
        )
    from gnani_coach.providers.limits import ProbeBudget

    return ProbeBudget(
        max_operations=MAX_LIVE_WIRE_ATTEMPTS,
        max_audio_seconds=30.0,
        max_connections=4,
    )


def _frames(pcm: bytes) -> list[bytes]:
    """Split a clip into the exact 1,024-byte frames the transport wants."""
    usable = len(pcm) - (len(pcm) % BINARY_FRAME_BYTES)
    return [
        pcm[start : start + BINARY_FRAME_BYTES]
        for start in range(0, usable, BINARY_FRAME_BYTES)
    ]


def _start_event() -> dict[str, Any]:
    """A valid ``start`` event for a guest call."""
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
        "emittedAt": "2026-10-20T10:00:00Z",
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


@pytest.mark.anyio
async def test_the_live_chain(live_budget: Any) -> None:
    """The real chain: speech in, a coach line out, in a bounded budget."""
    import anyio
    from fastapi.testclient import TestClient

    from gnani_coach.main import app
    from gnani_coach.settings import load_settings

    conversation_router = importlib.import_module("gnani_coach.conversation.router")
    providers_module = importlib.import_module("gnani_coach.conversation.providers")
    real_builder = providers_module.build_call_providers

    def spy(settings: Any, *, practice_language_id: str) -> Any:
        """Build the real providers, with the chain's own allowance."""
        return real_builder(
            settings,
            practice_language_id=practice_language_id,
            budget=live_budget,
        )

    conversation_router.build_call_providers = spy  # type: ignore[assignment]

    settings = load_settings()
    assert settings.voice.api_key is not None, "the live chain needs a voice key"
    assert settings.gemini.api_key is not None, "the live chain needs a model key"

    client = TestClient(app)
    client.__enter__()
    try:
        # 1. The real synthesiser says the sentence the learner will
        #    "speak". This proves the TTS port against the live provider.
        providers = real_builder(
            settings, practice_language_id="english", budget=live_budget
        )
        assert providers is not None, "the providers must build for a live call"
        tts_session = providers.tts.open_session(
            TtsOpenRequest(
                text=THE_SENTENCE,
                voice=providers.tts_voice,
                model=providers.tts_model,
                language=providers.tts_language,
            )
        )
        chunks = await tts_session.synthesize()
        await tts_session.aclose(reason="live")
        assert chunks, "the live synthesiser returned no audio"
        learner_audio = b"".join(chunk.data for chunk in chunks)
        assert (
            len(learner_audio) >= BINARY_FRAME_BYTES
        ), "the synthesised audio is too short"

        # 2-4. The real call: the frames go in, the recogniser hears them,
        #      the turn ends, the model answers and the coach speaks.
        socket = client.websocket_connect("/ws/call")
        socket.__enter__()
        try:
            socket.send_json(_start_event())
            for frame in _frames(learner_audio):
                socket.send_bytes(frame)
            # The hold is 1.2 s of silence; one frame is 32 ms.
            for _ in range(60):
                socket.send_bytes(b"\x00" * BINARY_FRAME_BYTES)

            transcript = ""
            coach_text = ""

            async def _wait() -> None:
                nonlocal transcript, coach_text
                for _ in range(120):
                    with anyio.move_on_after(30) as scope:
                        message = await socket._send_rx.receive()
                    if scope.cancelled_caught:
                        break
                    if message.get("type") == "websocket.close":
                        break
                    if "text" not in message:
                        continue
                    event = json.loads(message["text"])
                    if event.get("type") == "transcript_final":
                        transcript = event["payload"]["text"]
                    if event.get("type") == "coach_text":
                        coach_text = event["payload"]["text"]
                        return

            socket.portal.call(_wait)
            assert transcript, "the live recogniser returned no transcript"
            assert coach_text, "the live model returned no coach line"
        finally:
            socket.__exit__(None, None, None)
    finally:
        client.__exit__(None, None, None)

    attempts = live_budget.wire_attempts_used
    assert 0 < attempts <= MAX_LIVE_WIRE_ATTEMPTS, (
        f"the chain used {attempts} wire attempts, the ceiling is "
        f"{MAX_LIVE_WIRE_ATTEMPTS}"
    )
