"""The recording container: raw PCM in, a canonical WAV out.

The runtime buffers the learner's frames as raw 16 kHz mono s16le PCM.
The store records the object as ``audio/wav`` and a browser plays what it
is given, so the bytes the store receives must be a real WAV — the same
samples behind a 44-byte RIFF/WAVE header. These tests read the header
back with the standard library's parser, not with a hand-written one.
"""

from __future__ import annotations

import io
import struct
import wave

from gnani_coach.conversation.audio import pcm_duration_ms, wav_bytes
from phase05_support import FRAME_BYTES, loud_frame

#: One frame of the fake learner audio: 512 samples of s16le.
SAMPLES_PER_FRAME = 512


def test_the_wav_container_is_canonical() -> None:
    """The bytes start with RIFF/WAVE/fmt and carry the same samples."""
    pcm = loud_frame() * 3

    data = wav_bytes(pcm)

    assert data[:4] == b"RIFF"
    assert data[4:8] == struct.pack("<I", len(data) - 8)
    assert data[8:16] == b"WAVEfmt "
    assert len(data) == 44 + len(pcm)

    with wave.open(io.BytesIO(data), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getframerate() == 16_000
        assert reader.getsampwidth() == 2
        assert reader.getnframes() == SAMPLES_PER_FRAME * 3
        assert reader.readframes(reader.getnframes()) == pcm


def test_the_frame_count_matches_the_buffer() -> None:
    """One 1 024-byte frame is 512 samples, and the WAV says so."""
    pcm = loud_frame()

    assert len(pcm) == FRAME_BYTES
    data = wav_bytes(pcm)
    with wave.open(io.BytesIO(data), "rb") as reader:
        assert reader.getnframes() == len(pcm) // 2


def test_the_duration_is_the_sample_count() -> None:
    """The metadata duration and the WAV frame count are the same number."""
    pcm = loud_frame() * 10
    samples = len(pcm) // 2

    assert pcm_duration_ms(pcm) == int(samples * 1000 / 16_000)
    data = wav_bytes(pcm)
    with wave.open(io.BytesIO(data), "rb") as reader:
        assert reader.getnframes() == samples
        assert pcm_duration_ms(pcm) == int(reader.getnframes() * 1000 / 16_000)


def test_an_empty_buffer_is_a_valid_empty_wav() -> None:
    """The helper itself is total; the runtime refuses an empty buffer."""
    with wave.open(io.BytesIO(wav_bytes(b"")), "rb") as reader:
        assert reader.getnframes() == 0
    assert pcm_duration_ms(b"") == 0
