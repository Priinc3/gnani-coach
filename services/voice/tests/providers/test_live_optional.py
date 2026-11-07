"""Opt-in live checks. Skipped by default; never part of a green default run.

Enable with **both**::

    GNANI_LIVE_TESTS=1
    GNANI_API_KEY=...  GEMINI_API_KEY=...  GEMINI_MODEL=...

These tests spend real provider quota. They are excluded from the default
suite so that ``pytest services/voice/tests`` performs no inference.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live

REQUIRED = ("GNANI_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL")


def _enabled() -> tuple[bool, list[str]]:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    return os.environ.get("GNANI_LIVE_TESTS") == "1", missing


@pytest.fixture
def live_credentials():
    enabled, missing = _enabled()
    if not enabled:
        pytest.skip("live checks require GNANI_LIVE_TESTS=1 (opt-in)")
    if missing:
        pytest.skip(f"live checks need these variable names: {', '.join(missing)}")
    return {name: os.environ[name] for name in REQUIRED}


def test_live_stt_roundtrip(live_credentials):
    """One bounded STT call over a prepared spoken fixture."""
    import asyncio

    from tools.probes import fixtures_io
    from gnani_coach.providers.stt import GnaniSttSession, build_config

    fixture = fixtures_io.resolve_fixture("spoken-clear-sentence")
    config = build_config(fixture.language_code, sample_rate=fixture.sample_rate)

    async def run_once():
        async with GnaniSttSession(config, live_credentials["GNANI_API_KEY"]) as session:
            return await session.stream_pcm(
                fixtures_io.raw_pcm_of(fixture), real_time=True
            )

    result = asyncio.run(run_once())
    assert result.segment_count >= 1
    assert result.text.strip()
    # A VAD-closed segment is still not a conversational turn.
    assert not hasattr(result, "turns")


def test_live_tts_returns_audio_bytes(live_credentials):
    import asyncio

    from gnani_coach.providers.tts import AudioConfig, GnaniTtsSession, TtsConfig

    config = TtsConfig(
        text="Hello. This is a short test.",
        voice="Kaveri",
        model="timbre-v2.5",
        language="en-IN",
        audio=AudioConfig(sample_rate=16000, container="raw"),
    )

    async def run_once():
        async with GnaniTtsSession(config, live_credentials["GNANI_API_KEY"]) as session:
            return await session.synthesize()

    result = asyncio.run(run_once())
    assert result.total_bytes > 0
    # Container behaviour is observed, never assumed.
    assert "riff_header_count" in result.container_observation


def test_live_gemini_replies_without_tools(live_credentials):
    import asyncio

    from gnani_coach.providers.gemini import CoachRequest, GeminiCoach, GeminiConfig

    client = GeminiCoach(
        GeminiConfig(model=live_credentials["GEMINI_MODEL"], store=False),
        live_credentials["GEMINI_API_KEY"],
    )
    request = CoachRequest(
        recognized_text="I think we should ship it next week.",
        system_instruction="You are a spoken-language conversation coach.",
    )
    event = asyncio.run(client.reply(request))
    assert event.text
    assert event.tools_enabled is False
