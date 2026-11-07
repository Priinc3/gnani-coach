# Phase 03 — FIX 2: bring the frozen files in line with the built seams (small)

Type: NORMAL, contract owner. Siblings: Phase 05 is running a separate small FIX in `conversation/**` only. You must not touch G1 trees (`apps/web/src/{features,lib/auth,lib/audio,lib/transport,lib/session-ui}`, `services/voice/src/gnani_coach/{conversation,analysis,identity,persistence}`, `supabase/**`).

## Problem 🟠
G1 replaced three stubs, so nine of your integration assertions now fail by design. The failures are not code bugs. They are listed in COMM entries 06, 13, 14 and 15 and in the three REPORTs:

| File:line | Old stub expectation | Correct new behaviour |
|---|---|---|
| `tests/integration/test_seams.py:83,89,96` and `test_origins.py:163` | history, consent and recordings answer `503` | a guest gets `401` with the error shape (`unauthenticated`, `retryable:false`) |
| `test_seams.py:102` (`test_a_recording_route_never_returns_audio`) | JSON content-type from a `503` | a guest gets `401` JSON, never audio |
| `test_origins.py:188,205`, `test_seams.py:116` | first `/ws/call` message is `error` | the first message is `status` with `state: "connecting"` |
| `test_seams.py:148` | every analysis observation is `insufficient_evidence` | `turn.duration_ms` may be `available`. A missing transcription makes the rates `unavailable` (reason `stt_unavailable`) and never `0`. `filler.count` stays `insufficient_evidence` with `filler_detection_unvalidated` and a null value |
| `tests/integration/call-experience.spec.ts:17` and similar | the Phase 01 stub heading and a disabled start button | the real app: the landing heading is visible, Start is enabled and leads to the scenario picker. The page still requests no microphone on load |
| `tests/foundation/starter-screen.spec.ts` (10 failing) | the Phase 01 stub screen | Phase 04 reported the same properties are covered in `apps/web/tests/**`. **Decision:** retire the stub-specific tests in `tests/foundation` that Phase 04's suite covers (list the mapping in REPORT). Keep `lists all ten catalog languages` and `does not offer French`, and re-point them if needed. `tests/foundation/**` Python tests stay as they are. You own this edit because this FIX says so. |

## Fix (only these)
1. Update the assertions above to the new behaviour. Do not weaken them to pass: assert the status code, the error-shape fields, the first message type, and the three analysis rules.
2. Add one real-service check each that did not exist before: a guest `DELETE /api/recordings/x` gives `401`; `/ws/call` with an allowed Origin and an invalid `start` closes `1008`; `/ws/call` with a wrong sample rate answers `unsupported_audio_format`.
3. `.env.example` files: add `SUPABASE_PUBLISHABLE_KEY` (empty) and a one-line comment in the root and `services/voice/.env.example`. `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` already exist in the service file. Add `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` to `apps/web/.env.example` as **server-side** values. State plainly in comments that they are not `NEXT_PUBLIC_`. Keep your `test_voice_url.py` rule green: no `NEXT_PUBLIC_` secret.
4. `docs/contracts/seams.md`: record these decisions (CEO, 2026-10-22):
   - the history, consent and recording routes **stay out of the OpenAPI document** (the service publishes no API surface and the Phase 01 `/health`-only invariant stays). Fix the §2 sentence that says otherwise;
   - the owner of `SessionStorePort.save_metrics` is the verified request context (`identity.current_user()`); `save_metrics_for(user_id, record)` is the explicit form;
   - the first `/ws/call` message is `status connecting`;
   - saved recordings are `audio/wav` (16 kHz, mono, 16-bit) and the writer must send a real WAV (Phase 05 FIX-1).
5. Do not change any schema, name, route or port.

## Verify with (save full output under `evidence/fix-2/`)
`npm run test:contracts` · `npm run test:integration` (must be all green, with the real service and the real web app booted) · `npm run test:e2e` (green or only the retired tests removed) · `npm run lint` · `npm run typecheck` · `npm run build` · `uv run --project services/voice python -m pytest services/voice/tests -v` · `secret_scan.py`.
If an updated assertion fails because the service is wrong, **do not edit around it**. Stop and report `BLOCKED: <file:line, expected vs actual>`.

## Report
Append `## FIX-2` to `REPORT.md`: changed files, raw output paths, the retired-tests mapping. End with `PHASE 03 FIX-2 BUILT — AWAITING B2 TEST`. Stop there.
