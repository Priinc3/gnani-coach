"""PCM framing, WAV handling, and the local audio sample clock.

The Gnani realtime STT contract (checked 2026-10-18 against
https://docs.gnani.ai/api/STT/stt-websocket) is:

* raw **mono signed 16-bit little-endian PCM** only — no container may be
  sent mid-stream;
* every binary frame is **exactly 1,024 bytes** (512 samples x 2 bytes);
* frames are paced at the *actual* sample rate: 32 ms at 16 kHz, 64 ms at
  8 kHz, and proportionally faster at 44.1/48 kHz.

Two rules this module exists to enforce:

1. **A WAV header is never sent as a stream frame.** :func:`frames`
   operates on de-headered samples only.
2. **The local sample clock is separate from wall-clock/network time.**
   :class:`SampleClock` counts samples actually submitted. Genuine clip
   length and any deliberate end padding are recorded distinctly, so a
   padded silence tail can never be reported as learner speech span.
"""

from __future__ import annotations

import io
import wave
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from gnani_coach.providers.errors import InvalidRequestError

FRAME_BYTES = 1024
SAMPLES_PER_FRAME = FRAME_BYTES // 2  # 512 samples, 16-bit mono
SUPPORTED_SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)
STT_SAMPLE_RATES = (8000, 16000, 44100, 48000)  # accepted by x-sample-rate


def frame_duration_ms(sample_rate: int) -> float:
    """Duration of one 1,024-byte frame at ``sample_rate``."""
    if sample_rate <= 0:
        raise InvalidRequestError(f"invalid sample_rate {sample_rate!r}")
    return SAMPLES_PER_FRAME * 1000.0 / sample_rate


# ---------------------------------------------------------------------------
# WAV container <-> raw PCM
# ---------------------------------------------------------------------------


