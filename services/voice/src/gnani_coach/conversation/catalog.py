"""The frozen catalog, read at runtime.

``packages/contracts/data/catalog.json`` is the frozen catalog: the
language ids, their provider codes and the scenarios. The service reads
it to turn the practice language id of a ``start`` event into the
recogniser's language code and the synthesiser's language code.

The file is **read-only** and it is data, not configuration: the
environment never overrides it.

If the catalog cannot be found, the service says so honestly (the call
answers ``not_available``) rather than guessing a language code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: The relative path of the catalog inside the repository.
CATALOG_RELATIVE_PATH = Path("packages") / "contracts" / "data" / "catalog.json"

#: The TTS voice that the Phase 02 live chain used for each language.
#:
#: The pairing comes from the documented voice page (read 2026-10-18,
#: https://docs.gnani.ai/api/TTS/available-voices) and from the observed
#: Phase 02 runs in ``docs/feasibility/CAPABILITIES.md``. Each v2.5 voice
#: has one preferred language, so the pairing is not a free choice.
VOICE_BY_LANGUAGE: dict[str, str] = {
    "en-IN": "Devika",
    "hi-IN": "Ambuja",
    "bn-IN": "Dhruva",
    "gu-IN": "Falak",
    "kn-IN": "Kavin",
    "ml-IN": "Reshma",
    "mr-IN": "Ishaan",
    "pa-IN": "Mehuli",
    "ta-IN": "Asmita",
    "te-IN": "Lavanya",
    "hi-en": "Poorvi",
}


@dataclass(frozen=True)
class LanguageCodes:
    """The provider codes of one catalog language."""

    language_id: str
    display_name: str
    stt_code: str
    tts_code: str


def repository_root() -> Path | None:
    """The repository root, found by walking up from this module."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CATALOG_RELATIVE_PATH).is_file():
            return candidate
    return None


def catalog_path() -> Path | None:
    """Where the catalog lives, or ``None`` when it cannot be found."""
    root = repository_root()
    return root / CATALOG_RELATIVE_PATH if root is not None else None


@lru_cache(maxsize=1)
def _catalog() -> dict | None:
    path = catalog_path()
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def language(language_id: str) -> LanguageCodes | None:
    """The provider codes of one catalog language, or ``None``."""
    catalog = _catalog()
    if catalog is None:
        return None
    for entry in catalog.get("languages", []):
        if entry.get("id") == language_id:
            return LanguageCodes(
                language_id=entry["id"],
                display_name=entry.get("displayName", entry["id"]),
                stt_code=entry.get("sttCode", ""),
                tts_code=entry.get("ttsCode", ""),
            )
    for entry in catalog.get("codeMixedModes", []):
        if entry.get("id") == language_id:
            return LanguageCodes(
                language_id=entry["id"],
                display_name=entry.get("displayName", entry["id"]),
                stt_code=entry.get("sttCode", ""),
                tts_code=entry.get("ttsCode", ""),
            )
    return None


def language_names() -> dict[str, str]:
    """Every catalog language id and its display name."""
    catalog = _catalog()
    if catalog is None:
        return {}
    names: dict[str, str] = {}
    for key in ("languages", "codeMixedModes"):
        for entry in catalog.get(key, []):
            names[entry["id"]] = entry.get("displayName", entry["id"])
    return names


def voice_for(language_code: str, *, fallback: str) -> str:
    """The synthesis voice for a language code.

    The documented pairing wins; the configured voice is the fallback
    when the language is not one of the documented ones.
    """
    return VOICE_BY_LANGUAGE.get(language_code, fallback)
