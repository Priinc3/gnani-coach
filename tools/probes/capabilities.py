"""Build the machine-readable capability matrix from real probe evidence.

Reads only artifacts this phase produced — the live matrix results, the
chain result and the aggregate run index — and emits
``docs/feasibility/capabilities.json``.

Honesty rules encoded here
--------------------------
* Language ids are read from ``packages/contracts/data/catalog.json``; the
  catalog is never re-authored here and no shared capability flag is flipped.
* Every column is tracked **independently**. A successful STT call never
  implies a working TTS voice, a correct reply language, intelligible
  coaching, or any assessment capability.
* A cell that was never exercised is ``NOT RUN`` — never inferred from a
  neighbouring language.
* ``documented`` comes from the catalog and is explicitly labelled as
  documentation evidence, not as account access or a measured result.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "prompts" / "phase-02-provider-feasibility" / "evidence"
CATALOG = REPO_ROOT / "packages" / "contracts" / "data" / "catalog.json"
RUN_INDEX = REPO_ROOT / "tools" / "probes" / ".cache" / "runs.jsonl"

NOT_RUN = "NOT RUN"

#: What a live API roundtrip does and does not establish. Repeated verbatim
#: in the Markdown matrix so the caveat travels with the data.
NOT_PROVEN_BY_API_ACCESS = [
    "human intelligibility of the synthesised speech",
    "coaching or teaching quality in this language",
    "recognition accuracy on natural learner speech",
    "filler preservation",
    "any pronunciation or confidence measure",
]

#: Caveats that must travel with the data (Phase 02 FIX-1, P02-04/P02-06).
CAVEATS = [
    (
        "The observedStt column of these historical runs records PARAMETER "
        "ACCEPTANCE, not language coverage. Only the English fixture "
        "(spoken-clear-sentence, en-IN) existed when these runs were made, "
        "so every other row's STT cell shows that the endpoint accepted "
        "that language's code. It does not establish that-language "
        "recognition."
    ),
    (
        "These historical rows were aggregated from the STT cell alone. The "
        "repaired matrix aggregates every requested stage (STT, TTS, "
        "reasoning); a row is covered only when all of them pass. The "
        "repaired matrix has not been re-run: no replacement credentials "
        "are confirmed and no native per-language fixtures exist yet."
    ),
    (
        "Wire-attempt counts for these historical runs are UNKNOWN. Attempt "
        "accounting was introduced in Phase 02 FIX-1; the earlier runs "
        "carry no measured attempt count and are never reconstructed as "
        "zero."
    ),
    (
        "The filler state is 'fillers absent from recognition'. Whether the "
        "fillers were present in the rendered audio was NOT reviewed, so "
        "this is neither a measured zero-filler result nor a finding of "
        "permanent recogniser incapability."
    ),
]


def _matrix_rows() -> dict[str, dict]:
    """Merge every matrix evidence file; later files win per cell."""
    merged: dict[str, dict] = {}
    for path in sorted(EVIDENCE_DIR.glob("live-matrix-result*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("rows", []):
            merged.setdefault(row["id"], {}).update(
                {k: v for k, v in row.items() if k != "note"}
            )
    return merged


def build() -> dict:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    observed = _matrix_rows()
    chain_path = EVIDENCE_DIR / "live-chain-result.json"
    chain = (
        json.loads(chain_path.read_text(encoding="utf-8"))
        if chain_path.is_file()
        else None
    )

    entries: list[dict] = []

    def entry(
        *,
        entry_id: str,
        display_name: str,
        native_name: str | None,
        stt_code: str,
        tts_code: str,
        documented: bool,
        row: dict,
        source_refs: list[str],
        notes: list[str],
    ) -> dict:
        return {
            "id": entry_id,
            "displayName": display_name,
            "nativeName": native_name,
            "sttCode": stt_code,
            "ttsCode": tts_code,
            "documentedSupport": documented,
            "observedStt": row.get("stt", NOT_RUN),
            "observedTts": row.get("tts", NOT_RUN),
            "observedTtsModel": "timbre-v2.5" if row.get("tts") == "PASSED" else NOT_RUN,
            "observedTtsVoice": row.get("voice", NOT_RUN),
            "observedTtsBytes": row.get("ttsBytes"),
            "observedGeminiReplyLanguage": row.get("geminiLanguage", NOT_RUN),
            "observedGeminiModel": row.get("geminiModel", NOT_RUN),
            "verifiedCoachingQuality": NOT_RUN,
            "fillerPreservation": NOT_RUN,
            "audioLocalization": NOT_RUN,
            "limitations": [
                f"STT: {row.get('note', '')}" if row.get("note") else "",
                *notes,
                "No intelligibility or coaching-quality review was performed.",
            ],
            "sourceRefs": source_refs,
        }

    for language in catalog["languages"]:
        entries.append(
            entry(
                entry_id=language["id"],
                display_name=language["displayName"],
                native_name=language.get("nativeName"),
                stt_code=language["sttCode"],
                tts_code=language["ttsCode"],
                documented=language["capabilities"]["documented"],
                row=observed.get(language["id"], {}),
                source_refs=language.get("sourceRefs", []),
                notes=language.get("notes", []),
            )
        )

    for mode in catalog.get("codeMixedModes", []):
        entries.append(
            entry(
                entry_id=mode["id"],
                display_name=mode["displayName"],
                native_name=None,
                stt_code=mode["sttCode"],
                tts_code=mode["ttsCode"],
                documented=mode["capabilities"]["documented"],
                row=observed.get(mode["id"], {}),
                source_refs=mode.get("sourceRefs", []),
                notes=mode.get("notes", []),
            )
        )

    runs: list[dict] = []
    if RUN_INDEX.is_file():
        for line in RUN_INDEX.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return {
        "matrixVersion": "0.1",
        "status": "DRAFT - Phase 02 feasibility observation, NOT a frozen catalog",
        "generatedFrom": [
            "prompts/phase-02-provider-feasibility/evidence/live-matrix-result*.json",
            "prompts/phase-02-provider-feasibility/evidence/live-chain-result.json",
            "tools/probes/.cache/runs.jsonl",
        ],
        "catalogSource": "packages/contracts/data/catalog.json (read, not modified)",
        "entryKinds": ["language", "code-mixed-mode"],
        "notProvenByApiAccess": NOT_PROVEN_BY_API_ACCESS,
        "caveats": CAVEATS,
        "historicalWireAttempts": "unknown",
        "columnsTrackedIndependently": [
            "documentedSupport",
            "observedStt",
            "observedTts",
            "observedTtsVoice",
            "observedGeminiReplyLanguage",
            "verifiedCoachingQuality",
            "fillerPreservation",
            "audioLocalization",
        ],
        "entries": entries,
        "chainedTurn": chain,
        "probeInvocations": [
            {
                "recordedAt": run.get("recordedAt"),
                "command": run.get("command"),
                "allowLive": run.get("allow_live"),
                "overall": run.get("overall"),
                "exitCode": run.get("exit_code"),
            }
            for run in runs
        ],
    }


def main() -> int:
    payload = build()
    out = REPO_ROOT / "docs" / "feasibility" / "capabilities.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stt_pass = sum(1 for e in payload["entries"] if e["observedStt"] == "PASSED")
    tts_pass = sum(1 for e in payload["entries"] if e["observedTts"] == "PASSED")
    gem_pass = sum(1 for e in payload["entries"] if e["observedGeminiReplyLanguage"] == "PASSED")
    total = len(payload["entries"])
    print(f"wrote {out.relative_to(REPO_ROOT)}: {total} entries")
    print(f"  stt={stt_pass}/{total} tts={tts_pass}/{total} gemini={gem_pass}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
