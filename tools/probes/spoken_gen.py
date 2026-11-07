"""Prepare real spoken fixtures from an explicitly prepared speech source.

Why this exists
---------------
The analytic fixtures are generated signals, not speech. A recogniser will
say nothing useful about them, and a feasibility verdict cannot rest on
them. Real spoken audio is required.

The speech source used here is **our own Gnani Timbre TTS endpoint**:
synthetic, non-personal, generated inside this repository's provider
account, and fully recorded in the manifest. No human is recorded, no
learner microphone is opened, and no external dataset is downloaded.

Honesty rules that this module cannot bypass
--------------------------------------------
* A **TTS input script is not proof** that the rendered audio contains a
  hesitation. Normalisation may drop "um" or "uh" entirely. Every fixture
  whose script contains a filler is written with
  ``filler_labels_verified: false`` and ``review_state:
  UNVERIFIED-FILLER-LABEL`` regardless of what the audio sounds like. The
  only thing that flips that flag is a named human reviewer.
* Timbre **v2.5 does not support audio tags** (v3.0 does), so a pause
  cannot be requested in text. A known-gap fixture is instead built from
  two separately synthesised halves with an exactly-known silent interval
  concatenated between them. That is a *synthetic manipulation* boundary:
  exact by construction, but not an exact natural speech onset label.
* Anything concatenated or resampled records its offset so a later
  measurement can be checked against it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from gnani_coach.providers.pcm import encode_wav, resample
from gnani_coach.providers.tts import (
    MODEL_V25,
    AudioConfig,
    GnaniTtsSession,
    TtsConfig,
)

TARGET_SAMPLE_RATE = 16000
SPEECH_SOURCE = "gnani-timbre-tts"


@dataclass(frozen=True)
class SpokenRecipe:
    fixture_id: str
    language_id: str
    language_code: str
    voice: str
    #: One entry per synthesised part. Parts are concatenated with an exact
    #: silence between them.
    parts: tuple[str, ...]
    #: Silence inserted after each part except the last, in milliseconds.
    gaps_ms: tuple[int, ...]
    description: str
    contains_fillers_in_script: bool = False
    notes: tuple[str, ...] = ()


#: All text is synthetic, generic and non-personal. No names, no accounts,
#: no contact details, no recorded material.
RECIPES: tuple[SpokenRecipe, ...] = (
    SpokenRecipe(
        fixture_id="spoken-clear-sentence",
        language_id="english",
        language_code="en-IN",
        voice="Kaveri",
        parts=("I have been working on this project for about two years.",),
        gaps_ms=(),
        description="One clear sentence with no internal pause.",
    ),
    SpokenRecipe(
        fixture_id="spoken-known-gap",
        language_id="english",
        language_code="en-IN",
        voice="Kaveri",
        parts=(
            "I think the main issue is",
            "we did not test it properly.",
        ),
        gaps_ms=(1200,),
        description=(
            "Two halves separated by an exactly-known 1200 ms silence. The gap "
            "is exact by construction; it is NOT a natural speech onset label."
        ),
        notes=(
            "Timbre v2.5 has no audio tags, so the pause is a concatenation "
            "boundary, not a rendered hesitation.",
        ),
    ),
    SpokenRecipe(
        fixture_id="spoken-one-word",
        language_id="english",
        language_code="en-IN",
        voice="Kaveri",
        parts=("Yes.",),
        gaps_ms=(),
        description="A single-word answer; probes short-answer VAD behaviour.",
    ),
    SpokenRecipe(
        fixture_id="spoken-filled-hesitation",
        language_id="english",
        language_code="en-IN",
        voice="Kaveri",
        parts=(
            "So um I think the timeline is, uh, probably next month.",
        ),
        gaps_ms=(),
        description=(
            "A sentence whose script contains two filled pauses. Whether they "
            "survive synthesis is UNKNOWN until someone listens."
        ),
        contains_fillers_in_script=True,
        notes=(
            "The script contains 'um' and 'uh'. Text normalisation may remove "
            "them. This fixture is NOT filler ground truth until a named "
            "reviewer confirms the sounds are audible.",
        ),
    ),
    SpokenRecipe(
        fixture_id="spoken-lexical-like-vs-filler-like",
        language_id="english",
        language_code="en-IN",
        voice="Kaveri",
        parts=(
            "It is like a small library, with shelves everywhere.",
            "It is like, I am not sure, a small library.",
        ),
        gaps_ms=(400,),
        description=(
            "Two sentences differing only in how 'like' is used: one lexical, "
            "one arguably a filler. The judgement is linguistic and is "
            "UNVERIFIED."
        ),
        contains_fillers_in_script=True,
        notes=(
            "A forced aligner can time whichever 'like' is in the text; it "
            "cannot decide which usage was intended.",
        ),
    ),
    SpokenRecipe(
        fixture_id="spoken-code-mixed",
        language_id="hinglish",
        language_code="hi-en",
        voice="Poorvi",
        parts=("Main office se aap late kyun aaye, sir?",),
        gaps_ms=(),
        description="One Hindi-English code-mixed sentence rendered by the Hinglish voice.",
        notes=(
            "STT takes en-IN for Hindi-English mixed input. The TTS code hi-en "
            "must never be sent to STT.",
        ),
    ),
)


@dataclass
class SynthesisOutcome:
    fixture_id: str
    ok: bool
    samples: np.ndarray | None = None
    detail: dict = field(default_factory=dict)


async def _synthesize(
    recipe: SpokenRecipe, text: str, api_key: str, budget
) -> tuple[np.ndarray | None, dict]:
    config = TtsConfig(
        text=text,
        voice=recipe.voice,
        model=MODEL_V25,
        language=recipe.language_code,
        audio=AudioConfig(sample_rate=TARGET_SAMPLE_RATE, container="raw"),
    )
    session = GnaniTtsSession(config, api_key, budget=budget)
    try:
        async with session:
            result = await session.synthesize()
    except Exception as exc:  # noqa: BLE001 - categorised upstream
        return None, {"error": f"{type(exc).__name__}: {getattr(exc, 'category', 'unknown')}"}
    if result.total_bytes <= 0:
        return None, {"error": "no audio returned"}
    samples = np.frombuffer(result.audio, dtype="<i2")
    converted = resample(samples, config.audio.sample_rate, TARGET_SAMPLE_RATE)
    return converted.samples, {
        "bytes": int(result.total_bytes),
        "first_nonempty_chunk_ms_backend": result.first_nonempty_chunk_ms,
        "chunk_count": len(result.chunks),
        "container_observation": result.container_observation,
        "resample_method": converted.method,
        "resample_source_offset_samples": converted.source_offset_samples,
    }


async def build_spoken_fixtures(
    api_key: str,
    root: Path,
    *,
    budget,
    only: tuple[str, ...] | None = None,
) -> list[SynthesisOutcome]:
    """Render the spoken fixture set with Timbre v2.5."""
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    outcomes: list[SynthesisOutcome] = []

    for recipe in RECIPES:
        if only and recipe.fixture_id not in only:
            continue
        pieces: list[np.ndarray] = []
        details: list[dict] = []
        gaps: list[dict] = []
        cursor = 0
        failed = False

        for index, text in enumerate(recipe.parts):
            samples, detail = await _synthesize(recipe, text, api_key, budget)
            detail["part_index"] = index
            detail["text_chars"] = len(text)
            details.append(detail)
            if samples is None:
                failed = True
                break
            pieces.append(samples)
            cursor += len(samples)
            gap_ms = recipe.gaps_ms[index] if index < len(recipe.gaps_ms) else 0
            if gap_ms:
                gap_samples = int(round(gap_ms * TARGET_SAMPLE_RATE / 1000.0))
                pieces.append(np.zeros(gap_samples, dtype=np.int16))
                gaps.append(
                    {
                        "kind": "inserted_silence",
                        "startSample": cursor,
                        "endSample": cursor + gap_samples,
                        "startMs": int(round(cursor * 1000.0 / TARGET_SAMPLE_RATE)),
                        "durationMs": gap_ms,
                        "boundaryExactness": "exact-by-construction-synthetic",
                        "note": "concatenation boundary, not a natural speech onset",
                    }
                )
                cursor += gap_samples

        if failed or not pieces:
            outcomes.append(
                SynthesisOutcome(recipe.fixture_id, False, None, {"parts": details})
            )
            continue

        merged = np.concatenate(pieces).astype(np.int16)
        wav = encode_wav(merged, TARGET_SAMPLE_RATE)
        (audio_dir / f"{recipe.fixture_id}.wav").write_bytes(wav)

        segments = []
        start = 0
        for piece in pieces:
            if piece.any():  # only non-silent parts become "speech" segments
                end = start + len(piece)
                segments.append(
                    {
                        "tag": "speech",
                        "startSample": start,
                        "endSample": end,
                        "startMs": int(round(start * 1000.0 / TARGET_SAMPLE_RATE)),
                        "endMs": int(round(end * 1000.0 / TARGET_SAMPLE_RATE)),
                        "durationMs": int(round(len(piece) * 1000.0 / TARGET_SAMPLE_RATE)),
                    }
                )
            start += len(piece)

        outcomes.append(
            SynthesisOutcome(
                recipe.fixture_id,
                True,
                merged,
                {
                    "parts": details,
                    "segments": segments,
                    "inserted_silences": gaps,
                    "sha256": hashlib.sha256(wav).hexdigest(),
                    "bytes": len(wav),
                    "durationMs": int(round(len(merged) * 1000.0 / TARGET_SAMPLE_RATE)),
                    "sampleRate": TARGET_SAMPLE_RATE,
                },
            )
        )
    return outcomes


def write_manifest_entries(
    manifest: dict,
    outcomes: list[SynthesisOutcome],
    recipes: tuple[SpokenRecipe, ...],
    root: Path | None = None,
) -> int:
    """Merge successful outcomes into the manifest and **persist it**.

    Mutating the dict is not enough: the CLI regenerates the manifest at the
    start of every run, so an un-persisted edit would be silently lost and
    the fixtures would read back as missing.
    """
    by_id = {r.fixture_id: r for r in recipes}
    updated = 0
    for outcome in outcomes:
        recipe = by_id[outcome.fixture_id]
        for entry in manifest["fixtures"]:
            if entry["fixtureId"] != outcome.fixture_id:
                continue
            if not outcome.ok:
                entry["labelProvenance"] = {
                    **entry.get("labelProvenance", {}),
                    "review_state": "SYNTHESIS-FAILED",
                    "smallest_user_action": entry.get("labelProvenance", {}).get(
                        "smallest_user_action", ""
                    ),
                }
                continue
            detail = outcome.detail
            entry["syntheticOrigin"] = f"{SPEECH_SOURCE}-synthetic-nonpersonal"
            entry["audio"] = {
                "path": f"audio/{outcome.fixture_id}.wav",
                "container": "wav",
                "encoding": "pcm_s16le",
                "sampleRate": TARGET_SAMPLE_RATE,
                "channels": 1,
                "sampleWidth": 2,
                "sampleCount": int(
                    len(outcome.samples) if outcome.samples is not None else 0
                ),
                "durationMs": detail["durationMs"],
                "sha256": detail["sha256"],
                "bytes": detail["bytes"],
                "gitIgnored": True,
            }
            entry["generator"] = {
                "name": SPEECH_SOURCE,
                "model": MODEL_V25,
                "voice": recipe.voice,
                "language": recipe.language_code,
                "synthesis_parts": [len(text) for text in recipe.parts],
                "inserted_gap_ms": list(recipe.gaps_ms),
                "notes": list(recipe.notes),
            }
            entry["segments"] = detail["segments"]
            entry["labels"] = detail["inserted_silences"]
            entry["expectedScript"] = " ".join(recipe.parts)
            entry["labelProvenance"] = {
                "origin": f"{SPEECH_SOURCE}-synthetic-nonpersonal",
                "verified_by": None,
                "filler_labels_verified": False,
                "review_state": (
                    "UNVERIFIED-FILLER-LABEL"
                    if recipe.contains_fillers_in_script
                    else "SCRIPT-AND-AUDIO-BOTH-KNOWN-NO-HUMAN-REVIEW"
                ),
                "note": (
                    "Synthetic speech rendered by the project's own TTS. A TTS "
                    "input script is NOT proof that a rendered hesitation is "
                    "audible. Filler labels stay unverified until a named human "
                    "reviewer listens."
                ),
                "speech_source_parts": detail["parts"],
            }
            updated += 1
    if root is not None:
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return updated


def summarise_budget(budget) -> dict:
    return budget.summary()
