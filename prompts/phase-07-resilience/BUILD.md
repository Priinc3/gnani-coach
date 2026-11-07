# Phase 07 — resilience (B3, NORMAL)

You are Phase 07. **Siblings running now: none.** G1 (04/05/06) is finished and its trees are yours now. Phases 08 and 09 wait for you. Comm folder: none.

Goal link: `prompts/00-plan.md` §2 and §9. The product is built but was never tested **assembled**, and no provider has been called live. You make the call path survive failure, prove the pieces work together, and fix real defects. **Do not refactor, restyle or add features.** The contest deadline is **2026-11-10**, so every item below is either a defect fix or a test that proves behaviour.

## OWN (write)
`apps/web/**` · `services/voice/**` (including `providers/**`, which Phase 02 is no longer using) · `supabase/**` · `tests/integration/**` · root dependency and config files (exact pins, with a cited reason) · `docs/operations/**` · your own `prompts/phase-07-resilience/REPORT.md` + `evidence/`.
DO NOT TOUCH: `packages/contracts/**` (a contract change needs a CEO FIX), `tools/**`, `fixtures/**`, `UI.png`, `docs/{contracts,feasibility}/**` except one-line corrections you list in REPORT, CEO files (plan, tracker, waivers, BUILD/FIX/VERIFY, batch-*).

## Read first
`docs/contracts/{seams,call-transport,capability-states}.md`, the REPORTs of phases 03–06 (their **Limits** sections are your defect list), `prompts/waivers.md`, `prompts/batch-B2-TEST.md` (its §1–3 and §5 are the assembled checks you now automate).

## Precondition
If `git status` shows the tree uncommitted, do **not** commit. Record a sha256 manifest of the tracked source files at the start (`evidence/start-manifest.sha256`) so the ownership check works. State this in REPORT.

## Deliverables

### A. The assembled automated test (replaces the skipped B2 TEST's no-credential items)
Under `tests/integration/assembled/`, with a fake-provider harness (fake STT, TTS, Gemini, and Supabase Auth + REST + Storage over HTTP, in-process or as a local stub server) that boots the **real** voice service and the **real** Next.js app, and drives a **real browser** (Playwright, Chromium, fake mic) through the whole product:
1. Guest call: start → 4 turns → `round_feedback` → retry → end. The UI shows each state. No live socket remains afterward.
2. Authenticated call, recording OFF: metrics saved for that user, `recordingId: null`, no audio object. `GET /api/history` shows the session in the History screen.
3. Authenticated, recording ON: the recording is saved, **`GET /api/recordings/{id}` returns bytes that parse with `wave`**, and the History replay control plays it (assert the `<audio>` element loads, `readyState ≥ 2`, `duration > 0`). Delete it from the UI: it is gone and a repeat returns `404`.
4. Consent withdrawn mid-call: metrics saved, no recording.
5. Interrupt: the learner speaks over the coach → audio stops, late reply/audio never reach the page. Record the stop time over 20 trials (fake stack. Label it "not the real target").
6. Sign-out closes a live call (`onSignOut`).
7. Isolation: user B cannot read, list or delete user A's recording or session; foreign and missing ids give identical `404`s; forged `user_id` ignored.
8. Metrics-only inspection: after recording-OFF calls, grep the fake DB, the captured service logs (DEBUG) and temp/cache dirs for the test transcript, reply text and custom topic: none.
Every message the browser sends and every server envelope is validated against `packages/contracts` schemas (Ajv in the test).

### B. Failure matrix (each: expected behaviour, an automated test, plain-word UI)
Gnani STT down / auth rejected / throttled · TTS down mid-sentence · Gemini timeout or malformed JSON · Supabase Auth down (call continues as guest, no data written, clear notice) · Supabase REST/Storage down at call end (the call ends cleanly, the learner is told the session was not saved) · socket drop mid-turn (bounded reconnect, no duplicate turn) · tab close / mic unplugged · 10 min cap · expired token mid-call · double Start · 10 concurrent calls (bounded memory, caps refuse extras with the error shape). Fix every defect these tests find, inside your OWN paths.

