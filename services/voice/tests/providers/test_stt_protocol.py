"""STT protocol behaviour against a fake transport [P1].

Covers: concurrent send/receive, a clean close, duplicate and out-of-order
segments, malformed and oversized responses, invalid language/sample rate,
missing configuration, and the documented "a VAD-closed segment is not a
conversational turn" boundary.
"""

from __future__ import annotations

import json

import pytest

from gnani_coach.providers.errors import (
    EndpointError,
    InvalidRequestError,
    ProtocolError,
    ProviderError,
)
from gnani_coach.providers.limits import ProbeBudget
from gnani_coach.providers.stt import (
    FORMAT_VERBATIM,
    GnaniSttSession,
    VadSettings,
    build_config,
    catalog_codes,
)
from gnani_coach.providers.transport import (
    MAX_MESSAGE_BYTES,
    FakeTransport,
    decode_json_message,
    validate_endpoint,
)
from _helpers import (
    DUMMY_GNANI_KEY,
    run,
    stt_connected_message,
    stt_error,
    stt_transcript,
)


def _pcm(seconds: float = 0.2) -> bytes:
    return b"\x00\x01" * int(16000 * seconds)


def _session(transport, **overrides) -> GnaniSttSession:
    config = build_config(
        overrides.pop("language", "en-IN"), sample_rate=overrides.pop("sample_rate", 16000)
    )
    return GnaniSttSession(
        config,
        overrides.pop("api_key", DUMMY_GNANI_KEY),
        transport=transport,
        **overrides,
    )


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


def test_language_codes_come_from_the_documented_ten():
    codes = catalog_codes()
    assert len(codes) == 10
    assert {"en-IN", "hi-IN", "ta-IN", "te-IN"} <= codes
    # Hinglish is a TTS-only code and must never be sent to STT.
    assert "hi-en" not in codes


def test_an_uncatalogued_language_is_refused_before_any_connection():
    transport = FakeTransport(scripted=[])
    with pytest.raises(InvalidRequestError):
        _session(transport, language="fr-IN")
    assert transport.sent == []
    assert transport.close_calls == 0


def test_an_unsupported_sample_rate_is_refused():
    # The sample rate is validated at connect time, not at construction.
    with pytest.raises(InvalidRequestError):
        GnaniSttSession(build_config("en-IN", sample_rate=22050), DUMMY_GNANI_KEY)


def test_a_missing_key_is_a_configuration_failure_not_a_crash():
    with pytest.raises(InvalidRequestError):
        GnaniSttSession(build_config("en-IN"), "")


def test_baseline_config_is_verbatim_with_substitution_off_and_no_word_bias():
    config = build_config("en-IN")
    assert config.output_format == FORMAT_VERBATIM
    assert config.enable_substitution is False
    assert config.bias_words == ()
    headers = config.headers(DUMMY_GNANI_KEY)
    assert headers["x-format"] == "verbatim"
    assert "x-bias-list" not in headers
    assert "x-enable-substitution" not in headers


def test_substitution_cannot_be_enabled_for_baseline_analysis():
    config = build_config("en-IN")
    object.__setattr__(config, "enable_substitution", True)
    with pytest.raises(InvalidRequestError):
        config.headers(DUMMY_GNANI_KEY)


def test_vad_settings_are_validated_against_the_documented_ranges():
    VadSettings().validate()
    with pytest.raises(InvalidRequestError):
        VadSettings(threshold=1.5).validate()
    with pytest.raises(InvalidRequestError):
        VadSettings(min_silence_ms=50).validate()
    with pytest.raises(InvalidRequestError):
        VadSettings(max_speech_s=500.0).validate()


def test_vad_headers_are_emitted_and_recorded_as_connection_lifetime_settings():
    config = build_config("en-IN", vad=VadSettings(min_silence_ms=700, threshold=0.5))
    headers = config.headers(DUMMY_GNANI_KEY)
    assert headers["x-min-silence-ms"] == "700"
    assert headers["x-vad-threshold"] == "0.5"
    summary = config.safe_summary(DUMMY_GNANI_KEY)
    assert summary["frame_bytes"] == 1024
    assert summary["frame_duration_ms"] == 32.0
    assert "fixed for the life of the connection" in summary["vad"]["note"]


def test_the_api_key_never_appears_in_the_safe_summary():
    config = build_config("en-IN")
    summary = config.safe_summary(DUMMY_GNANI_KEY)
    assert DUMMY_GNANI_KEY not in json.dumps(summary)
    assert summary["headers"]["x-api-key-id"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# endpoint / key confinement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ws://api.vachana.ai/stt/v3/stream",
        "wss://evil.example.com/stt/v3/stream",
        "wss://api.vachana.ai.evil.test/stt/v3/stream",
        "https://api.vachana.ai/stt/v3/stream",
        "wss://user:pass@api.vachana.ai/stt/v3/stream",
        "wss://api.vachana.ai/stt/v3/stream?next=https://evil.test",
    ],
)
def test_endpoint_validation_rejects_every_unreviewed_destination(url):
    with pytest.raises(EndpointError):
        validate_endpoint(url)