def decode_wav(data: bytes) -> tuple[np.ndarray, int, int]:
    """Decode a mono/stereo 16-bit PCM WAV to int16 samples + sample rate.

    Returns ``(samples, sample_rate, source_channels)``. A stereo source is
    **not** silently downmixed here — the caller decides, because averaging
    channels changes the signal and the chosen policy must be recorded.
    """
    with wave.open(io.BytesIO(data), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if width != 2:
        raise InvalidRequestError(
            f"only signed 16-bit PCM WAV is supported (got sample width {width})"
        )
    if rate not in SUPPORTED_SAMPLE_RATES:
        raise InvalidRequestError(f"unsupported WAV sample rate {rate}")
    samples = np.frombuffer(frames, dtype="<i2")
    if channels > 1:
        samples = samples.reshape(-1, channels)
    else:
        samples = samples.reshape(-1)
    return samples, rate, channels


def to_mono(samples: np.ndarray, channels: int) -> np.ndarray:
    """Downmix to mono with an explicit, documented policy."""
    if channels == 1:
        return np.asarray(samples, dtype=np.int16)
    if channels == 2:
        averaged = (samples[:, 0].astype(np.int32) + samples[:, 1].astype(np.int32)) // 2
        return averaged.astype(np.int16)
    raise InvalidRequestError(f"unsupported channel count {channels}")


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Wrap raw int16 mono samples in a WAV container (for fixtures only).

    Never used on the STT stream: the provider accepts raw PCM frames only.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return buffer.getvalue()


def strip_wav_header(data: bytes) -> bytes:
    """Return the raw PCM payload of a WAV file, rejecting non-WAV input.

    Used by fixtures so a header can never leak into a stream frame.
    """
    if not data.startswith(b"RIFF") or not data.startswith(b"WAVE", 8):
        raise InvalidRequestError("not a RIFF/WAVE payload")
    with wave.open(io.BytesIO(data), "rb") as handle:
        return handle.readframes(handle.getnframes())


# ---------------------------------------------------------------------------
# Resampling (documented, with explicit offset accounting)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResampleResult:
    samples: np.ndarray
    source_rate: int
    target_rate: int
    #: Input samples consumed before the first output sample, in source
    #: samples. Recorded so a reviewer can see the provenance offset that a
    #: resampled clip carries versus a native-rate clip.
    source_offset_samples: int
    #: True when the clip was already at the target rate (offset 0).
    native: bool
    method: str


def resample(samples: np.ndarray, source_rate: int, target_rate: int) -> ResampleResult:
    """Resample int16 mono audio to ``target_rate``.

    Linear interpolation is used deliberately: it is deterministic, has no
    hidden dependency, and is adequate for the *analysis* path. This is
    **not** a high-quality resampler, and a resampled clip's boundary labels
    are correspondingly approximate — recorded in the fixture manifest.
    """
    samples = np.asarray(samples, dtype=np.float64)
    if source_rate == target_rate:
        return ResampleResult(
            samples.astype(np.int16),
            source_rate,
            target_rate,
            0,
            True,
            "none",
        )
    if source_rate <= 0 or target_rate <= 0:
        raise InvalidRequestError("resampling requires positive sample rates")
    duration = len(samples) / source_rate
    out_length = max(1, int(round(duration * target_rate)))
    source_positions = np.arange(out_length) * (source_rate / target_rate)
    resampled = np.interp(
        source_positions, np.arange(len(samples)), samples, left=0.0, right=0.0
    )
    return ResampleResult(
        np.clip(np.round(resampled), -32768, 32767).astype(np.int16),
        source_rate,
        target_rate,
        0,
        False,
        "linear",
    )


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def frames(pcm: bytes, *, sample_rate: int, include_tail: bool = True) -> Iterator[bytes]:
    """Yield 1,024-byte frames from **raw** PCM.

    Parameters
    ----------
    include_tail:
        When ``False`` a trailing partial frame is dropped, which is the
        safe choice for a *submission* budget: a short final frame is still
        a valid message but the padding it implies is not real audio. The
        probe records which policy was used.
    """
    if len(pcm) < FRAME_BYTES and not include_tail:
        return
    offset = 0
    total = len(pcm)
    while offset < total:
        chunk = pcm[offset : offset + FRAME_BYTES]
        if len(chunk) < FRAME_BYTES:
            if not include_tail:
                return
            chunk = chunk + b"\x00" * (FRAME_BYTES - len(chunk))
        yield chunk
        offset += FRAME_BYTES


def pad_to_frame(pcm: bytes) -> tuple[bytes, int]:
    """Zero-pad to a frame boundary, returning the padded PCM and pad bytes.

    The pad count is returned so genuine audio length stays separable from
    end padding in every measurement.
    """
    remainder = len(pcm) % FRAME_BYTES
    if remainder == 0:
        return pcm, 0
    pad = FRAME_BYTES - remainder
    return pcm + b"\x00" * pad, pad


def pcm_seconds(pcm: bytes, sample_rate: int) -> float:
    """Seconds of real audio in ``pcm`` (no padding assumed)."""
    return (len(pcm) // 2) / float(sample_rate)


# ---------------------------------------------------------------------------
# Local sample clock
# ---------------------------------------------------------------------------


@dataclass
class SampleClock:
    """A local, sample-accurate clock for one learner audio stream.

    This is the **only** clock that may anchor an evidence span. Wall-clock
    connection time, network latency and provider emission timestamps are
    recorded alongside but never used to place a pause.
    """

    sample_rate: int
    submitted_samples: int = 0
    genuine_samples: int = 0
    padding_samples: int = 0
    #: Monotonic wall-clock marks (seconds) for diagnostics only.
    started_at: float | None = None
    finished_at: float | None = None
    marks: list[tuple[int, float]] = field(default_factory=list)

    def mark(self, wall_seconds: float) -> None:
        """Record a wall-clock instant against the current sample position."""
        self.marks.append((self.submitted_samples, float(wall_seconds)))

    def advance(self, samples: int) -> None:
        if samples < 0:
            raise InvalidRequestError("sample clock cannot move backwards")
        self.submitted_samples += samples
        self.genuine_samples += samples
        self.padding_samples += 0

    def add_padding(self, samples: int) -> None:
        self.submitted_samples += samples
        self.padding_samples += samples

    # -- derived values -------------------------------------------------
    @property
    def genuine_seconds(self) -> float:
        """Elapsed learner audio span, padding excluded."""
        return self.genuine_samples / float(self.sample_rate)

    @property
    def submitted_seconds(self) -> float:
        """Everything actually written to the socket, padding included."""
        return self.submitted_samples / float(self.sample_rate)

    @property
    def padding_seconds(self) -> float:
        return self.padding_samples / float(self.sample_rate)

    def to_ms(self, samples: int) -> int:
        """Sample position -> integer milliseconds on the learner clock."""
        if self.sample_rate <= 0:
            raise InvalidRequestError("sample clock needs a positive sample rate")
        return int(round(samples * 1000.0 / self.sample_rate))

    def summary(self) -> dict[str, object]:
        return {
            "sample_rate": self.sample_rate,
            "genuine_samples": self.genuine_samples,
            "submitted_samples": self.submitted_samples,
            "padding_samples": self.padding_samples,
            "genuine_ms": self.to_ms(self.genuine_samples),
            "padding_ms": self.to_ms(self.padding_samples),
            "submitted_ms": self.to_ms(self.submitted_samples),
        }
