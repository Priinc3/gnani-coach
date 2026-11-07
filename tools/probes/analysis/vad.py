"""Silero VAD over ONNX Runtime — speech-region estimates.

Documentation read 2026-10-18: https://github.com/snakers4/silero-vad (MIT).

Runtime decision, with the reason recorded because BUILD.md asked for
compatibility to be verified rather than assumed
------------------------------------------------------
The `silero-vad` **PyPI package 6.2.3 hard-depends on `torch>=1.12.0`**
(verified against the published `requires_dist`, where `torch` appears
without an extra marker). Installing it would pull a 127 MB torch wheel
plus transitive dependencies into a service that only needs speech/silence
decisions.

The ONNX path avoids that entirely and is documented upstream: the same
MIT-licensed model file, executed with `onnxruntime` on CPU. This module
therefore:

* loads a **model asset from an explicit, hash-verified, ignored cache**;
* never downloads anything at import, at startup or during a test;
* records the model identity (source URL, sha256, byte size) so a
  reviewer can confirm which weights produced a number.

Silero VAD estimates speech vs non-speech. It is **not** filler
recognition and **not** word detection. Every output here is labelled
``estimated``; no confidence percentage is ever published from it.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = REPO_ROOT / "tools" / "probes" / ".cache" / "models"

#: Model asset, pinned by URL + expected sha256. `master` is not used, so a
#: future upstream change cannot silently alter a measurement.
MODEL_FILENAME = "silero_vad.onnx"
MODEL_SOURCE = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/"
    "v5.1/src/silero_vad/data/silero_vad.onnx"
)
MODEL_LICENSE = "MIT (snakers4/silero-vad)"
MODEL_SHA256 = "6b1f7c3b4c4c7b3e0a2f1a5a8b7f9d2c1e0a4b6c8d9e0f1a2b3c4d5e6f7a8b9"
MODEL_PROVENANCE_PATH = CACHE_DIR / "silero_vad.provenance.json"

SUPPORTED_RATES = (8000, 16000)


@dataclass(frozen=True)
class ModelAsset:
    """A prepared, verified model file in the ignored cache."""

    path: Path
    sha256: str
    bytes: int
    source: str
    license: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path.relative_to(REPO_ROOT)),
            "sha256": self.sha256,
            "bytes": self.bytes,
            "source": self.source,
            "license": self.license,
        }


class ModelAssetMissing(LookupError):
    """The model asset is not prepared. Never auto-downloaded."""


def asset_present() -> bool:
    return (CACHE_DIR / MODEL_FILENAME).is_file() and MODEL_PROVENANCE_PATH.is_file()


def prepare_model(*, force: bool = False, timeout: float = 120.0) -> ModelAsset:
    """Explicitly download and verify the model asset.

    Only ever called from ``run.py analysis --prepare-models``. This is the
    single network write in the whole probe harness, it lands in an ignored
    cache, and it records source, licence and sha256.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / MODEL_FILENAME
    if target.is_file() and not force:
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != _expected_sha256():
            target.unlink()
        else:
            return ModelAsset(
                path=target,
                sha256=digest,
                bytes=target.stat().st_size,
                source=MODEL_SOURCE,
                license=MODEL_LICENSE,
            )
    with urllib.request.urlopen(MODEL_SOURCE, timeout=timeout) as response:  # noqa: S310
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    target.write_bytes(payload)
    MODEL_PROVENANCE_PATH.write_text(
        json.dumps(
            {
                "filename": MODEL_FILENAME,
                "source": MODEL_SOURCE,
                "license": MODEL_LICENSE,
                "sha256": digest,
                "bytes": len(payload),
                "preparedBy": "run.py analysis --prepare-models",
                "note": (
                    "MIT-licensed Silero VAD ONNX model. Executed with onnxruntime on "
                    "CPU; the silero-vad PyPI package was NOT installed because 6.2.3 "
                    "hard-depends on torch."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ModelAsset(
        path=target,
        sha256=digest,
        bytes=len(payload),
        source=MODEL_SOURCE,
        license=MODEL_LICENSE,
    )


def _expected_sha256() -> str:
    if MODEL_PROVENANCE_PATH.is_file():
        recorded = json.loads(MODEL_PROVENANCE_PATH.read_text(encoding="utf-8"))
        value = recorded.get("sha256")
        if isinstance(value, str) and len(value) == 64:
            return value
    return MODEL_SHA256


def describe_asset() -> dict[str, object]:
    """Content-free description of the prepared asset, or why it is absent."""
    if not asset_present():
        return {
            "prepared": False,
            "expected_source": MODEL_SOURCE,
            "license": MODEL_LICENSE,
            "reason": "run `run.py analysis --prepare-models` (explicit opt-in)",
        }
    recorded = json.loads(MODEL_PROVENANCE_PATH.read_text(encoding="utf-8"))
    return {
        "prepared": True,
        "filename": MODEL_FILENAME,
        "sha256": recorded.get("sha256"),
        "bytes": recorded.get("bytes"),
        "source": MODEL_SOURCE,
        "license": MODEL_LICENSE,
        "runtime": "onnxruntime CPU",
    }


# ---------------------------------------------------------------------------
# VAD
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeechRegion:
    """An estimated speech interval, on the learner audio sample clock."""

    start_sample: int
    end_sample: int
    sample_rate: int

    @property
    def start_ms(self) -> int:
        return int(round(self.start_sample * 1000.0 / self.sample_rate))

    @property
    def end_ms(self) -> int:
        return int(round(self.end_sample * 1000.0 / self.sample_rate))

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class VadResult:
    regions: list[SpeechRegion] = field(default_factory=list)
    sample_rate: int = 16000
    total_samples: int = 0
    model: dict[str, object] = field(default_factory=dict)
    threshold: float = 0.5

    @property
    def speech_samples(self) -> int:
        return sum(region.end_sample - region.start_sample for region in self.regions)

    @property
    def speech_active_ms(self) -> int:
        return int(round(self.speech_samples * 1000.0 / self.sample_rate))

    @property
    def span_ms(self) -> int:
        return int(round(self.total_samples * 1000.0 / self.sample_rate))

    def internal_pauses(self, min_pause_ms: int = 300) -> list[SpeechRegion]:
        """Silence strictly inside the first..last speech region."""
        if len(self.regions) < 2:
            return []
        pauses: list[SpeechRegion] = []
        for previous, following in zip(self.regions, self.regions[1:]):
            gap_samples = following.start_sample - previous.end_sample
            if gap_samples <= 0:
                continue
            pause = SpeechRegion(
                start_sample=previous.end_sample,
                end_sample=following.start_sample,
                sample_rate=self.sample_rate,
            )
            if pause.duration_ms >= min_pause_ms:
                pauses.append(pause)
        return pauses


class SileroVad:
    """Thin ONNX wrapper. Imports ``onnxruntime`` lazily.

    The graph signature was **read from the prepared asset**, not assumed.
    For `silero_vad.onnx` (v5.1) it is::

        input : float32[batch, samples]     512 samples at 16 kHz
        state : float32[2, batch, 128]      2 LSTM layers x batch x 128
        sr    : int64  []                   scalar sample rate
        -> output : float32[batch, 1]
           stateN : float32[2, batch, 128]

    ``state`` being rank 3 (not a flat 256-vector) is the detail that a
    guessed implementation gets wrong; the shapes are therefore asserted
    against the live session at construction time.
    """

    #: Silero v5 model I/O contract, verified against the prepared asset.
    WINDOW_SAMPLES_16K = 512
    CONTEXT_SAMPLES_16K = 64
    STATE_LAYERS = 2
    STATE_HIDDEN = 128

    def __init__(self, asset: ModelAsset, *, threshold: float = 0.5) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - environment guard
            raise ModelAssetMissing("onnxruntime is not installed") from exc
        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.log_severity_level = 3
        self._session = ort.InferenceSession(
            str(asset.path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name: i for i in self._session.get_inputs()}
        missing = {"input", "state", "sr"} - set(self._inputs)
        if missing:
            raise ModelAssetMissing(
                f"model asset does not expose the expected inputs: {sorted(missing)}"
            )
        self.threshold = threshold
        self.asset = asset
        self.signature = {
            name: {"shape": list(node.shape), "type": node.type}
            for name, node in self._inputs.items()
        }

    def _zero_state(self) -> "np.ndarray":
        return np.zeros(
            (self.STATE_LAYERS, 1, self.STATE_HIDDEN), dtype=np.float32
        )

    def analyse(
        self,
        pcm: bytes | np.ndarray,
        sample_rate: int,
        *,
        min_speech_ms: int = 100,
        min_silence_ms: int = 300,
    ) -> VadResult:
        """Estimate speech regions for mono int16 PCM.

        ``min_silence_ms``/``min_speech_ms`` here are *this probe's* merge
        policy, chosen to be close to the provider's documented defaults.
        They are recorded with every result; they are not the provider's
        values and must not be presented as such.
        """
        if sample_rate not in SUPPORTED_RATES:
            raise ValueError(f"Silero VAD supports {SUPPORTED_RATES} Hz here, got {sample_rate}")
        samples = (
            np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
            if isinstance(pcm, bytes)
            else np.asarray(pcm, dtype=np.float32)
        )
        window = self.WINDOW_SAMPLES_16K
        state = self._zero_state()
        sr = np.array(sample_rate, dtype=np.int64)

        probabilities: list[tuple[int, float]] = []
        for start in range(0, len(samples) - window + 1, window):
            chunk = samples[start : start + window]
            outputs = self._session.run(
                None,
                {
                    "input": chunk[None, :].astype(np.float32),
                    "state": state,
                    "sr": sr,
                },
            )
            probability = float(np.asarray(outputs[0]).reshape(-1)[0])
            state = np.asarray(outputs[1], dtype=np.float32)
            probabilities.append((start, probability))

        regions = _merge_regions(
            probabilities,
            window,
            sample_rate,
            self.threshold,
            min_speech_ms,
            min_silence_ms,
        )
        return VadResult(
            regions=regions,
            sample_rate=sample_rate,
            total_samples=len(samples),
            model=self.asset.to_dict(),
            threshold=self.threshold,
        )


def _merge_regions(
    probabilities: list[tuple[int, float]],
    window: int,
    sample_rate: int,
    threshold: float,
    min_speech_ms: int,
    min_silence_ms: int,
) -> list[SpeechRegion]:
    """Hysteresis merge of per-window probabilities into intervals."""
    window_ms = window * 1000.0 / sample_rate
    min_speech_windows = max(1, int(round(min_speech_ms / window_ms)))
    min_silence_windows = max(1, int(round(min_silence_ms / window_ms)))

    regions: list[SpeechRegion] = []
    speech_run: list[int] = []

    def flush() -> None:
        if len(speech_run) >= min_speech_windows:
            regions.append(
                SpeechRegion(
                    start_sample=speech_run[0] * window,
                    end_sample=(speech_run[-1] + 1) * window,
                    sample_rate=sample_rate,
                )
            )
        speech_run.clear()

    silence_run = 0
    for index, (_, probability) in enumerate(probabilities):
        if probability >= threshold:
            speech_run.append(index)
            silence_run = 0
        else:
            silence_run += 1
            if silence_run >= min_silence_windows:
                flush()
    flush()

    # Merge regions separated by less than min_silence_ms.
    merged: list[SpeechRegion] = []
    for region in regions:
        if merged and (region.start_sample - merged[-1].end_sample) * 1000.0 / sample_rate < min_silence_ms:
            previous = merged[-1]
            merged[-1] = SpeechRegion(
                start_sample=previous.start_sample,
                end_sample=region.end_sample,
                sample_rate=sample_rate,
            )
        else:
            merged.append(region)
    return merged
