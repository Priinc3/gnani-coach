"""TTS protocol, container behaviour and cancellation fencing [P2].

Covers: start/audio/complete lifecycle, base64 decoding, chunk ordering,
empty and invalid chunks, cancellation fencing, the documented absence of
a provider cancel frame, and container/header observation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct

import pytest

from gnani_coach.providers.errors import InvalidRequestError, ProtocolError
from gnani_coach.providers.events import decode_audio_payload
from gnani_coach.providers.limits import ProbeBudget
from gnani_coach.providers.tts import (
    MODEL_V25,
    MODEL_V30,
    VOICE_CATALOG,
    AudioConfig,
    GnaniTtsSession,
    TtsConfig,
    inspect_container,
)
from gnani_coach.providers.transport import FakeTransport
from _helpers import (
    DUMMY_GNANI_KEY,
    run,
    tts_audio,
    tts_complete,
    tts_error,
    tts_start,
)


def _config(**overrides) -> TtsConfig:
    payload = {
        "text": "Hello there.",
        "voice": "Kaveri",
        "model": MODEL_V25,
        "language": "en-IN",
        "audio": AudioConfig(sample_rate=16000, container="raw"),
    }
    payload.update(overrides)
    return TtsConfig(**payload)


def _session(transport, config=None, **kwargs) -> GnaniTtsSession:
    return GnaniTtsSession(
        config or _config(), DUMMY_GNANI_KEY, transport=transport, **kwargs
    )


# ---------------------------------------------------------------------------
# model / voice pairing
# ---------------------------------------------------------------------------


def test_the_documented_catalog_sizes_match_the_voice_page():
    assert len(VOICE_CATALOG[MODEL_V25]) == 42
    assert len(VOICE_CATALOG[MODEL_V30]) == 13


def test_a_voice_from_the_wrong_model_is_refused_before_any_call():
    transport = FakeTransport(scripted=[])
    # 'Nalini' is v2.5; sending it with v3.0 is documented as a 400.
    with pytest.raises(InvalidRequestError):
        _session(transport, _config(voice="Nalini", model=MODEL_V30))
    assert transport.sent == []


def test_an_unknown_voice_is_refused():
    transport = FakeTransport(scripted=[])
    with pytest.raises(InvalidRequestError):
        _session(transport, _config(voice="DefinitelyNotAVoice"))
    assert transport.sent == []


def test_an_unsupported_tts_language_is_refused():
    with pytest.raises(InvalidRequestError):
        _config(language="fr-FR").validate()


def test_hinglish_is_a_valid_tts_language_but_not_a_valid_stt_code():
    from gnani_coach.providers.stt import catalog_codes

    _config(voice="Poorvi", language="hi-en").validate()
    assert "hi-en" not in catalog_codes()


def test_a_v25_voice_used_with_its_non_preferred_language_is_refused():
    with pytest.raises(InvalidRequestError):
        # Nalini is a Hindi voice; pairing it with en-IN contradicts the docs.
        _config(voice="Nalini", language="en-IN").validate()


def test_empty_text_and_out_of_range_speed_are_refused():
    with pytest.raises(InvalidRequestError):
        _config(text="   ").validate()
    with pytest.raises(InvalidRequestError):
        _config(speed=2.0).validate()


def test_audio_config_rejects_stereo_and_non_16_bit():
    with pytest.raises(InvalidRequestError):
        AudioConfig(num_channels=2).validate()
    with pytest.raises(InvalidRequestError):
        AudioConfig(sample_width=1).validate()
    with pytest.raises(InvalidRequestError):
        AudioConfig(sample_rate=12345).validate()


def test_the_request_payload_matches_the_documented_shape():
    payload = _config().to_request()
    assert payload["model"] == MODEL_V25
    assert payload["voice"] == "Kaveri"
    assert payload["language"] == "en-IN"
    assert payload["audio_config"]["container"] == "raw"


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


def test_a_full_start_audio_complete_lifecycle_is_recorded():
    transport = FakeTransport(
        scripted=[
            tts_start("req_1"),
            tts_audio(b"\x00" * 3200, chunk_index=0),
            tts_audio(b"\x00" * 3200, chunk_index=1),
            tts_complete(2),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize()

    result = run(scenario())
    assert result.request_id == "req_1"
    assert result.completion is not None
    assert result.total_bytes == 6400
    assert result.chunk_indexes_seen == [0, 1]
    assert result.first_nonempty_chunk_ms is not None
    # 6400 bytes / (16000 Hz * 1 ch * 2 bytes) = 0.2 s of audio.
    assert result.total_duration_ms == pytest.approx(200.0, abs=1.0)


def test_an_empty_audio_chunk_is_legal_and_is_not_counted_as_first_audio():
    transport = FakeTransport(
        scripted=[
            tts_start(),
            tts_audio(b"", chunk_index=0),
            tts_audio(b"\x00" * 1600, chunk_index=1),
            tts_complete(2),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize()

    result = run(scenario())
    assert result.total_bytes == 1600
    assert result.chunks[0].bytes == b""
    assert result.chunks[0].is_first_nonempty is False
    assert result.chunks[1].is_first_nonempty is True


def test_invalid_base64_is_a_protocol_error_not_a_silent_empty_chunk():
    transport = FakeTransport(
        scripted=[
            tts_start(),
            json.dumps({"type": "audio", "data": {"chunk_index": 0, "audio": "!!!not base64!!!"}}),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize()

    with pytest.raises(ProtocolError):
        run(scenario())


def test_decode_audio_payload_bounds_the_decoded_size():
    with pytest.raises(ValueError):
        decode_audio_payload("A" * 64, max_bytes=8)
    assert decode_audio_payload("") == b""
    assert decode_audio_payload(base64.b64encode(b"ab").decode()) == b"ab"


def test_an_audio_message_without_a_data_object_is_a_protocol_error():
    transport = FakeTransport(scripted=[json.dumps({"type": "audio"})])

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize()

    with pytest.raises(ProtocolError):
        run(scenario())


def test_an_error_frame_is_reported_without_raising():
    transport = FakeTransport(scripted=[tts_start(), tts_error()])

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize()

    result = run(scenario())
    assert result.errors
    assert result.total_bytes == 0


def test_one_synthesis_at_a_time_is_enforced():
    transport = FakeTransport(scripted=[tts_start()])

    async def scenario():
        async with _session(transport) as session:
            session._in_flight = True
            with pytest.raises(InvalidRequestError):
                await session.synthesize()

    run(scenario())


def test_out_of_order_chunk_indexes_are_flagged():
    transport = FakeTransport(
        scripted=[
            tts_start(),
            tts_audio(b"\x00" * 160, chunk_index=0),
            tts_audio(b"\x00" * 160, chunk_index=0),
            tts_complete(1),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize()

    result = run(scenario())
    assert result.out_of_order_indexes == [0]


# ---------------------------------------------------------------------------
# container / header behaviour
# ---------------------------------------------------------------------------


def test_a_repeated_riff_header_per_chunk_is_detected_not_assumed_away():
    def wav_chunk(payload: bytes) -> bytes:
        header = b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
        header += b"fmt " + struct.pack("<I", 16) + struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16)
        header += b"data" + struct.pack("<I", len(payload))
        return header + payload

    observation = inspect_container([wav_chunk(b"\x00" * 100), wav_chunk(b"\x00" * 100)])
    assert observation["riff_header_count"] == 2
    assert observation["repeated_header_per_chunk"] is True
    # Naive concatenation of these chunks would inject two headers.
    assert observation["chunks"][0]["header_bytes"] == 44


def test_raw_pcm_chunks_report_no_header():
    observation = inspect_container([b"\x00" * 1024, b"\x00" * 1024])
    assert observation["riff_header_count"] == 0
    assert observation["repeated_header_per_chunk"] is False


# ---------------------------------------------------------------------------
# cancellation
# ---------------------------------------------------------------------------


def test_cancelling_consumption_fences_later_chunks():
    forwarded: list[bytes] = []

    async def consumer(payload: bytes) -> None:
        forwarded.append(payload)

    transport = FakeTransport(
        scripted=[
            tts_start(),
            tts_audio(b"\x00" * 1600, chunk_index=0),
            tts_audio(b"\x00" * 1600, chunk_index=1),
            tts_audio(b"\x00" * 1600, chunk_index=2),
            tts_complete(3),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize(
                forward=consumer, cancel_after_chunks=1, close_on_cancel=False
            )

    result = run(scenario())
    assert result.cancelled_by_consumer is True
    assert len(forwarded) == 1
    assert result.fenced_chunk_count > 0
    # Fenced chunks are recorded but excluded from the forwarded audio.
    assert result.audio == b"\x00" * 1600


def test_stopping_consumption_is_not_the_same_as_cancelling_the_provider():
    """The documented API has no cancel frame; only consumption is fenced."""
    transport = FakeTransport(
        scripted=[
            tts_start(),
            tts_audio(b"\x00" * 1600, chunk_index=0),
            tts_audio(b"\x00" * 1600, chunk_index=1),
            tts_complete(2),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.synthesize(cancel_after_chunks=1, close_on_cancel=True)

    result = run(scenario())
    # `connection_closed_to_stop` is True only because the caller chose to
    # close; the provider was never sent a cancel message.
    assert result.connection_closed_to_stop is True
    assert transport.sent == [
        json.dumps(_config().to_request())
    ], "only the synthesis request may ever be sent to the provider"


def test_no_undocumented_cancel_frame_is_ever_sent():
    transport = FakeTransport(scripted=[tts_start(), tts_complete(0)])

    async def scenario():
        async with _session(transport) as session:
            await session.cancel_consumption()
            return await session.synthesize()

    run(scenario())
    for message in transport.sent:
        assert "cancel" not in json.loads(message).keys()


def test_a_second_synthesis_is_rejected_while_one_is_in_flight():
    transport = FakeTransport(scripted=[tts_start()])

    async def scenario():
        async with _session(transport) as session:
            session._in_flight = True
            with pytest.raises(InvalidRequestError):
                await session.synthesize()

    run(scenario())


def test_the_synthesis_request_is_charged_to_the_budget():
    transport = FakeTransport(scripted=[tts_start(), tts_audio(b"\x00" * 1600), tts_complete(1)])
    budget = ProbeBudget()

    async def scenario():
        async with _session(transport, budget=budget) as session:
            return await session.synthesize()

    run(scenario())
    assert budget.per_kind.get("gnani-tts:synthesize") == 1
    assert budget.wire_attempts_used >= 2  # connect + synthesize


def test_the_configured_endpoint_is_the_one_dialed(monkeypatch):
    """Phase 07 defect C1: ``GNANI_TTS_WS_URL`` must reach the client.

    Before the fix the session always dialled ``DEFAULT_TTS_URL`` and the
    setting was dead configuration. The transport constructor is captured
    so the assertion is about the URL actually handed to the dialer, not
    merely about an attribute.
    """
    import gnani_coach.providers.tts as tts_module

    dialled: list[str] = []

    class _CapturingTransport(FakeTransport):
        def __init__(self, url: str, headers: dict[str, str]) -> None:
            super().__init__()
            dialled.append(url)

        async def __aenter__(self) -> "_CapturingTransport":
            return self

        async def __aexit__(self, *args: object) -> None:
            await self.close()

    monkeypatch.setattr(tts_module, "WebSocketTransport", _CapturingTransport)
    configured = "wss://api.vachana.ai/reviewed-custom-tts"
    session = GnaniTtsSession(
        _config(), DUMMY_GNANI_KEY, url=configured
    )

    async def scenario():
        await session._connect()
        await session.aclose(reason="test")

    run(scenario())
    assert dialled == [configured]
    assert session.url == configured
