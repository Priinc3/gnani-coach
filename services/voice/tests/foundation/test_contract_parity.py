"""Contract parity — Python ``jsonschema`` consumes the same files as Ajv.

Draft: every schema must declare JSON Schema draft 2020-12 and is validated
with ``Draft202012Validator``. Formats: a ``FormatChecker`` is attached, and
the ``format-nongpl`` extra is installed so ``date``, ``date-time`` and ``uri``
are genuinely checked. No remote fetching: only local ``$ref`` values are
allowed. Expectation comes from the folder name: ``valid/`` must pass,
``invalid/`` must fail. ``REQUIRED_FIXTURES`` mirrors
``packages/contracts/scripts/test-examples.mjs`` so neither runtime can
silently drop coverage.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

EXPECTED_LANGUAGE_IDS = [
    "bengali",
    "english",
    "gujarati",
    "hindi",
    "kannada",
    "malayalam",
    "marathi",
    "punjabi",
    "tamil",
    "telugu",
]

REQUIRED_FIXTURES: dict[str, dict[str, list[str]]] = {
    "catalog": {
        "valid": ["minimal-catalog.json"],
        "invalid": ["with-fr-stt-code.json", "with-fr-tts-code.json"],
    },
    "session-settings": {
        "valid": ["default-recording-off.json", "recording-on-with-consent.json"],
        "invalid": ["language-code-form-invalid.json", "recording-on-without-grant.json"],
    },
    "event-envelope": {
        "valid": ["text-event.json", "audio-frame-descriptor.json"],
        "invalid": [
            "mismatched-prefixed-turn-id.json",
            "base64-audio-in-text-payload.json",
            "space-separated-emitted-at.json",
            "negative-sequence.json",
        ],
    },
    "analysis-observation": {
        "valid": ["measured-zero-fillers.json", "unavailable-pause.json", "measured-fractional-rate.json"],
        "invalid": [
            "unavailable-with-zero-value.json",
            "available-with-null-value.json",
            "missing-unit-when-available.json",
            "confidence-as-metric.json",
            "negative-value.json",
            "fractional-count.json",
            "mismatched-unit.json",
        ],
    },
    "durable-metrics": {
        "valid": ["numeric-only.json", "controlled-provenance.json"],
        "invalid": [
            "with-transcript-field.json",
            "with-audio-url-field.json",
            "with-quoted-mistakes-field.json",
            "with-model-text-field.json",
            "with-embedding-field.json",
            "method-prose-transcript.json",
            "method-prose-model-feedback.json",
            "negative-count.json",
            "fractional-count.json",
            "mismatched-unit.json",
        ],
    },
    "recording-metadata": {
        "valid": ["retained.json", "deleted-with-deleted-at.json"],
        "invalid": ["public-url-field.json", "deleted-without-deleted-at.json"],
    },
    "error-shape": {
        "valid": ["provider-unavailable-retryable.json", "invalid-request-not-retryable.json"],
        "invalid": [
            "with-stack-field.json",
            "with-raw-transcript-field.json",
            "unknown-category.json",
            "retryable-invalid-request.json",
        ],
    },
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_remote_refs(node: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_find_remote_refs(item, f"{path}[{index}]"))
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and not value.startswith("#"):
                found.append(f"{path}.$ref = {value}")
            found.extend(_find_remote_refs(value, f"{path}.{key}"))
    return found


def _validator(contracts_dir: Path, stem: str) -> Draft202012Validator:
    schema = _load(contracts_dir / "schemas" / f"{stem}.schema.json")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_schema_inventory_is_draft_2020_12_with_local_refs_only(contracts_dir: Path) -> None:
    schema_paths = sorted((contracts_dir / "schemas").glob("*.schema.json"))
    assert schema_paths, "no schemas found"
    for schema_path in schema_paths:
        schema = _load(schema_path)
        assert schema["$schema"] == DRAFT_2020_12, schema_path.name
        assert schema["$id"].endswith("/0.1.0"), schema_path.name
        assert _find_remote_refs(schema) == [], schema_path.name


def test_examples_match_folder_expectation(contracts_dir: Path) -> None:
    examples_dir = contracts_dir / "examples"
    stems = sorted(
        path.name.removesuffix(".schema.json")
        for path in (contracts_dir / "schemas").glob("*.schema.json")
    )
    problems: list[str] = []
    for stem in stems:
        validator = _validator(contracts_dir, stem)
        for folder in ("valid", "invalid"):
            files = sorted((examples_dir / stem / folder).glob("*.json"))
            assert files, f"no fixtures in examples/{stem}/{folder}"
            for file_path in files:
                errors = list(validator.iter_errors(_load(file_path)))
                if folder == "valid" and errors:
                    problems.append(f"examples/{stem}/valid/{file_path.name}: {errors[0].message}")
                if folder == "invalid" and not errors:
                    problems.append(f"examples/{stem}/invalid/{file_path.name}: expected rejection")
    assert problems == [], problems


def test_required_fixtures_exist(contracts_dir: Path) -> None:
    missing: list[str] = []
    for stem, folders in REQUIRED_FIXTURES.items():
        for folder, names in folders.items():
            for name in names:
                if not (contracts_dir / "examples" / stem / folder / name).is_file():
                    missing.append(f"examples/{stem}/{folder}/{name}")
    assert missing == [], missing


def test_formats_are_actually_checked(contracts_dir: Path) -> None:
    """A format-violating fixture must be rejected — proving FormatChecker is active.

    Without the checker the same document would validate structurally, so the
    pair of assertions distinguishes a genuine format check from a silent skip.
    """
    validator = _validator(contracts_dir, "event-envelope")
    document = _load(
        contracts_dir / "examples" / "event-envelope" / "invalid" / "space-separated-emitted-at.json"
    )
    assert list(validator.iter_errors(document)) != []
    structural_only = Draft202012Validator(
        _load(contracts_dir / "schemas" / "event-envelope.schema.json")
    )
    assert list(structural_only.iter_errors(document)) == []


def test_catalog_matches_draft_invariants(contracts_dir: Path) -> None:
    catalog = _load(contracts_dir / "data" / "catalog.json")
    _validator(contracts_dir, "catalog").validate(catalog)
    ids = sorted(language["id"] for language in catalog["languages"])
    assert ids == EXPECTED_LANGUAGE_IDS
    assert "french" not in ids
    raw = (contracts_dir / "data" / "catalog.json").read_text(encoding="utf-8")
    assert "fr-FR" not in raw
    for entry in [*catalog["languages"], *catalog["codeMixedModes"]]:
        flags = entry["capabilities"]
        assert flags["documented"] is True
        for flag in ("accountEnabled", "conversationTested", "assessmentValidated"):
            assert flags[flag] is False
    hinglish = next(mode for mode in catalog["codeMixedModes"] if mode["id"] == "hinglish")
    assert hinglish["sttCode"] == "en-IN"
    assert hinglish["ttsCode"] == "hi-en"
