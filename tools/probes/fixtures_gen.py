"""Synthetic fixture generation for the Phase 02 probes.

Everything here is **synthetic**. No learner microphone, no recorded call,
no personal data. Two classes of fixture exist and they are not
interchangeable:

**Offline analytic fixtures** (no speech provider involved)
    Built from deterministic synthesis in this file: digital silence,
    seeded pseudo-noise, and *marked* tone bursts used as speech-shaped
    placeholders. Their exact sample indices are known by construction, so
    gap labels are exact. They prove that the measurement pipeline, the
    framing and the gap-preservation logic work. They prove **nothing**
    about a recogniser or about natural speech.

**Prepared spoken fixtures** (need an explicitly prepared speech source)
    Real speech must come from somewhere explicitly prepared and recorded
    in the manifest: a locally available TTS engine or a human reviewer.
    This generator does **not** download a voice and does **not** claim a
    spoken fixture exists. ``build_spoken`` records
    ``label_provenance.reviewed_by = null`` and refuses to claim a filler
    label that nobody listened to.

Honesty rules encoded here
--------------------------
* A TTS input script is **not** evidence that the rendered audio contains
  a hesitation. Normalisation may remove it. Every spoken fixture therefore
  records ``filler_labels_verified: false`` until a named reviewer has
  listened and confirmed.
* Silence and gaps are inserted at **known sample indices** and those
  indices are written to the manifest before any measurement runs, so a
  later chunking or conversion step can be checked against them.
* Generated audio stays **ignored** by the repository's existing rules.
  The manifest and recipes are the committed artefacts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from gnani_coach.providers.pcm import encode_wav

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1
GENERATOR_NAME = "gnani-coach-phase02-fixture-generator"
GENERATOR_VERSION = "1.0.0"

#: Seeded RNG so a regenerated fixture is byte-identical.
RNG_SEED = 20261018


@dataclass
class Label:
    """A known, synthetic manipulation point. Exact by construction."""

    kind: str
    start_sample: int
    end_sample: int
    note: str = ""

    @property
    def start_ms(self) -> int:
        return int(round(self.start_sample * 1000.0 / SAMPLE_RATE))

    @property
    def end_ms(self) -> int:
        return int(round(self.end_sample * 1000.0 / SAMPLE_RATE))

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class FixtureRecipe:
    """Fully reproducible description of one synthetic fixture."""

    fixture_id: str
    kind: str  # "analytic" | "spoken"
    description: str
    language_id: str
    language_code: str
    segments: list[dict] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    expected_script: str = ""
    label_provenance: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "fixtureId": self.fixture_id,
            "kind": self.kind,
            "description": self.description,
            "languageId": self.language_id,
            "languageCode": self.language_code,
            "segments": list(self.segments),
            "labels": [
                {
                    "kind": label.kind,
                    "startSample": label.start_sample,
                    "endSample": label.end_sample,
                    "startMs": label.start_ms,
                    "endMs": label.end_ms,
                    "durationMs": label.duration_ms,
                    "note": label.note,
                }
                for label in self.labels
            ],
            "expectedScript": self.expected_script,
            "labelProvenance": self.label_provenance,
        }


# ---------------------------------------------------------------------------
# deterministic signal builders
# ---------------------------------------------------------------------------


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(round(seconds * SAMPLE_RATE)), dtype=np.int16)


def seeded_noise(seconds: float, amplitude: int = 900, seed: int = RNG_SEED) -> np.ndarray:
    """Deterministic pseudo-noise. Not a recording of anything."""
    rng = np.random.default_rng(seed)
    n = int(round(seconds * SAMPLE_RATE))
    samples = rng.normal(0.0, amplitude, n)
    return np.clip(np.round(samples), -32768, 32767).astype(np.int16)


def voiced_placeholder(
    seconds: float,
    *,
    f0: float = 120.0,
    seed: int = RNG_SEED,
) -> np.ndarray:
    """A speech-*shaped* analytic placeholder: harmonic stack + jitter.

    This is deliberately labelled as a placeholder in the manifest. It is
    not speech, not a phoneme, and VAD boundary behaviour on it says
    nothing about VAD behaviour on a learner.
    """
    n = int(round(seconds * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    rng = np.random.default_rng(seed)
    jitter = 1.0 + 0.01 * np.sin(2 * np.pi * 4.5 * t)
    wave = np.zeros(n)
    for harmonic, gain in enumerate([1.0, 0.55, 0.32, 0.18, 0.09], start=1):
        wave += gain * np.sin(2 * np.pi * f0 * harmonic * jitter * t)
    wave *= 0.28
    wave += 0.02 * rng.normal(0.0, 1.0, n)
    envelope = np.minimum(1.0, np.minimum(t / 0.04, (seconds - t) / 0.04))
    wave *= np.clip(envelope, 0.0, 1.0)
    return np.clip(np.round(wave * 32767), -32768, 32767).astype(np.int16)


def _concat(parts: list[tuple[np.ndarray, str]]) -> tuple[np.ndarray, list[dict], list[Label]]:
    """Concatenate ``(samples, tag)`` parts, tracking exact sample indices."""
    chunks: list[np.ndarray] = []
    segments: list[dict] = []
    labels: list[Label] = []
    cursor = 0
    for samples, tag in parts:
        n = len(samples)
        start, end = cursor, cursor + n
        segments.append(
            {
                "tag": tag,
                "start_sample": start,
                "end_sample": end,
                "start_ms": int(round(start * 1000.0 / SAMPLE_RATE)),
                "end_ms": int(round(end * 1000.0 / SAMPLE_RATE)),
                "duration_ms": int(round(n * 1000.0 / SAMPLE_RATE)),
            }
        )
        if tag == "silence":
            labels.append(
                Label(
                    kind="silence",
                    start_sample=start,
                    end_sample=end,
                    note="exact by construction",
                )
            )
        chunks.append(np.asarray(samples, dtype=np.int16))
        cursor = end
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16), segments, labels


# ---------------------------------------------------------------------------
# recipes
# ---------------------------------------------------------------------------


def analytic_recipes() -> list[FixtureRecipe]:
    """The offline analytic set. No speech provider, no model download.

    Covers every case BUILD.md requires at the *mechanics* level: silence,
    synthetic noise, a clear utterance-shaped segment, a one-word-length
    segment, a known internal gap, repetition, filled hesitation as a
    marked pause, lexical vs filler "like" as two distinguishable tonal
    patterns, and a code-mixed pattern.

    Where a case needs a genuine *spoken* fixture for its label to mean
    anything, the recipe says so in ``label_provenance``.
    """
    out: list[FixtureRecipe] = []
    analytic_labels = {
        "origin": "synthetic-analytic",
        "generator": f"{GENERATOR_NAME}@{GENERATOR_VERSION}",
        "seed": RNG_SEED,
        "verified_by": None,
        "review_state": "unreviewed-synthetic",
        "note": (
            "Generated signal, not speech. Segment indices and silence "
            "boundaries are exact; no claim is made about natural speech "
            "onsets or about any recogniser."
        ),
    }
    spoken_labels = {
        "origin": "synthetic-spoken-pending",
        "generator": None,
        "seed": None,
        "verified_by": None,
        "review_state": "AWAITING-PREPARED-SPEECH-SOURCE",
        "note": (
            "Needs an explicitly prepared speech source. No script is "
            "rendered here: a TTS input script is not proof the rendered "
            "audio contains a hesitation. Filler labels stay UNVERIFIED "
            "until a named reviewer listens and confirms."
        ),
    }

    # 1. pure silence
    samples, segments, labels = _concat([(silence(3.0), "silence")])
    out.append(
        FixtureRecipe(
            fixture_id="silence-3s",
            kind="analytic",
            description="3 s of digital silence; must yield zero speech regions.",
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            label_provenance=dict(analytic_labels),
        )
    )

    # 2. synthetic noise
    samples, segments, labels = _concat(
        [(silence(0.4), "silence"), (seeded_noise(2.2, amplitude=1400), "noise"),
         (silence(0.4), "silence")]
    )
    out.append(
        FixtureRecipe(
            fixture_id="noise-2s",
            kind="analytic",
            description="Seeded pseudo-noise between silences; must not be scored as fluent speech.",
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            label_provenance=dict(analytic_labels),
        )
    )

    # 3. clear single utterance (no internal gap)
    samples, segments, labels = _concat(
        [(silence(0.5), "silence"), (voiced_placeholder(2.0), "speech"),
         (silence(0.5), "silence")]
    )
    out.append(
        FixtureRecipe(
            fixture_id="clear-utterance",
            kind="analytic",
            description="One contiguous speech-shaped segment inside leading/trailing silence.",
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            expected_script="(placeholder signal; no words)",
            label_provenance=dict(analytic_labels),
        )
    )

    # 4. one-word-length speech
    samples, segments, labels = _concat(
        [(silence(0.4), "silence"), (voiced_placeholder(0.25), "speech"),
         (silence(0.6), "silence")]
    )
    out.append(
        FixtureRecipe(
            fixture_id="one-word",
            kind="analytic",
            description="Single short utterance; probes x-min-segment-ms short-answer behaviour.",
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            expected_script="(placeholder signal; no words)",
            label_provenance=dict(analytic_labels),
        )
    )

    # 5. known internal gap of 1200 ms inside one utterance
    samples, segments, labels = _concat(
        [
            (silence(0.5), "silence"),
            (voiced_placeholder(1.2), "speech"),
            (silence(1.2), "silence"),
            (voiced_placeholder(1.2), "speech"),
            (silence(0.5), "silence"),
        ]
    )
    out.append(
        FixtureRecipe(
            fixture_id="known-internal-gap",
            kind="analytic",
            description="1200 ms internal silence between two speech segments; the pause label is exact.",
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            label_provenance=dict(analytic_labels),
        )
    )

    # 6. repetition: same segment twice, distinguishable by seed
    samples, segments, labels = _concat(
        [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.9), "speech"),
            (silence(0.25), "silence"),
            (voiced_placeholder(0.9, seed=RNG_SEED + 1), "speech"),
            (silence(0.4), "silence"),
        ]
    )
    out.append(
        FixtureRecipe(
            fixture_id="repetition",
            kind="analytic",
            description="Two near-identical speech segments; probes duplicate detection and index order.",
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            label_provenance=dict(analytic_labels),
        )
    )

    # 7. filled hesitation: short low-energy vocal burst inside an utterance
    samples, segments, labels = _concat(
        [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.8), "speech"),
            (voiced_placeholder(0.18, f0=95.0, seed=RNG_SEED + 2), "filled_hesitation"),
            (voiced_placeholder(0.9), "speech"),
            (silence(0.4), "silence"),
        ]
    )
    out.append(
        FixtureRecipe(
            fixture_id="filled-hesitation",
            kind="analytic",
            description=(
                "Short low-energy burst between two speech segments. The BURST is exact; "
                "whether a listener would call it a filled pause is UNVERIFIED."
            ),
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            label_provenance={
                **analytic_labels,
                "review_state": "UNVERIFIED-FILLER-LABEL",
                "note": (
                    "The inserted burst has exact sample indices. That is not the same as a "
                    "confirmed filled pause: no listener has judged it. This fixture may be "
                    "used for boundary-preservation mechanics, never as filler ground truth."
                ),
            },
        )
    )

    # 8. lexical "like" vs filler "like" — two distinguishable patterns.
    #    Deliberately NOT labelled as filler/non-filler: that judgement is
    #    linguistic and requires a reviewer.
    samples, segments, labels = _concat(
        [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.7), "speech"),
            (voiced_placeholder(0.28, f0=205.0, seed=RNG_SEED + 3), "like_a_lexical"),
            (silence(0.2), "silence"),
            (voiced_placeholder(0.7), "speech"),
            (voiced_placeholder(0.28, f0=118.0, seed=RNG_SEED + 4), "like_b_disputed"),
            (silence(0.4), "silence"),
        ]
    )
    out.append(
        FixtureRecipe(
            fixture_id="lexical-like-vs-filler-like",
            kind="analytic",
            description=(
                "Two acoustically distinct tokens in the same position. Which one a "
                "listener would call a lexical 'like' and which a filler is UNVERIFIED; "
                "this fixture exists to keep both classes in the evaluation set."
            ),
            language_id="english",
            language_code="en-IN",
            segments=segments,
            labels=labels,
            label_provenance={
                **analytic_labels,
                "review_state": "UNVERIFIED-FILLER-LABEL",
                "classes_present": ["lexical-like", "disputed-filler-like"],
                "note": (
                    "A forced aligner would map whichever token is in the supplied text. "
                    "It cannot decide which token was a filler. Do not score this fixture "
                    "with filler precision/recall until a reviewer labels it."
                ),
            },
        )
    )

    # 9. code-mixed example (English structure with an Indic-script slot)
    samples, segments, labels = _concat(
        [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.8, seed=RNG_SEED + 5), "english_part"),
            (voiced_placeholder(0.55, f0=132.0, seed=RNG_SEED + 6), "indic_part"),
            (voiced_placeholder(0.7, seed=RNG_SEED + 7), "english_part_2"),
            (silence(0.4), "silence"),
        ]
    )
    out.append(
        FixtureRecipe(
            fixture_id="code-mixed-en-in",
            kind="analytic",
            description="Two-pitch code-mix pattern; exercises segment continuity across a language switch.",
            language_id="hinglish",
            language_code="hi-en",
            segments=segments,
            labels=labels,
            label_provenance={
                **analytic_labels,
                "note": (
                    "STT takes en-IN for Hindi-English mixed input; hi-en is a TTS-only "
                    "code and must never be sent to STT."
                ),
            },
        )
    )

    return out


SPOKEN_FIXTURE_IDS = (
    "spoken-clear-sentence",
    "spoken-known-gap",
    "spoken-one-word",
    "spoken-filled-hesitation",
    "spoken-lexical-like-vs-filler-like",
    "spoken-code-mixed",
)


def spoken_placeholders() -> list[FixtureRecipe]:
    """Recipes for fixtures that need a real prepared speech source.

    No audio is produced. Each entry records why it is absent and what the
    smallest user action would be to produce it.
    """
    out: list[FixtureRecipe] = []
    notes = {
        "spoken-clear-sentence": (
            "One clear sentence, no internal pause, to establish a recognition baseline.",
            "A short, consent-free sentence recorded by the user or rendered by a locally "
            "installed TTS engine, at 16 kHz mono.",
        ),
        "spoken-known-gap": (
            "One sentence with a deliberate 1.2 s mid-sentence pause.",
            "The user reads one sentence, pausing mid-sentence for about 1.2 s.",
        ),
        "spoken-one-word": ("A single-word answer.", "The user says one word, e.g. 'yes'."),
        "spoken-filled-hesitation": (
            "A sentence containing at least two genuine filled pauses ('um', 'uh').",
            "The user reads a sentence aloud, inserting 'um' or 'uh' at two points. The "
            "user is the reviewer, since only they can confirm the hesitation was audible.",
        ),
        "spoken-lexical-like-vs-filler-like": (
            "One sentence with a lexical 'like' and one with a filler 'like'.",
            "The user reads two sentences and marks which 'like' was filler usage.",
        ),
        "spoken-code-mixed": (
            "One Hindi-English mixed sentence.",
            "The user reads a code-mixed sentence naturally.",
        ),
    }
    for fixture_id, (description, action) in notes.items():
        out.append(
            FixtureRecipe(
                fixture_id=fixture_id,
                kind="spoken",
                description=description,
                language_id="english",
                language_code="en-IN",
                segments=[],
                labels=[],
                label_provenance={
                    "origin": "synthetic-spoken-pending",
                    "generator": None,
                    "verified_by": None,
                    "review_state": "MISSING-REQUIRED-SPEECH-SOURCE",
                    "smallest_user_action": action,
                    "note": (
                        "Real spoken fixtures are required before any filler or "
                        "boundary claim can be made. Synthetic analytic fixtures "
                        "cannot substitute for them."
                    ),
                },
            )
        )
    return out


# ---------------------------------------------------------------------------
# materialisation
# ---------------------------------------------------------------------------


def build_analytic(recipe: FixtureRecipe, out_dir: Path) -> dict:
    """Render one analytic recipe and write its ignored WAV + entry."""
    parts: list[tuple[np.ndarray, str]] = []
    if recipe.fixture_id == "silence-3s":
        parts = [(silence(3.0), "silence")]
    elif recipe.fixture_id == "noise-2s":
        parts = [
            (silence(0.4), "silence"),
            (seeded_noise(2.2, amplitude=1400), "noise"),
            (silence(0.4), "silence"),
        ]
    elif recipe.fixture_id == "clear-utterance":
        parts = [
            (silence(0.5), "silence"),
            (voiced_placeholder(2.0), "speech"),
            (silence(0.5), "silence"),
        ]
    elif recipe.fixture_id == "one-word":
        parts = [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.25), "speech"),
            (silence(0.6), "silence"),
        ]
    elif recipe.fixture_id == "known-internal-gap":
        parts = [
            (silence(0.5), "silence"),
            (voiced_placeholder(1.2), "speech"),
            (silence(1.2), "silence"),
            (voiced_placeholder(1.2), "speech"),
            (silence(0.5), "silence"),
        ]
    elif recipe.fixture_id == "repetition":
        parts = [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.9), "speech"),
            (silence(0.25), "silence"),
            (voiced_placeholder(0.9, seed=RNG_SEED + 1), "speech"),
            (silence(0.4), "silence"),
        ]
    elif recipe.fixture_id == "filled-hesitation":
        parts = [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.8), "speech"),
            (voiced_placeholder(0.18, f0=95.0, seed=RNG_SEED + 2), "filled_hesitation"),
            (voiced_placeholder(0.9), "speech"),
            (silence(0.4), "silence"),
        ]
    elif recipe.fixture_id == "lexical-like-vs-filler-like":
        parts = [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.7), "speech"),
            (voiced_placeholder(0.28, f0=205.0, seed=RNG_SEED + 3), "like_a_lexical"),
            (silence(0.2), "silence"),
            (voiced_placeholder(0.7), "speech"),
            (voiced_placeholder(0.28, f0=118.0, seed=RNG_SEED + 4), "like_b_disputed"),
            (silence(0.4), "silence"),
        ]
    elif recipe.fixture_id == "code-mixed-en-in":
        parts = [
            (silence(0.4), "silence"),
            (voiced_placeholder(0.8, seed=RNG_SEED + 5), "english_part"),
            (voiced_placeholder(0.55, f0=132.0, seed=RNG_SEED + 6), "indic_part"),
            (voiced_placeholder(0.7, seed=RNG_SEED + 7), "english_part_2"),
            (silence(0.4), "silence"),
        ]
    else:
        raise ValueError(f"no analytic recipe for {recipe.fixture_id!r}")

    samples, segments, labels = _concat(parts)
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    wav_bytes = encode_wav(samples, SAMPLE_RATE)
    audio_path = audio_dir / f"{recipe.fixture_id}.wav"
    audio_path.write_bytes(wav_bytes)

    entry = {
        "fixtureId": recipe.fixture_id,
        "kind": recipe.kind,
        "syntheticOrigin": "generated-no-real-audio",
        "description": recipe.description,
        "languageId": recipe.language_id,
        "languageCode": recipe.language_code,
        "audio": {
            "path": f"audio/{recipe.fixture_id}.wav",
            "container": "wav",
            "encoding": "pcm_s16le",
            "sampleRate": SAMPLE_RATE,
            "channels": CHANNELS,
            "sampleWidth": SAMPLE_WIDTH,
            "sampleCount": int(len(samples)),
            "durationMs": int(round(len(samples) * 1000.0 / SAMPLE_RATE)),
            "sha256": hashlib.sha256(wav_bytes).hexdigest(),
            "bytes": len(wav_bytes),
            "gitIgnored": True,
        },
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
            "seed": RNG_SEED,
            "deterministic": True,
        },
        "segments": segments,
        "labels": [
            {
                "kind": label.kind,
                "startSample": label.start_sample,
                "endSample": label.end_sample,
                "startMs": label.start_ms,
                "endMs": label.end_ms,
                "durationMs": label.duration_ms,
                "note": label.note,
                "boundaryExactness": "exact-by-construction",
            }
            for label in labels
        ],
        "expectedScript": recipe.expected_script,
        "labelProvenance": recipe.label_provenance,
    }
    return entry


def _existing_spoken_entries(root: Path) -> dict[str, dict]:
    """Spoken entries from a previous manifest that still verify on disk.

    ``fixtures --offline`` regenerates the analytic set, which is
    deterministic. It must **not** silently discard prepared spoken
    fixtures: doing so would destroy hours of provider work and make the
    documented offline command destructive. A spoken entry is preserved
    only when its audio file still exists and its sha256 still matches.
    """
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    preserved: dict[str, dict] = {}
    for entry in previous.get("fixtures", []):
        if entry.get("kind") != "spoken":
            continue
        audio = entry.get("audio")
        if not isinstance(audio, dict):
            continue
        candidate = (root / str(audio.get("path", ""))).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != audio.get("sha256"):
            continue
        preserved[entry["fixtureId"]] = entry
    return preserved


def build_manifest(out_dir: Path) -> dict:
    """Write ``manifest.json`` + recipes. Audio stays ignored."""
    recipes_dir = out_dir / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    preserved = _existing_spoken_entries(out_dir)

    entries: list[dict] = []
    for recipe in analytic_recipes():
        entries.append(build_analytic(recipe, out_dir))
    for recipe in spoken_placeholders():
        existing = preserved.get(recipe.fixture_id)
        if existing is not None:
            # Keep the verified audio entry and its provenance verbatim.
            entries.append(existing)
            continue
        entries.append(
            {
                "fixtureId": recipe.fixture_id,
                "kind": recipe.kind,
                "syntheticOrigin": "MISSING-REQUIRED-SPEECH-SOURCE",
                "description": recipe.description,
                "languageId": recipe.language_id,
                "languageCode": recipe.language_code,
                "audio": None,
                "generator": None,
                "segments": [],
                "labels": [],
                "expectedScript": "",
                "labelProvenance": recipe.label_provenance,
            }
        )

    manifest = {
        "manifestVersion": "0.1",
        "status": "DRAFT - Phase 02 feasibility, not an evaluation set",
        "generatedBy": f"{GENERATOR_NAME}@{GENERATOR_VERSION}",
        "audioPolicy": (
            "Generated audio is ignored by the repository's existing *.wav rule. "
            "The manifest and recipes are the committed artefacts. Root ignore rules "
            "were not amended and no audio was force-added."
        ),
        "honestyRules": [
            "Analytic fixtures are generated signals, not speech.",
            "Silence and gap labels are exact by construction; natural speech onset labels are not.",
            "A TTS input script is not proof the rendered audio contains a hesitation.",
            "Filler labels require a named human reviewer who listened; none are recorded yet.",
            "The candidate detector's own prediction is never treated as ground truth.",
        ],
        "fixtures": entries,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for recipe in analytic_recipes() + spoken_placeholders():
        (recipes_dir / f"{recipe.fixture_id}.json").write_text(
            json.dumps(recipe.to_json(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return manifest
