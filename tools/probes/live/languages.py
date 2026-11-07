"""Language resolution through the shared catalog.

Every language identifier used by a probe — a catalog id, a display name,
an STT code or a TTS code — is resolved **through
``packages/contracts/data/catalog.json``**, which this phase reads but
never edits. A selector that does not resolve is refused *before* any
request is issued, so an invalid combination can never spend credit.

Two things this module deliberately refuses to do
-------------------------------------------------
1. **Guess a language from a free-text string.** The previous revision
   mapped the literal display string ``"English"`` to ``"en-IN"`` and left
   every other display name unresolved. Any display name that is not in
   the catalog is now an explicit error, not a silent fallback.
2. **Substitute one language's evidence for another's.** Hinglish keeps
   its own STT code (``en-IN``) and its own TTS code (``hi-en``); the two
   are reported separately and neither is presented as the other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from gnani_coach.providers.errors import InvalidRequestError

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "packages" / "contracts" / "data" / "catalog.json"


@dataclass(frozen=True)
class CatalogLanguage:
    """One catalog entry, resolved. Never a guess."""

    id: str
    display_name: str
    native_name: str
    stt_code: str
    tts_code: str
    documented: bool
    notes: tuple[str, ...]
    kind: str = "language"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "displayName": self.display_name,
            "nativeName": self.native_name,
            "sttCode": self.stt_code,
            "ttsCode": self.tts_code,
            "documented": self.documented,
            "kind": self.kind,
        }


def load_catalog(path: Path | None = None) -> list[CatalogLanguage]:
    """Read the shared catalog. Read-only: no flag is ever flipped here."""
    catalog_path = path or CATALOG_PATH
    if not catalog_path.is_file():
        raise InvalidRequestError(
            f"shared catalog not found at {catalog_path}; it is owned by Phase 03 "
            "and this phase only reads it"
        )
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries: list[CatalogLanguage] = []
    for language in payload.get("languages", []):
        entries.append(
            CatalogLanguage(
                id=language["id"],
                display_name=language["displayName"],
                native_name=language.get("nativeName", ""),
                stt_code=language["sttCode"],
                tts_code=language["ttsCode"],
                documented=bool(language.get("capabilities", {}).get("documented")),
                notes=tuple(language.get("notes") or ()),
                kind="language",
            )
        )
    for mode in payload.get("codeMixedModes", []):
        entries.append(
            CatalogLanguage(
                id=mode["id"],
                display_name=mode["displayName"],
                native_name=mode.get("nativeName", ""),
                stt_code=mode["sttCode"],
                tts_code=mode["ttsCode"],
                documented=bool(mode.get("capabilities", {}).get("documented")),
                notes=tuple(mode.get("notes") or ()),
                kind="code_mixed_mode",
            )
        )
    return entries


def known_selectors(entries: list[CatalogLanguage]) -> dict[str, list[CatalogLanguage]]:
    """Every accepted selector string, mapped to the entries it may mean.

    A selector can be **ambiguous**: ``en-IN`` is the STT code of both
    English and Hinglish. Ambiguity is preserved here and refused at
    resolve time, rather than being silently settled by whichever entry
    happened to be listed last.
    """
    index: dict[str, list[CatalogLanguage]] = {}
    for entry in entries:
        for selector in (
            entry.id,
            entry.display_name,
            entry.native_name,
            entry.stt_code,
            entry.tts_code,
        ):
            if not selector:
                continue
            key = selector.strip().lower()
            bucket = index.setdefault(key, [])
            if entry not in bucket:
                bucket.append(entry)
    return index


def resolve(selector: str, entries: list[CatalogLanguage]) -> CatalogLanguage:
    """Resolve one selector to a catalog entry, or refuse.

    Accepts a catalog id, a display name, a native name, or an STT/TTS
    code. Everything is matched case-insensitively. A selector that does
    not resolve names the known selectors instead of guessing, and a
    selector that could mean more than one entry (``en-IN``) is refused
    as ambiguous instead of being settled silently.
    """
    if not isinstance(selector, str) or not selector.strip():
        raise InvalidRequestError("a language selector must be a non-empty string")
    index = known_selectors(entries)
    key = selector.strip().lower()
    matches = index.get(key)
    if not matches:
        raise InvalidRequestError(
            f"{selector!r} does not resolve to a catalog language; "
            f"known ids: {', '.join(sorted(e.id for e in entries))}"
        )
    if len(matches) > 1:
        raise InvalidRequestError(
            f"{selector!r} is ambiguous: it matches "
            f"{', '.join(sorted(entry.id for entry in matches))}. "
            "Use the language id or display name instead."
        )
    return matches[0]


def resolve_many(
    selectors: list[str] | None, entries: list[CatalogLanguage]
) -> list[CatalogLanguage]:
    """Resolve a selector list, preserving catalog order and dropping dupes."""
    if not selectors:
        return list(entries)
    chosen = {resolve(selector, entries).id for selector in selectors}
    return [entry for entry in entries if entry.id in chosen]


def reply_language_name(entry: CatalogLanguage) -> str:
    """The name to ask a reasoning model to *reply in*.

    The native name is the right thing to hand a model; the catalog id is
    not a language name and the display name is an English gloss that a
    non-English model may not resolve reliably.
    """
    return entry.native_name or entry.display_name
