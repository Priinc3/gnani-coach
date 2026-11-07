# Batch B2 TEST (G1: Phases 04 + 05 + 06, plus the folded-in B1 checks per waiver W05)

Run only after **Phase 05 FIX-1** and **Phase 03 FIX-2** both report BUILT. You are the B2 tester. **Fix nothing.** Record results; the CEO issues FIX files. Write `prompts/batch-B2-TEST-RESULT.md` with raw output: exact command, cwd, runtime, exit code, and full stdout/stderr per command. Redact only secrets, and say where. Evidence goes in `prompts/batch-B2-evidence/<run-id>/`. Fresh evidence only: do not cite builder logs.

Credentials: `GNANI_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL` from the process environment or `tools/probes/.env`. Never read or print values. Missing means `BLOCKED: credentials not configured` for each live item. Run everything else and stop at the end. Live budget total ≤ 40 wire attempts. Supabase: use the local stack only if the CLI and Docker exist. Otherwise mark `BLOCKED: no local Supabase`.

## 0. Baseline (every command must exit 0)
`npm run test:contracts` · `uv run --project services/voice python -m pytest services/voice/tests -v` · `npm run lint` · `npm run typecheck` · `npm run build` · `npm run test:integration` · `npm run test:e2e` · `npx playwright test --config apps/web/tests/playwright.config.ts` · `npx playwright test --config=prompts/phase-06-private-history/web-tests/playwright.config.ts` · `uv run --project services/voice python tools/probes/secret_scan.py` (0 findings). Add `git status --short` and `git diff --stat` after the run (nothing generated may be left untracked outside the ignored caches).

## 1. Happy path, assembled (real service + real web app, fakes only for the providers)
Boot the voice service and the web app. With a fake-provider harness (in `tests/` or `prompts/batch-B2-evidence/`, not in a G1 tree):
1. Browser → `/ws/call`: `start` → `ready` → 16 kHz frames → transcript → coach text and audio → 4 turns → one `round_feedback` → `retry` → end. Check the UI shows each state, the fenced/stale-turn audio never plays, and the session ends with no live socket.
2. Authenticated path (fake Supabase Auth, or the local stack): the token in `start` verifies, the metrics row is saved for that user, and `GET /api/history` returns it.
3. Recording OFF: metrics only, no audio object, and `recordingId: null`. Recording ON with consent: a recording is saved **and `GET /api/recordings/{id}` returns bytes that parse as a valid WAV** (`wave.open`: 1 channel, 16 000 Hz, 16-bit) and play in the browser's history replay. This is the Phase 05 FIX-1 check.
4. Consent withdrawn mid-call: the metrics are saved and no recording is written.

## 2. Top edges
1. **Interrupt:** the learner speaks over the coach → the audio stops, the late reply and late audio are never played or sent, the round state survives, and the measured interrupt-to-stop is recorded over 20 trials (the target p95 ≤ 300 ms is for the real stack. Report the fake-stack number and say it is not the target).
2. **Silence, noise, no speech:** a round with no speech yields `insufficient_evidence`/`missing-transcription`, and never a `0` rate and never invented feedback.
3. **Disconnect and duplicates:** a socket drop → a bounded reconnect with a new connection id, no duplicated turn, and an old-connection event dropped. A duplicate `sequence` is dropped. A double-click on Start opens one connection.
4. **Bad input:** a >16 KiB `start`, a malformed `start`, a wrong sample rate, a wrong frame size, a bad Origin, and a bad token. Each gets the frozen error shape, the right close code, and no stack trace or token echo.
5. **Load:** 10 concurrent calls with fakes. Memory and connections stay bounded. Per-address and per-user caps refuse excess calls with the error shape.
6. **Offline / slow:** the UI shows plain-word status within 1 s and no dead end.

## 3. Security probe
- Isolation matrix, run for real: user A and user B. B cannot read, list or delete A's recording or session. The `404` for a foreign id is **byte-identical** to a missing id apart from correlation id and timestamp. Forged `user_id` in a body is ignored. A guest gets `401` everywhere.
- Token matrix: missing, malformed, expired, wrong audience, wrong issuer, valid.
- Withdraw/delete races: a late save after a delete or a withdrawal cannot resurrect the recording.
- Metrics-only inspection: after calls with recording OFF, grep the fake DB, the logs (captured at DEBUG) and any temp or cache dir for the test transcript, reply text and custom topic. There must be none.
- Secrets: grep the web build output (`apps/web/.next`) for `GNANI`, `GEMINI`, `SERVICE_ROLE`, `x-api-key-id`. None. Only `NEXT_PUBLIC_VOICE_WS_URL` is public. The service-role key never appears in the web tree.
- CORS and WS Origin: the allowed origin works, `https://evil.example` fails on both the preflight and the handshake.
- `git ls-files | grep -i env` → only `.env.example` files. `npm audit --omit=dev` → 0. Report `npm audit` (full) against W01.
- SQL: RLS on every table, no `anon`/`public` policy, private bucket, the content-key check constraint. Re-run `evidence/local_postgres_check.sh` from Phase 06 against a local PostgreSQL if present.

## 4. Live items (the folded-in B1 TEST; ≤ 40 wire attempts total)
1. `run.py --env-file tools/probes/.env chain --language en-IN --fixture spoken-clear-sentence --voice Kaveri --tts-model timbre-v2.5 --allow-live --max-requests 8` and record the recognised text, the reply and the TTS bytes.
2. `run.py --env-file tools/probes/.env filler --allow-live --max-requests 16` (E1 and E2 only). Record exact settings and results. This is the first and only live answer on the filler routes. Do not tune.
3. Phase 05's opt-in live test (`GNANI_LIVE_TESTS=1`, ≤ 16 attempts).
4. If everything above passes, one real browser call against the real service with a headset or a fake mic, 4 turns, in English. Record the end-of-turn-to-first-audio latency per turn from the service logs (numbers only) and report the p50 and max. Do not claim p95 from fewer than 30 turns.

## 5. Cross-phase and ownership
- Contracts: Ajv and Python parity pass. Every message the real client sends validates against the schemas, and every server envelope validates too (capture a call and run it through Ajv).
- Seams: names exactly as in `docs/contracts/seams.md`; the first `/ws/call` message is `status`; the history routes have the `ADDENDUM §B` shapes.
- Ownership: list files changed per phase from git (the tree should be committed first) and confirm that none lie outside OWN paths or the one manifest exception. Confirm `providers/**`, `tools/**`, `fixtures/**` and `UI.png` are unchanged since the Phase 03 manifest hash (`prompts/phase-03-contract-freeze/evidence/fix-1/provider-package-manifest.sha256`).
- Filler: no filler flag is true anywhere; no UI or service output contains a filler count. Every filler surface shows `insufficient_evidence` with `filler_detection_unvalidated`.
- No overall score, confidence %, pronunciation grade or fake history in any screen (grep the UI text of every captured state).
- W03 (fresh complete evidence): every command above has its full stdout/stderr saved.

## Result format
`## Item → PASS | FAIL | BLOCKED → evidence path → one-line note`. End with counts, a list of everything unproven, and what the live items would have shown. Do not declare VERIFIED. Stop after the file.

> **2026-10-23:** B2 TEST was skipped by user order (waiver W06). Do not run this file on its own. Its items are executed as part of `prompts/batch-B3-TEST.md`.
