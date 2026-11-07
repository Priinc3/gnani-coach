# G1 contract addendum — CEO decisions, 2026-10-20

Read with `docs/contracts/seams.md` and `call-transport.md`. These close seams Phase 03 left open. If something is missing, post `HELP:` in COMM.md. Do not guess.

## A. Store access (Phase 05 ← Phase 06)
Phase 06 adds these to `gnani_coach/persistence/__init__.py`, alongside `router`:
- `get_session_store() -> SessionStorePort | None`
- `get_recording_store() -> RecordingStorePort | None`

Each returns `None` when storage is unconfigured. Phase 05 imports them lazily, inside a `try/except ImportError` that treats a missing name as `None`. Phase 05 tests use in-memory fakes of the ports. Phase 05 must never import from `persistence/*` any other way.

Write rules (Phase 05 enforces; Phase 06 re-enforces):
- A **guest** (`get_identity().verify_token(...)` returned `None`) writes nothing.
- An authenticated user gets `save_metrics(doc)` at call end. The doc is the validated durable-metrics shape: numbers and ids only.
- Audio goes to `save_recording` only if `settings.consent.recordingRetentionGranted` is true from `start` **and** the user is authenticated. Re-check the flag at write time. Never write after `end`/disconnect-without-consent.

## B. HTTP shapes (Phase 06 implements; Phase 04 consumes)
All use `Authorization: Bearer <access token>`; no cookies. Errors use the frozen error shape.

| Route | Request | Success | Other |
|---|---|---|---|
| `GET /api/history` | — | `200 {"sessions":[{sessionId,recordedAt,practiceLanguageId,scenarioId,recordingId|null,turnCount,speakingTimeMs}]}`, newest first; `{"sessions":[]}` when none | guest/no token → `401` (Phase 04 renders the guest state, not an error) |
| `POST /api/consent` | `{"consentVersion":str,"recordingRetentionGranted":bool}` | `200 {"recordingRetentionGranted":bool,"recordingRetentionGrantedAt":str|null}` | withdrawing stops future retention and does not delete old recordings |
| `GET /api/recordings/{id}` | — | `200 audio/wav` bytes | someone else's or a missing id → `404` identically (no existence leak) |
| `DELETE /api/recordings/{id}` | — | `204` | non-owner → `404`; a repeat delete → `404` |

Phase 04 derives `VOICE_HTTP_URL` from `VOICE_WS_URL` in its own lib (`ws→http`, `wss→https`, path stripped). It does not edit `lib/voice.ts`.

## C. Web access token (Phase 04 ← Phase 06)
Phase 06 adds an **additive** export to `apps/web/src/lib/auth/index.ts`: `getAccessToken(): Promise<string | null>` (`null` for a guest). The stub has no such export yet. Phase 04 must typecheck without it, so it reads it through a 04-owned adapter, `apps/web/src/lib/session-ui/accessToken.ts`: `(await import("@/lib/auth")) as unknown as {getAccessToken?: () => Promise<string|null>}`, with a guest fallback. Phase 04 never edits `lib/auth/**`.

## D. Audio format
Phase 04 captures with an AudioWorklet, downsamples to **16 kHz mono s16le**, and sends **1,024-byte** frames at real-time cadence (32 ms). `start.audio.sampleRateHz` is `16000`. Phase 05 accepts only 16000 in G1 and answers anything else with an `error` envelope (`code: unsupported_audio_format`) and a close. TTS returns follow the descriptor in `call-transport.md`; Phase 04 plays them by turn id.

## E. Supabase env (Phase 06)
Checked: `settings.supabase` has only `url` (`SUPABASE_URL`) and `service_role_key` (`SUPABASE_SERVICE_ROLE_KEY`). There is **no publishable-key field**, and `settings.py` is Phase 03's, so Phase 06 does not add one. Phase 06 reads `SUPABASE_PUBLISHABLE_KEY` straight from `os.environ` in its own module (Python: only if the Auth `/user` check or JWKS call needs the `apikey` header; web: server-side only). Use the `url` field from settings. The service role key is used only by the Python stores, never logged or returned, never in the web app.

The `NEXT_PUBLIC_` rule in Phase 03's integration test forbids any other public variable, so the web side reads `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` **server-side** and passes them to the browser client as props. Document the names in `supabase/README.md` (your tree). `.env.example` files are Phase 03's: post `HELP:` for an entry.

## F. Manifest exception (the only one)
Normally manifests and locks are read-only in G1. **Phase 06 alone** may edit `apps/web/package.json`, `services/voice/pyproject.toml`, `package-lock.json` and `services/voice/uv.lock`, **dependencies only**, with exact pins and a cited reason. It does this **first**, posts `INFO: deps installed` in COMM, and never touches them again. Phases 04 and 05 add no dependency. They must not run `npm install`, `npm ci` or `uv sync` after that notice appears in COMM until they read it. Use `npm ci` / `uv sync` only to restore.

## G. COMM and STATUS (all three builders)
The first builder to start creates `prompts/parallel-G1/COMM.md` and `STATUS.md` from these stubs. The others append or update their own row.

`COMM.md` stub:
```
# G1 COMM (max 60 lines; prune oldest RESOLVED)
## 00 --:-- — group opened by CEO. Read ADDENDUM.md. INFO
```
Entries: `## NN HH:MM — <≤25 words>` plus a tag `INFO|HELP|DECISION|BLOCKED`. No code or logs; link your REPORT. The author appends `RESOLVED: reason`.

`STATUS.md` stub:
```
| Phase | State | Updated | Doing now | Need |
|---|---|---|---|---|
| 04 | NOT STARTED | - | - | - |
| 05 | NOT STARTED | - | - | - |
| 06 | NOT STARTED | - | - | - |
```
Update only your own row: at start, on a state change and at finish. State is `ACTIVE|BLOCKED|DONE`; Doing is under 15 words. Read both files at start and before REPORT.

## H. Shared rules
- Editing another phase's OWN file is a 🔴 fail. A shared change needs `HELP:` in COMM and a wait for a CEO FIX.
- Provider keys are never read by tests. Live provider calls: none from 04 and 06. Phase 05 may make a live call only in its own opt-in test, marked `live`, ≤ 16 wire attempts, and only if the three env names exist. Otherwise write `BLOCKED: credentials not configured` for that item and carry on.
- No commit/push/deploy/delegation. Search before any decision; cite the URL in your REPORT.
- Filler: unvalidated. Always render or return `insufficient_evidence` with reason `filler_detection_unvalidated`. Never a count, never `0`.
- Every report ends `PHASE NN BUILT — AWAITING B2 TEST` or `BLOCKED: reason`. Stop there.
