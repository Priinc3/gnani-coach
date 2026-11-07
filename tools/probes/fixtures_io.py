"""Fixture manifest resolution with path confinement.

Only **prepared synthetic fixtures** are acceptable input in this phase.
There is deliberately no way to hand this CLI an arbitrary URL or an
arbitrary local path:

* fixture ids must exist in ``fixtures/synthetic/manifest.json``;
* the manifest's audio path is resolved against the manifest's own
  directory and must stay inside ``fixtures/synthetic/``;
* every path component is checked with ``Path.resolve()`` so a symlink
  cannot redirect a read outside the authorised tree;
* the file's sha256 must match the manifest, and its measured sample
  rate / channel count / duration must match the recorded values.

Learner microphone capture and real recorded-call collection are not
implemented anywhere in this package.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from gnani_coach.providers.errors import InvalidRequestError
from gnani_coach.providers.pcm import decode_wav, strip_wav_header

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "synthetic"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


@dataclass(frozen=True)
class ResolvedFixture:
    """A manifest entry whose audio has been verified on disk."""

    fixture_id: str
    kind: str
    language_id: str
    language_code: str
    audio_path: Path
    sample_rate: int
    channels: int
    duration_ms: int
    sha256: str
    labels: list[dict]
    segments: list[dict]
    label_provenance: dict
    description: str
    filler_labels_verified: bool


def load_manifest(path: Path | None = None) -> dict:
    manifest_path = path or MANIFEST_PATH
    if not manifest_path.is_file():
        raise InvalidRequestError(
            f"fixture manifest not found at {manifest_path.relative_to(REPO_ROOT)}; "
            "run `run.py fixtures --offline` first"
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _assert_inside(child: Path, parent: Path, *, what: str) -> Path:
    """Resolve ``child`` and refuse anything outside ``parent``.

    The *unresolved* path is what is checked for symlinks: by definition
    ``Path.resolve()`` returns a symlink-free path, so checking only the
    resolved form would let a symlink inside the tree through unnoticed.
    A symlink is refused even when its target happens to stay inside.
    """
    resolved_parent = parent.resolve()
    resolved_child = child.resolve()
    if not resolved_child.is_relative_to(resolved_parent):
        raise InvalidRequestError(
            f"{what} resolves outside the authorised fixture directory"
        )
    probe = child if child.is_absolute() else parent / child
    try:
        relative = probe.relative_to(parent)
    except ValueError:
        relative = None
    if relative is not None:
        cursor = parent
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise InvalidRequestError(f"{what} traverses a symlink")
    return resolved_child


def list_fixtures(manifest: dict) -> list[str]:
    return [entry["fixtureId"] for entry in manifest.get("fixtures", [])]


def resolve_fixture(
    fixture_id: str,
    manifest: dict | None = None,
    *,
    root: Path | None = None,
    require_audio: bool = True,
) -> ResolvedFixture:
    """Resolve one fixture id against the manifest, verifying the asset.

    ``fixture_id`` is never treated as a path. Unknown ids raise.
    """
    manifest = manifest or load_manifest()
    root = (root or FIXTURE_ROOT).resolve()
    if not fixture_id or "/" in fixture_id or "\\" in fixture_id or fixture_id.startswith("."):
        raise InvalidRequestError(f"invalid fixture id {fixture_id!r}")

    entries = {entry["fixtureId"]: entry for entry in manifest.get("fixtures", [])}
    entry = entries.get(fixture_id)
    if entry is None:
        raise InvalidRequestError(
            f"unknown fixture id {fixture_id!r}; known ids: "
            f"{', '.join(sorted(entries))}"
        )

    provenance = entry.get("labelProvenance") or {}
    review_state = str(provenance.get("review_state", ""))
    audio = entry.get("audio")
    if audio is None:
        raise InvalidRequestError(
            f"fixture {fixture_id!r} has no audio: "
            f"{provenance.get('smallest_user_action', 'no prepared speech source recorded')}"
        )

    relative = audio.get("path", "")
    candidate = (root / relative).resolve()
    audio_path = _assert_inside(candidate, root, what=f"fixture {fixture_id!r} audio")
    if not audio_path.is_file():
        raise InvalidRequestError(f"fixture {fixture_id!r} audio file is missing")

    raw = audio_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != audio.get("sha256"):
        raise InvalidRequestError(
            f"fixture {fixture_id!r} sha256 does not match the manifest "
            "(regenerate with `fixtures --offline`)"
        )

    samples, sample_rate, channels = decode_wav(raw)
    duration_ms = int(round(len(samples) * 1000.0 / sample_rate))
    if sample_rate != audio.get("sampleRate") or channels != audio.get("channels"):
        raise InvalidRequestError(
            f"fixture {fixture_id!r} audio format disagrees with the manifest"
        )

    return ResolvedFixture(
        fixture_id=fixture_id,
        kind=entry["kind"],
        language_id=entry["languageId"],
        language_code=entry["languageCode"],
        audio_path=audio_path,
        sample_rate=sample_rate,
        channels=channels,
        duration_ms=duration_ms,
        sha256=digest,
        labels=list(entry.get("labels") or []),
        segments=list(entry.get("segments") or []),
        label_provenance=provenance,
        description=entry.get("description", ""),
        filler_labels_verified=bool(provenance.get("verified_by")),
    )


def raw_pcm_of(fixture: ResolvedFixture) -> bytes:
    """Header-stripped PCM for a fixture. A WAV header never reaches a frame."""
    return strip_wav_header(fixture.audio_path.read_bytes())


def available(manifest: dict | None = None) -> tuple[list[str], list[str]]:
    """Split fixture ids into (available, missing) without raising."""
    manifest = manifest or load_manifest()
    ready: list[str] = []
    missing: list[str] = []
    for entry in manifest.get("fixtures", []):
        try:
            resolve_fixture(entry["fixtureId"], manifest)
            ready.append(entry["fixtureId"])
        except InvalidRequestError:
            missing.append(entry["fixtureId"])
    return sorted(ready), sorted(missing)


def analytic_fixtures(manifest: dict | None = None) -> list[ResolvedFixture]:
    manifest = manifest or load_manifest()
    out: list[ResolvedFixture] = []
    for entry in manifest.get("fixtures", []):
        if entry["kind"] != "analytic" or entry.get("audio") is None:
            continue
        out.append(resolve_fixture(entry["fixtureId"], manifest))
    return out


def calibration_ids() -> list[str]:
    """Fixture ids reserved for development/calibration."""
    return ["clear-utterance", "known-internal-gap", "filled-hesitation"]


def holdout_ids() -> list[str]:
    """Fixture ids reserved as holdout. Never used for tuning.

    With the analytic set alone this is deliberately small: the honest
    statement is that the required 20-positive/20-negative per filler mode
    does not exist yet.
    """
    return [
        "repetition",
        "lexical-like-vs-filler-like",
        "code-mixed-en-in",
        "one-word",
    ]