def test_endpoint_validation_accepts_the_documented_url():
    assert (
        validate_endpoint("wss://api.vachana.ai/stt/v3/stream")
        == "wss://api.vachana.ai/stt/v3/stream"
    )


def test_a_non_allowlisted_host_is_refused_before_the_key_is_attached():
    config = build_config("en-IN")
    object.__setattr__(config, "url", "wss://attacker.test/stt/v3/stream")
    with pytest.raises(EndpointError):
        config.headers(DUMMY_GNANI_KEY)


# ---------------------------------------------------------------------------
# protocol
# ---------------------------------------------------------------------------


def test_send_and_receive_run_concurrently_and_the_stream_closes_cleanly():
    transport = FakeTransport(
        scripted=[
            stt_connected_message(),
            stt_transcript("hello there", segment_id="s1", segment_index=0),
            stt_transcript("second part", segment_id="s2", segment_index=1),
        ]
    )

    async def scenario():
        session = _session(transport)
        async with session:
            return await session.stream_pcm(_pcm(), real_time=False, idle_grace_ms=80)

    result = run(scenario())
    assert result.segment_count == 2
    assert result.text == "hello there second part"
    assert result.closed_cleanly is True
    # The receiver task was actually running while frames were written.
    assert any(isinstance(message, bytes) for message in transport.sent)