### C. Known defects to close (from the REPORTs' Limits)
1. `GNANI_TTS_WS_URL` in settings is ignored by the TTS client (it dials its own default): make config and client agree, then test.
2. Reasoning round-feedback has no provider-side response schema (COMM 18): add it **only if** `providers/gemini.py` supports a response schema cleanly. Cite https://ai.google.dev/gemini-api/docs/structured-output. Otherwise leave the local validation and say so.
3. The stray hoisted `eslint@9.39.5` peer copy: fix with a lockfile refresh only if `npm ls` and lint stay green. Otherwise leave it and note it.
4. Per-process connection caps: document the multi-worker behaviour in `docs/operations/` and read the caps from settings.
5. Any `include_in_schema`/OpenAPI, `.env.example` or doc drift you find against `docs/contracts/seams.md`.

### D. Security hardening (research and cite each; OWASP https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html is a start)
Security response headers on the web app (CSP that still allows the worklet and `ws(s)` to the voice URL, `frame-ancestors`/clickjacking, referrer, nosniff, permissions policy allowing only the microphone for self); request body and message size limits and rate limits on the HTTP routes and the WS handshake per address (state the worker caveat); token and cookie handling review (no token in logs or URLs; cookies `Secure`/`HttpOnly`/`SameSite` as Supabase SSR sets them); CORS and WS Origin are strict in non-local settings (startup refuses `localhost` origins when `SPEAKING_COACH_ENVIRONMENT=production`, and refuses missing Supabase URL when a Supabase key is set); dependency audit (`npm audit`, `npm audit --omit=dev`, and `uv` equivalent if available) against waiver W01; secret scan 0; confirm no `.env` is tracked.

### E. Observability that is content-free
Structured log lines carry ids, counts, durations, error categories only. Add **end-of-turn → first coach audio byte** latency per turn (ms) to the logs and expose p50/p95 over the last N turns at a protected `/health/latency`-style endpoint **only if it returns numbers and no content** (state the exposure and auth you chose. If you cannot protect it, log only). Provide `tests/integration/live/` with an opt-in latency harness (skipped without `GNANI_LIVE_TESTS=1` and the three env names) that Phase 08 and the final test can run for ≥ 30 turns.

### F. Operations doc
`docs/operations/` — how to run, config table (names only), failure modes and what the learner sees, how to rotate keys, log-content rules, and the provider-retention sentence (Gnani keeps the raw transcript in its billing records; our toggle cannot waive that).

## Criteria / commands (repo root, save full output to `evidence/`)
`npm run test:contracts` · `uv run --project services/voice python -m pytest services/voice/tests -v` · `npm run lint` · `npm run typecheck` · `npm run build` · `npm run test:integration` (existing) · the new assembled command (add `npm run test:assembled`) · `npm run test:e2e` · `npx playwright test --config apps/web/tests/playwright.config.ts` · the Phase 06 web tests (`prompts/phase-06-private-history/web-tests/` config) · `uv run --project services/voice python tools/probes/secret_scan.py` (0) · `npm audit` / `npm audit --omit=dev`. Everything must exit 0. If a defect cannot be fixed inside your OWN paths, stop that item and report `BLOCKED:` with file:line.

## Constraints
No live provider call, no credential reads, no paid service, no commit/push/deploy. Search before any decision and cite URLs. No new dependency without a pin and a reason. No score, no confidence, no filler count anywhere. Filler stays `insufficient_evidence`.

## REPORT.md
Files changed; commands with raw output paths; the failure matrix with test names; defects found and fixed (file:line before/after); the security checklist with sources; latency numbers from the fake stack, labelled; limits (what is still fake-proven: no provider, no real mic, no real Supabase). End `PHASE 07 BUILT — AWAITING B3 TEST` or `BLOCKED: reason`. Stop there. Do not start Phase 08.
