# Phase 03 — contract-freeze (B1, NORMAL)

You are Phase 03. **Siblings running now: none.** Phase 04/05/06 (G1) are LOCKED until you finish and B1 passes. Comm folder: none.

Goal link: `prompts/00-plan.md` §2/§9. G1 builders will run in parallel against what you freeze. If you leave a seam vague, they will guess and collide. Build the smallest set that makes the seams exact. Skip anything G1 does not need.

## Read first
`prompts/00-plan.md` §9, `docs/feasibility/{HANDOFF,DECISION,CAPABILITIES}.md` (HANDOFF §5, §5.1a, §5.2–5.6 are your requirements list), `prompts/phase-04-call-ui/UI-REFERENCE.md` + root `UI.png`, `prompts/waivers.md`, `docs/architecture.md`, `packages/contracts/README.md`.

## OWN (write)
`packages/contracts/**` · `services/voice/src/gnani_coach/{main.py,settings.py,ports/**}` · `apps/web/src/app/{layout.tsx,page.tsx,globals.css}` · root and workspace manifests, locks, configs, scripts · `tests/integration/**` · `docs/contracts/**` · your own `REPORT.md` and `evidence/` folder under `prompts/phase-03-contract-freeze/`.
You may create **empty stubs** in Phase 04/05/06 directories (listed below) and hand them over in REPORT.

DO NOT TOUCH: `tools/probes/**`, `services/voice/src/gnani_coach/providers/**`, `fixtures/**`, `docs/feasibility/**`, `UI.png`, CEO files (plan, tracker, waivers, BUILD/FIX/VERIFY). No commit/push/deploy/delegation.

## Deliverables (only these)

### 1. Contract changes from Phase 02 (HANDOFF)
- §5.1 split `speech.rate_wpm` and `speech.active_rate_wpm` methods and denominators.
- §5.1a recognition status (`measured | no-analyzable-speech | missing-transcription`; rate **omitted**, not zero, for the last two). Add the source classification, with a description saying that a label is a declaration, not proof. Add the span-contents statement.
- §5.2 `turn.duration_ms` is sample-clock based. §5.3 `speakingTimeMs` is the sum of speech-active time, with invariant `≤ Σ durationMs`.
- §5.4: no word timing exists; a missing or unvalidated filler is `insufficient_evidence`, never `0`.
- Keep Ajv/Python parity and add valid + invalid examples for each change. Run `npm run test:contracts`.

### 2. Filler capability state (decision of 2026-10-20)
No filler route has passed. Freeze `capabilities.json` / catalog flags so filler localisation is **`unvalidated`** and the UI/coach must render `insufficient_evidence`. Add a data field for a later validated state. The goal is **preserved** and not narrowed; a later validated detector flips data only (Phase 08). Do not set any filler flag true.