def test_duplicate_segment_ids_are_detected_rather_than_counted_twice():
    transport = FakeTransport(
        scripted=[
            stt_connected_message(),
            stt_transcript("same", segment_id="dup-1", segment_index=0),
            stt_transcript("same", segment_id="dup-1", segment_index=1),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(_pcm(), real_time=False, idle_grace_ms=80)

    result = run(scenario())
    assert result.duplicate_segment_ids == ["dup-1"]
    assert result.transcripts[1].status == "duplicate"


def test_out_of_order_segment_indexes_are_flagged_not_reordered_silently():
    transport = FakeTransport(
        scripted=[
            stt_connected_message(),
            stt_transcript("first", segment_id="a", segment_index=0),
            stt_transcript("late", segment_id="b", segment_index=0),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(_pcm(), real_time=False, idle_grace_ms=80)

    result = run(scenario())
    assert result.out_of_order_indexes == [0]
    assert result.transcripts[1].status == "out_of_order"


def test_an_error_frame_is_recorded_not_raised():
    transport = FakeTransport(scripted=[stt_connected_message(), stt_error()])

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(_pcm(), real_time=False, idle_grace_ms=80)

    result = run(scenario())
    assert result.errors and "failed to initialize" in result.errors[0].message


def test_malformed_json_is_a_protocol_error():
    with pytest.raises(ProtocolError):
        decode_json_message("{not json")
    with pytest.raises(ProtocolError):
        decode_json_message(json.dumps(["not", "an", "object"]))
    with pytest.raises(ProtocolError):
        decode_json_message(json.dumps({"no_type": True}))


def test_an_oversized_response_is_rejected_before_it_is_parsed():
    oversized = "x" * (MAX_MESSAGE_BYTES + 10)
    with pytest.raises(ProtocolError):
        decode_json_message(oversized)


def test_a_structurally_invalid_frame_is_a_protocol_error():
    """Not JSON, not an object, or no string type: a hard protocol failure."""
    with pytest.raises(ProtocolError):
        decode_json_message("{not json")
    with pytest.raises(ProtocolError):
        decode_json_message(json.dumps(["not", "an", "object"]))
    with pytest.raises(ProtocolError):
        decode_json_message(json.dumps({"no_type": True}))


def test_a_well_formed_frame_of_an_unknown_type_is_recorded_not_dropped():
    """Protocol drift must stay visible without making the adapter unusable.

    Observed live on 2026-10-18: the server emits `speech_start`, which is
    absent from the published message list.
    """
    transport = FakeTransport(
        scripted=[
            stt_connected_message(),
            json.dumps(
                {
                    "type": "speech_start",
                    "timestamp": "2024-01-15T10:30:04.000Z",
                    "utterance_id": "abc-123",
                }
            ),
            stt_transcript("hello", segment_id="s1", segment_index=1),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(_pcm(), real_time=False, idle_grace_ms=80)

    result = run(scenario())
    assert len(result.unrecognized_frames) == 1
    frame = result.unrecognized_frames[0]
    assert frame.message_type == "speech_start"
    assert "utterance_id" in frame.keys
    # The adapter kept working: the transcript is still delivered.
    assert result.segment_count == 1
    assert result.text == "hello"


def test_a_missing_connected_frame_is_a_protocol_error():
    transport = FakeTransport(scripted=[stt_transcript("orphan")])

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(_pcm(), real_time=False)

    with pytest.raises(ProtocolError):
        run(scenario())


def test_fencing_stops_consumption_and_is_idempotent():
    transport = FakeTransport(scripted=[stt_connected_message()])

    async def scenario():
        session = _session(transport)
        async with session:
            await session.fence()
            await session.fence()   # idempotent
            await session.aclose()  # also idempotent
            return session

    session = run(scenario())
    assert session._closed is True
    # An injected transport is caller-owned, so the session does not close
    # it: exactly the ownership rule the real transport depends on.
    assert transport.close_calls == 0


def test_a_session_owns_and_closes_the_transport_it_created():
    created: list[object] = []

    class _Owned(FakeTransport):
        async def __aenter__(self):
            created.append(self)
            return self

    from gnani_coach.providers.stt import GnaniSttSession as _S
    import gnani_coach.providers.stt as stt_module

    original = stt_module.WebSocketTransport

    def _factory(url, headers):
        return _Owned(scripted=[stt_connected_message()])

    stt_module.WebSocketTransport = _factory
    try:
        transport = _Owned(scripted=[stt_connected_message()])
        session = _S(build_config("en-IN"), DUMMY_GNANI_KEY, transport=transport)
        # Force the session to treat the transport as its own.
        session._owns_transport = True
        run(session.aclose())
        assert transport.close_calls == 1
        run(session.aclose())
        assert transport.close_calls == 1, "close must happen exactly once"
    finally:
        stt_module.WebSocketTransport = original


def test_the_sample_clock_survives_the_stream_and_records_padding_separately():
    transport = FakeTransport(scripted=[stt_connected_message(), stt_transcript()])
    pcm = b"\x00\x01" * 300  # 600 bytes -> partial frame

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(pcm, real_time=False, idle_grace_ms=80)

    result = run(scenario())
    assert result.sample_clock.to_ms(result.sample_clock.genuine_samples) == pytest.approx(
        round(600 / 2 * 1000 / 16000)
    )
    assert result.end_padding_ms > 0
    assert result.sample_clock.to_ms(result.sample_clock.genuine_samples) != (
        result.sample_clock.to_ms(result.sample_clock.submitted_samples)
    )


def test_submitted_audio_is_charged_to_the_budget_not_just_counted():
    transport = FakeTransport(scripted=[stt_connected_message()])
    budget = ProbeBudget()

    async def scenario():
        async with _session(transport, budget=budget) as session:
            return await session.stream_pcm(
                _pcm(0.5), real_time=False, idle_grace_ms=60, trailing_silence_ms=0
            )

    result = run(scenario())
    assert budget.audio_seconds_used == pytest.approx(0.5, abs=0.05)
    assert budget.wire_attempts_used >= 2
    assert budget.per_kind.get("gnani-stt:session") == 1


def test_trailing_silence_is_charged_as_submitted_but_not_as_learner_speech():
    """The server's VAD closes on silence, so padding must be sent — and
    charged as submitted audio without ever entering the genuine span."""
    transport = FakeTransport(scripted=[stt_connected_message()])
    budget = ProbeBudget()
    clip = _pcm(0.5)  # 0.5 s of real audio

    async def scenario():
        async with _session(transport, budget=budget) as session:
            return await session.stream_pcm(
                clip, real_time=False, idle_grace_ms=60, trailing_silence_ms=800
            )

    result = run(scenario())
    clock = result.sample_clock
    assert clock.to_ms(clock.genuine_samples) == pytest.approx(500, abs=5)
    assert clock.to_ms(clock.padding_samples) >= 800
    # Budget counts everything submitted, including the silence.
    assert budget.audio_seconds_used >= 1.3
    assert budget.audio_seconds_used <= 1.5


def test_the_documented_session_ceiling_is_not_mistaken_for_the_probe_budget():
    from gnani_coach.providers.limits import MAX_AUDIO_SECONDS
    from gnani_coach.providers.transport import DOCUMENTED_SESSION_CEILING_SECONDS

    assert MAX_AUDIO_SECONDS == 300.0
    assert DOCUMENTED_SESSION_CEILING_SECONDS == 900
    # A probe never approaches the provider's connection ceiling.
    assert MAX_AUDIO_SECONDS < DOCUMENTED_SESSION_CEILING_SECONDS


def test_a_vad_closed_segment_is_not_reported_as_a_conversational_turn():
    """A VAD-closed segment is metadata about the provider, not a turn."""
    transport = FakeTransport(
        scripted=[
            stt_connected_message(),
            stt_transcript("one", segment_id="a", segment_index=0),
            stt_transcript("two", segment_id="b", segment_index=1),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(_pcm(), real_time=False, idle_grace_ms=80)

    result = run(scenario())
    # SttResult exposes segments; it exposes no notion of "turn".
    assert not hasattr(result, "turns")
    assert result.segment_count == 2


def test_server_reported_timing_is_kept_as_metadata_only():
    transport = FakeTransport(
        scripted=[
            stt_connected_message(),
            stt_transcript("x", duration_ms=2340, latency_ms=320),
        ]
    )

    async def scenario():
        async with _session(transport) as session:
            return await session.stream_pcm(_pcm(), real_time=False, idle_grace_ms=80)

    result = run(scenario())
    event = result.transcripts[0]
    assert event.audio_duration_ms == 2340
    assert event.latency_ms == 320
    # The only sample-clock anchor is the local one.
    assert event.learner_clock_samples >= 0
    assert not hasattr(event, "word_start_ms")
