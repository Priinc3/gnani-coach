"""The container of an opted-in recording.

The runtime's recording buffer is **raw PCM**: the learner's frames exactly
as they arrived, 16 kHz mono s16le, with no header. A stored recording is
served back as ``audio/wav`` and played by a browser, which cannot decode
headerless PCM as WAV. This module is the single conversion:

* the samples are unchanged — nothing is resampled, mixed or trimmed;
* :func:`wav_bytes` puts a canonical 44-byte RIFF/WAVE header in front of
  them, written by the standard library's :mod:`wave` module, so there is
  no new dependency;
* :func:`pcm_duration_ms` states the duration of the same samples, so the
  metadata and the file agree.
"""

from __future__ import annotations

import io
import wave

#: The one format this service accepts and records.
SAMPLE_RATE_HZ = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2


def pcm_duration_ms(
    pcm: bytes,
    *,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
    channels: int = CHANNELS,
    sample_width_bytes: int = SAMPLE_WIDTH_BYTES,
) -> int:
    """The duration of ``pcm``, from its sample count.

    A whole frame is a sample of every channel; a trailing partial frame
    is ignored, as it cannot be played.
    """
    frame_bytes = max(1, channels * sample_width_bytes)
    frames = len(pcm) // frame_bytes
    return int(frames * 1000 / sample_rate_hz)


def wav_bytes(
    pcm: bytes,
    *,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
    channels: int = CHANNELS,
    sample_width_bytes: int = SAMPLE_WIDTH_BYTES,
) -> bytes:
    """``pcm`` wrapped in a canonical RIFF/WAVE header.

    The samples are copied verbatim, so the result plays back exactly the
    audio that was buffered.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width_bytes)
        writer.setframerate(sample_rate_hz)
        writer.writeframes(pcm)
    return buffer.getvalue()


__all__ = [
    "CHANNELS",
    "SAMPLE_RATE_HZ",
    "SAMPLE_WIDTH_BYTES",
    "pcm_duration_ms",
    "wav_bytes",
]
