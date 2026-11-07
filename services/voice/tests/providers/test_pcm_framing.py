"""PCM framing, pacing, partial-tail and sample-clock rules [P1].

The documented STT contract is 1,024-byte raw PCM frames paced at the
real sample rate. These tests pin that behaviour and, critically, that a
WAV header can never become a stream frame.
"""

from __future__ import annotations

import numpy as np
import pytest

from gnani_coach.providers.errors import InvalidRequestError
from gnani_coach.providers.pcm import (
    FRAME_BYTES,
    SAMPLES_PER_FRAME,
    SampleClock,
    encode_wav,
    frame_duration_ms,
    frames,
    pad_to_frame,
    pcm_seconds,
    resample,
    strip_wav_header,
)
from _helpers import run


def test_frame_is_exactly_1024_bytes_and_512_samples():
    assert FRAME_BYTES == 1024
    assert SAMPLES_PER_FRAME == 512


@pytest.mark.parametrize(
    ("rate", "expected_ms"), [(8000, 64.0), (16000, 32.0), (44100, 11.61), (48000, 10.67)]
)
def test_frame_duration_matches_the_documented_cadence(rate, expected_ms):
    assert frame_duration_ms(rate) == pytest.approx(expected_ms, rel=1e-3)


def test_frames_are_uniformly_sized_and_reassemble_to_the_input():
    pcm = bytes(range(256)) * 40  # 10240 bytes -> exactly 10 frames
    produced = list(frames(pcm, sample_rate=16000))
    assert len(produced) == 10
    assert all(len(chunk) == FRAME_BYTES for chunk in produced)
    assert b"".join(produced) == pcm


def test_partial_tail_is_padded_and_the_padding_is_reported_separately():
    raw = b"\x01\x02" * 300  # 600 bytes, not a whole number of frames
    padded, pad_bytes = pad_to_frame(raw)
    assert pad_bytes == FRAME_BYTES - 600
    assert len(padded) % FRAME_BYTES == 0
    # Genuine length is unaffected by the padding.
    assert pcm_seconds(raw, 16000) == pytest.approx(600 / 2 / 16000)
    assert len(padded) > len(raw)


def test_dropping_a_partial_tail_never_invents_audio_or_hides_real_audio():
    raw = b"\x01\x02" * 768  # 1536 bytes: one whole frame plus a 512-byte tail
    with_tail = b"".join(frames(raw, sample_rate=16000, include_tail=True))
    without_tail = b"".join(frames(raw, sample_rate=16000, include_tail=False))
    # With a tail: 2 frames (the second zero-padded). Without: 1 real frame.
    assert len(with_tail) == 2048
    assert len(without_tail) == 1024
    # Dropping the tail never fabricates samples and never drops real ones.
    assert without_tail == raw[:1024]
    assert with_tail[:1024] == raw[:1024]


def test_a_clip_shorter_than_one_frame_yields_nothing_without_a_tail():
    raw = b"\x01\x02" * 100  # 200 bytes
    assert b"".join(frames(raw, sample_rate=16000, include_tail=False)) == b""
    assert len(b"".join(frames(raw, sample_rate=16000, include_tail=True))) == 1024


def test_a_wav_header_is_never_emitted_as_a_stream_frame():
    samples = (np.sin(np.arange(4000) * 0.05) * 8000).astype(np.int16)
    wav = encode_wav(samples, 16000)
    assert wav[:4] == b"RIFF"
    pcm = strip_wav_header(wav)
    assert pcm[:4] != b"RIFF"
    for chunk in frames(pcm, sample_rate=16000):
        assert len(chunk) == FRAME_BYTES
        assert chunk[:4] != b"RIFF"


def test_strip_wav_header_rejects_non_wav_payloads():
    with pytest.raises(InvalidRequestError):
        strip_wav_header(b"ID3\x04not a wav file")


def test_resampling_records_its_source_offset_and_method():
    samples = (np.sin(np.arange(16000) * 0.01) * 8000).astype(np.int16)
    native = resample(samples, 16000, 16000)
    assert native.native is True
    assert native.method == "none"
    assert native.source_offset_samples == 0

    converted = resample(samples, 48000, 16000)
    assert converted.native is False
    assert converted.method == "linear"
    # A converted clip carries provenance that a native-rate clip does not.
    assert converted.source_rate == 48000


def test_sample_clock_separates_genuine_audio_from_end_padding():
    clock = SampleClock(sample_rate=16000)
    clock.advance(16000)          # 1.0 s of real audio
    clock.add_padding(8000)       # 0.5 s of zero padding
    assert clock.to_ms(clock.genuine_samples) == 1000
    assert clock.to_ms(clock.padding_samples) == 500
    assert clock.to_ms(clock.submitted_samples) == 1500
    # The elapsed learner span excludes padding entirely.
    assert clock.genuine_seconds == pytest.approx(1.0)
    assert clock.submitted_seconds == pytest.approx(1.5)


def test_sample_clock_refuses_to_move_backwards():
    clock = SampleClock(sample_rate=16000)
    with pytest.raises(InvalidRequestError):
        clock.advance(-1)


def test_sample_clock_marks_are_anchored_to_sample_positions_not_network_time():
    clock = SampleClock(sample_rate=16000)
    clock.mark(100.0)
    clock.advance(32000)
    clock.mark(101.9)
    positions = [samples for samples, _ in clock.marks]
    assert positions[0] == 0
    assert positions[1] == 32000


def test_the_summary_keeps_genuine_and_submitted_lengths_separate():
    clock = SampleClock(sample_rate=16000)
    clock.advance(8000)
    clock.add_padding(2400)
    summary = clock.summary()
    assert summary["genuine_ms"] == 500
    assert summary["padding_ms"] == 150
    assert summary["submitted_ms"] == 650


def test_pcm_seconds_counts_real_samples_not_frames():
    assert pcm_seconds(b"\x00" * FRAME_BYTES, 16000) == pytest.approx(0.032)
    assert pcm_seconds(b"\x00" * FRAME_BYTES, 8000) == pytest.approx(0.064)