### 3. Settings (HANDOFF §5.5)
`speech_readiness()` (Gnani only) and `reasoning_readiness()` (Gemini only) with no Supabase dependency; states `unconfigured|configured|verified`, and never `live` from presence alone. Freeze `GEMINI_MODEL` explicit default with an access date (observed `gemini-3.8-flash`; verify against https://ai.google.dev/gemini-api/docs/models first and cite). Add the TTS model/voice selector and a VAD settings object that survives reconnect. Secrets stay `SecretStr`; nothing is logged.

### 4. Ports (`services/voice/src/gnani_coach/ports/`)
Python `Protocol`s plus DTOs: `SpeechToTextPort`, `TextToSpeechPort`, `ReasoningPort`, `AnalysisPort`, `IdentityPort` (verify bearer token → `UserId | None`), `SessionStorePort` (metrics-only writes), `RecordingStorePort` (opt-in audio). Provider adapters from Phase 02 must satisfy the STT/TTS/Reasoning ports **without being edited**. If they can't, say so in REPORT; do not edit `providers/**`.

### 5. Frozen seams (exact names — G1 builds to these)

| Seam | Name / location | Owner after freeze | Unavailable behaviour |
|---|---|---|---|
| Web mount | `apps/web/src/features/call/index.ts` exports `CallExperience` (React component, no props except `{catalog}`); `page.tsx` renders it | Phase 04 | stub renders the existing honest starter notice |
| Voice conversation | `gnani_coach/conversation/router.py` exports `router` (FastAPI `APIRouter`) with WebSocket `/ws/call`, mounted in `main.py` | Phase 05 | stub closes with the error-shape code `not_available` |
| Voice history | `gnani_coach/persistence/router.py` exports `router`: `GET /api/history`, `POST /api/consent`, `GET/DELETE /api/recordings/{id}` | Phase 06 | `503` with error-shape `not_available` |
| Identity | `gnani_coach/identity/__init__.py` exports `get_identity() -> IdentityPort`; injected via FastAPI dependency | Phase 06 | returns the anonymous guest implementation |
| Web auth | `apps/web/src/lib/auth/index.ts` exports `useSession`, `signOut`; `apps/web/src/proxy.ts` placeholder | Phase 06 | guest state |
| Analysis | `gnani_coach/analysis/__init__.py` exports `get_analysis() -> AnalysisPort` | Phase 05 | returns `insufficient_evidence` |

You may change a name if there is a documented reason, but record the final names in `docs/contracts/seams.md`. G1 builders read only that file.

### 6. Call transport contract (`docs/contracts/call-transport.md` + event-envelope schema)
Browser↔voice over one WebSocket: client sends binary PCM16 frames, with the sample rate declared in an initial JSON `start` event, plus JSON control events (`mute`, `end`, `interrupt`, `retry`, `coaching_choice`). The server sends JSON events (`status`, `transcript_partial`, `transcript_final`, `coach_text`, `round_feedback`, `error`) and binary TTS audio chunks tagged by turn id. Define the sequence, ids, heartbeat, stale-turn suppression and caps (call length ≤ 10 min, message size). Auth: the token goes in the first `start` event or a short-lived query ticket. No credentials in URLs and none in the browser. Pick the least risky option and cite the source.

### 7. UI seams from `UI-REFERENCE.md`
Scenario presets (Team Meeting and Office Communication as presets under workplace; Custom Topic as a transient, non-persisted field), the recording-OFF default, and the states loading/error/insufficient-evidence/empty-history. Add the new catalog ids only if needed, and update the examples. Record the global design tokens location (`globals.css`) and apply the Speakify palette/typography baseline once, so Phase 04 does not need to edit it.

### 8. Integration test seam
`tests/integration/`: a minimal pytest/Playwright smoke that boots the service and checks that every mounted seam answers its stated unavailable behaviour, `/health` works, and the web page renders the `CallExperience` stub. B2 extends it.

## Constraints
- Search before any dependency, version, protocol or security decision. Cite URL in `docs/contracts/*` or REPORT. No new dependency without a cited reason and an exact pin.
- The waivers W01/W02 expire at Phase 03 dependency freeze or 2026-10-25: re-run `npm audit` (full + omit dev), report the result, and recommend renew/remove. CEO decides.
- Keep Phase 01/02 tests green.

## Criteria / commands (from repo root; save full output)
- `npm run test:contracts`
- `uv run --project services/voice python -m pytest services/voice/tests -v`
- `npm run lint`, `npm run typecheck`, `npm run build` (use the repo's actual script names; show them)
- the new `tests/integration` command
- `uv run --project services/voice python tools/probes/secret_scan.py` → 0 findings

## REPORT.md (required, in this folder)
Files changed; commands + raw output; the seam table as frozen; contract diffs by HANDOFF section number; the filler state; npm audit result; stubs handed to 04/05/06 (paths); limits; help needed. End with `PHASE 03 BUILT — AWAITING B1 TEST` or `BLOCKED: reason`. Stop there; do not start G1.
