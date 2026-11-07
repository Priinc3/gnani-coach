# Batch B1 TEST (Phases 01 + 02 + 03)

Run only after Phase 03 REPORT says `PHASE 03 BUILT`. You are the B1 tester. **Fix nothing.** Record results; CEO issues FIX files. Write `prompts/batch-B1-TEST-RESULT.md` with **raw output** (full stdout/stderr, exact command, cwd, runtime, exit code per command; redact only secrets and say where). Use immutable evidence under `prompts/batch-B1-evidence/<run-id>/`. Waiver W03 needs fresh, complete evidence here.

Credentials: names `GNANI_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL` must come from the process environment or `tools/probes/.env` (user-created; do not read or print values). If missing, mark every live item `BLOCKED: credentials not configured`, run everything else, and stop. Live budget total ≤ 40 wire attempts; use `--allow-live --max-requests` and put `--env-file` before the subcommand.

## 1. Happy path
1. `npm run test:contracts`; `uv run --project services/voice python -m pytest services/voice/tests -v`; web lint, typecheck and build; the Phase 03 integration test.
2. Start the service and web app; `/health` OK; each frozen seam (see `docs/contracts/seams.md`) returns its documented unavailable behaviour; the home page renders.
3. **Live chain** (one run): `run.py --env-file tools/probes/.env chain --language en-IN --fixture spoken-clear-sentence --voice Kaveri --tts-model timbre-v2.5 --allow-live --max-requests 8`. Record recognised text, reply, and TTS bytes.
4. **Filler routes** (the FIX-2 command, once): `run.py --env-file tools/probes/.env filler --allow-live --max-requests 16`. Record the E1 variants and E2 results with exact settings. This decides whether any route can pass; do not tune.

## 2. Top 3 edges
1. **No credentials / bad key:** the preflight and a chain with missing names show plain unavailable states, with no stack trace and no key echo.
2. **Over-limit / oversize:** `--max-requests 1` on the chain is refused **before** any call (0 wire attempts); oversize or malformed JSON, or a wrong sample rate, on the mounted `/ws/call` stub is rejected with the error-shape.
3. **Ambiguous / invalid language:** `en-IN` resolves to an ambiguity error naming English and Hinglish; `french` is rejected by membership. A schema-valid `french` id must still pass the shape check only.

## 3. Security probe
- `secret_scan.py` → 0 findings; grep the web **build output** for `GNANI|GEMINI|api-key|x-api-key-id` (no key names or values reach the client).
- Unauthenticated `GET /api/history`, `GET/DELETE /api/recordings/x` → `503`/`401`, never data.
- CORS: only the configured web origin is allowed; `Origin: https://evil.example` is not.
- No `.env` is tracked: `git ls-files | grep -i env` → only `.env.example`, if any.
- `npm audit` (full and `--omit=dev`) result vs W01/W02.

## 4. Cross-phase integration
- Contracts: the Ajv and Python parity suites both pass; every HANDOFF §5.1–5.4 change is present in the schemas **with** valid and invalid examples. A missing transcription cannot validate as a measured `0`.
- The Phase 02 adapters satisfy the Phase 03 ports without edits (`git diff --stat services/voice/src/gnani_coach/providers tools` is empty for Phase 03).
- Filler flags: grep `capabilities.json`/catalog: no filler flag is true; the state is `unvalidated`.
- Ownership: list files changed by Phase 03 and confirm all lie within its OWN paths (or the allowed stubs).
- Stubs: Phase 04/05/06 directories contain only the frozen seam stubs.

## Result format
`## Item → PASS | FAIL | BLOCKED → evidence path → one-line note`. End with counts and a list of anything unproven. Do not declare VERIFIED. Stop after the file.

> **2026-10-23:** superseded. B1 TEST skipped (W05); its items are executed through `prompts/batch-B3-TEST.md`.
