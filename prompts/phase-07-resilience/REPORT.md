# Phase 07 — resilience (B3) report

**Result: built. No commit, no push, no deploy, no live provider call.**

The worktree was already uncommitted when Phase 07 started. The starting
hashes of the 113 files that were tracked then are recorded in
`prompts/phase-07-resilience/evidence/start-manifest.sha256`; nothing was
committed or reverted. Many Phase 04–06 paths were untracked at the start, so
the tree cannot be diffed cleanly against a commit. The final worktree status
is saved at `prompts/phase-07-resilience/evidence/final-worktree-status.txt`.

## 1. What was built

- An **assembled** suite: a fake Supabase HTTP service, the real FastAPI app
  with its real lifespan, the real Next.js app and Chromium with a
  deterministic fake microphone. Only the speech/reasoning/analysis ports,
  the microphone signal and Supabase are doubles.
- A1–A8 browser acceptance tests, F1–F10 browser failure tests, 18 assembled
  Python tests (failure matrix, caps, WAV/replay, 20-trial interrupt stop
  time) and two security-header tests.
- The failure matrix B, the known defects C1–C5, the security hardening D,
  content-free observability E and the operations doc F.
- `docs/operations/RUNBOOK.md`, an opt-in live harness, and updated
  `.env.example` files.

## 2. Files changed (Phase 07 edits only)

**Voice service**

- `services/voice/src/gnani_coach/settings.py` — caps, HTTP/WS budgets,
  `health_token`, production boundary.
- `services/voice/src/gnani_coach/security.py` — fixed-window per-address
  rate limiter.
- `services/voice/src/gnani_coach/main.py` — lifespan wiring, per-address
  HTTP 429, protected `/health/latency`.
- `services/voice/src/gnani_coach/observability/{__init__.py,latency.py}` —
  bounded latency registry (200 turns).
- `services/voice/src/gnani_coach/conversation/connections.py` — process
  cap + configurable caps.
- `services/voice/src/gnani_coach/conversation/router.py` — handshake budget,
  host-only address, async consent checker, C1 URL plumbing.
- `services/voice/src/gnani_coach/conversation/runtime.py` — notices, consent
  re-check, persistence outcome, latency recording, round-feedback turn id,
  recording-not-saved notice.
- `services/voice/src/gnani_coach/conversation/providers.py` — pass the
  configured STT/TTS URLs.
- `services/voice/src/gnani_coach/providers/tts.py` — use the configured URL
  and validate it.
- `services/voice/src/gnani_coach/ports/provider_adapters.py` — URL plumbing.
- `services/voice/tests/providers/test_tts_protocol.py` — C1 regression test.
- `services/voice/tests/test_resilience_guards.py` — caps, limiter, latency
  window, production guard, `/health/latency` (9 tests).

**Web**

- `apps/web/next.config.ts` — CSP/security headers, production boundary,
  allowed dev origins.
- `apps/web/src/lib/session-ui/callState.ts` — sticky `notice`, `splitNotice`,
  status reducer.
- `apps/web/src/lib/session-ui/useCallSession.ts` — end-wait for `status
  ended`, sign-out teardown, mic-ended guard.
- `apps/web/src/lib/transport/client.ts` — `requestEnd` keeps the socket for
  the final notice.
- `apps/web/src/lib/audio/capture.ts` — track-ended listener.
- `apps/web/src/features/call/views/{CallView,SummaryView}.tsx` — notices.
- `apps/web/src/features/call/views/HistoryView.tsx` — `preload="metadata"`.
- `apps/web/src/features/call/CallExperience.tsx` — sign-out wiring.

**Tests, config, docs**

- `tests/integration/assembled/` — `harness.py`, `launcher.py`,
  `fake_supabase.py`, `fake_stack.py`, `conftest.py`, `constants.ts`,
  `instrumentation.ts`, `contracts.ts`, `playwright.config.ts`,
  `assembled.spec.ts`, `security.spec.ts`, `test_failure_matrix.py`,
  `test_interrupt_latency.py`.
- `tests/integration/live/test_latency.py` — opt-in 30-turn live harness.
- `package.json` — `test:assembled`; `test:integration:service` ignores the
  assembled directory.
- `playwright.integration.config.ts` — ignores `assembled/**` so the existing
  integration suite does not collect the Phase 07 specs.
- `docs/operations/RUNBOOK.md`.
- `.env.example`, `services/voice/.env.example`.
- `prompts/phase-07-resilience/REPORT.md` and `evidence/`.

No file under `packages/contracts/**`, `tools/**`, `fixtures/**`, `UI.png`,
`docs/{contracts,feasibility}/**` or the CEO files was edited by Phase 07.

## 3. Acceptance commands

Raw output is in `prompts/phase-07-resilience/evidence/`.

| Command | Result | Raw log |
| --- | --- | --- |
| `npm run test:contracts` | PASS (78 examples, 8 schemas) | `test-contracts.log` |
| `uv run --project services/voice python -m pytest services/voice/tests -v` | **510 passed, 4 skipped** | `pytest-voice.log` |
| `npm run lint` | exit 0 | `lint.log` |
| `npm run typecheck` | exit 0 | `typecheck.log` |
| `npm run build` | exit 0 | `build.log` |
| `npm run test:integration` | 45 passed, 1 skipped (Python) + 5 passed (Playwright) | `test-integration.log` |
| `npm run test:assembled` | **18 passed (Python) + 20 passed (Playwright)** | `test-assembled.log` |
| `npm run test:e2e` | 2 passed | `test-e2e.log` |
| `npx playwright test --config apps/web/tests/playwright.config.ts` | 77 passed | `web-tests.log` |
| `npx playwright test --config prompts/phase-06-private-history/web-tests/playwright.config.ts` | 14 passed | `phase06-web-tests.log` |
| `uv run --project services/voice python tools/probes/secret_scan.py` | 0 findings | `secret-scan.log` |
| `npm audit --omit=dev` | 0 vulnerabilities | `npm-audit-omit-dev.log` |
| `npm audit` | **exit 1 — 5 high, unchanged W01** | `npm-audit.log` |
| `npm ls --all` | exit 0 | `npm-ls-all.log` |
| `git ls-files` `.env` check | only `.env.example` files | `tracked-env-files.log` |

### The one non-zero command, stated plainly

`npm audit` exits 1 with the **same** 5 high-severity `braces` chain that
waiver **W01** has covered since Phase 01:
`eslint-config-next@16.4.2 → @next/eslint-plugin-next → fast-glob@3.3.1 →
micromatch@4.0.8 → braces@3.0.3`, advisory
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
The advisory lists **no patched version**; `npm audit fix --force` would
downgrade to `eslint-config-next@14.2.35`, a breaking dev-only change. W01
renewed on 2026-10-20 and explicitly says: do not suppress the advisory, do
not disable lint, and **do not call the full dependency audit clean**. The
production tree is clean (`npm audit --omit=dev` = 0). The lockfile was not
changed. This is not a new finding and not hidden; if the CEO wants a zero
exit here, that is a W01 decision, not something this phase may fake.

## 4. A1–A8 (assembled browser suite)

All tests are in `tests/integration/assembled/assembled.spec.ts`; every server
envelope the browser sent or received is validated with the frozen Ajv
schemas from `packages/contracts`.

| Test | What it proves |
| --- | --- |
| A1 — guest 4 turns, round break, retry, clean end | four real turns, a round-feedback card, "Try again" starts a retry, each call state is visible, the socket closes 1000, and no data is written |
| A2 — authenticated, recording off | metrics saved, **no audio object**, History shows the session |
| A3 — authenticated, recording on | WAV saved; `test_a_recording_is_a_wav_that_parses_and_delete_removes_it` parses it with Python's `wave` (`RIFF/WAVE`, duration > 0); History replay reaches `readyState >= 2` with a duration; delete removes it and the next GET is 404 |
| A4 — consent withdrawn mid-call | metrics saved, no audio object |
| A5 — interrupt | playback stops, the late reply/audio never reaches the page; the 20-trial timing is Python, labelled fake |
| A6 — sign-out | the live call socket is closed |
| A7 — isolation | user B cannot list/read/delete A's data; a foreign id, a missing id and a forged `user_id` give the same 404 shape |
| A8 — metrics-only | no transcript, reply or custom topic in the DB, the service log or the project temp/cache dirs |

## 5. Failure matrix B

The row is green only because the named test exists and the UI is plain-word.

| Failure | Automated test(s) | What the learner sees |
| --- | --- | --- |
| Gnani STT network | `test_a_recognition_failure_keeps_the_call_alive[network-…]`, F4 | "The speech service is having trouble."; the call can still end |
| Gnani STT auth rejected | same test `[auth-…]` | "That request was not valid."; call survives |
| Gnani STT throttled | same test `[throttle-…]` | "Too many requests at once."; call survives |
| TTS down mid-sentence | `test_a_tts_failure_mid_sentence_is_named_and_the_call_survives`, F5 | speech-service title; call survives |
| Gemini timeout | `test_a_reasoning_timeout_is_named_and_the_call_survives`, F6 | "That took too long."; call survives |
| Gemini malformed feedback JSON | `test_a_malformed_feedback_document_falls_back_to_the_facts` | facts-only fallback, no invented strength/note, filler stays `insufficient_evidence` |
| Supabase Auth down | `test_supabase_auth_down_continues_as_a_guest_with_a_notice`, F7 | call continues as guest, `notice:` says sign-in could not be confirmed, no data |
| Supabase REST down at end | `test_supabase_rest_down_at_the_end_says_not_saved`, F8 | "This session was not saved…", clean end |
| Supabase Storage down at end | `test_supabase_storage_down_keeps_the_metrics_and_says_the_audio_is_missing`, F9 | metrics saved; "The recording could not be saved…" in the summary |
| socket drop mid-turn | F3 | bounded reconnect, no duplicate transcript turn |
| tab close | F10 | session persisted on disconnect |
| microphone unplugged | F2 | "Your microphone was disconnected…", call released |
| 10-minute cap | Phase 05 `test_the_call_cap_ends_the_call_cleanly` (cited, not duplicated) | clean end |
| expired token mid-call | `test_an_expired_token_mid_call_does_not_drop_or_re_key_the_session` | session stays on A's id |
| double Start | F1 | exactly one call socket |
| 10 concurrent calls | `test_ten_concurrent_calls_are_bounded_and_the_eleventh_is_refused`, `test_the_user_cap_refuses_a_third_call_with_the_frozen_error_shape`, `test_the_process_cap_refuses_the_eleventh_connection` | 11th refused `1008`; user excess gets `too_many_connections` |

The 10-minute cap and idle timeout are Phase 05's tests; Phase 07 did not
rewrite them.

## 6. Known defects C1–C5

### C1 — `GNANI_TTS_WS_URL` was dead configuration

**Before:** `GnaniTtsSession` stored the endpoint but always dialled
`DEFAULT_TTS_URL`; `settings.voice.tts_ws_url` never reached the client.
**After:** `conversation/providers.py:81` passes
`url=settings.voice.tts_ws_url`; `providers/tts.py:324-331` stores and
validates it, and `providers/tts.py:378` dials `self.url`. Regression test:
`services/voice/tests/providers/test_tts_protocol.py:373`
`test_the_configured_endpoint_is_the_one_dialed`, which captures the URL given
to the transport (not just an attribute).

### C2 — Gemini response schema

`providers/gemini.py` has no clean provider-side response-schema hook for this
call path, so the local validation remains. Source:
<https://ai.google.dev/gemini-api/docs/structured-output> (checked
2026-10-23). The malformed-feedback test proves the fallback is facts-only and
does not invent a score.

### C3 — stray hoisted `eslint@9.39.5`

Left in place, as W02 allowed. `npm ls --all` exits 0 (`npm-ls-all.log`), lint
is green on `eslint@10.13.0` and the hoisted copy is not run by any script.
The next supported lockfile refresh may remove it; forcing one now would be an
unverified dependency change.

### C4 — per-process caps

Caps now come from settings (`settings.py:290-292`), are applied by
`connections.py:49-60` and enforced before accept (`router.py:105-129`) or
after the token is known (`runtime.py:523-526`). The multi-worker caveat is in
`docs/operations/RUNBOOK.md` §3 and in the module docstring. Tests:
`test_resilience_guards.py` and the two assembled cap tests. The process bound
is 10 by default.

### C5 — OpenAPI / env / doc drift

The history, consent and recording routes and `/health/latency` are
intentionally outside the OpenAPI document (CEO decision; `/health/latency`
uses `include_in_schema=False` at `main.py:233`). No contract file was
changed. The `.env.example` files now list the caps, the latency token and the
live-harness opt-in; the old examples did not.

## 7. Defects found while testing (not on the C list)

1. **`round_feedback` carried `turnId: null`**, so "Try again" was disabled
   forever. **Before:** `runtime.py` sent the feedback with a null turn id.
   **After:** `runtime.py:1235-1238` attaches the last learner turn of the
   round. A1 clicks "Try again".
2. **The sticky notice was lost** because the status reducer could not see the
   status it was switching on. **Before:** `callState.ts` had no local status
   binding in the `status` case. **After:** `callState.ts:162` binds
   `const status = action.payload.state`, and `splitNotice`
   (`callState.ts:116`) keeps the notice sticky across the following
   `listening`. This is what makes the auth/not-saved notices visible.
3. **The end notice never reached the page.** **Before:** the client tore the
   socket down immediately on End, so `status ended` (and a not-saved notice)
   was lost. **After:** `useCallSession.ts:215-226` waits for the service's
   `ended` and falls back after two seconds; `client.ts:174` keeps the socket
   open for that answer. F8/F9 and A1 assert it.
4. **A mic unplug showed the wrong sentence.** **Before:** the track-ended
   handler tore down the context, and the still-starting capture promise then
   rejected with a generic "another app is using your microphone" error,
   overwriting the correct message. **After:** `useCallSession.ts:86,168,
   197,205` set and check `micEndedRef`; the disconnected sentence survives.
   F2.
5. **A Storage failure was silent.** **Before:** metrics saved, the recording
   vanished, and the learner was told nothing. **After:**
   `runtime.py:135,1459-1460` sends the separate recording-not-saved sentence;
   `runtime.py:1059-1065` uses it in `status ended`. F9 and the Python test.
6. **History replay did not preload metadata.** **Before:** the player had no
   reliable duration. **After:** `HistoryView.tsx:255` uses
   `preload="metadata"`; A3 waits for `readyState >= 2` and duration > 0.
7. **A failing identity used to end the call.** Phase 05's behavior was
   changed deliberately: an unverifiable token now continues as a guest with
   a `notice:` on `ready` and writes nothing (renamed
   `test_a_failing_identity_continues_as_a_guest_with_a_notice`). This is the
   BUILD's Auth-down requirement; it is a behavior change, not a regression.

## 8. Security checklist D

Sources (all checked 2026-10-23):

- OWASP WebSocket Security Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>
- OWASP Secure Headers Project:
  <https://owasp.org/www-project-secure-headers/>
- MDN `Permissions-Policy`:
  <https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy>
- Next.js `headers`:
  <https://nextjs.org/docs/app/api-reference/config/next-config-js/headers>
- OWASP ASVS:
  <https://owasp.org/www-project-application-security-verification-standard/>
- Gemini structured output (C2):
  <https://ai.google.dev/gemini-api/docs/structured-output>

| Item | Evidence |
| --- | --- |
| CSP allows the AudioWorklet and the voice WS, denies framing | `apps/web/next.config.ts:86-113`; `security.spec.ts` asserts `default-src 'self'`, `worker-src 'self' blob:`, `connect-src` with `ws://127.0.0.1:8017`, `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'` |
| Clickjacking | `X-Frame-Options: DENY` (asserted by `security.spec.ts`) |
| Referrer / sniffing | `strict-origin-when-cross-origin`, `X-Content-Type-Options: nosniff` (asserted) |
| Permissions policy | microphone for self only, camera denied (asserted) |
| Body and message sizes | existing frozen limits; `test_the_same_frame_size_is_enforced`, `test_the_partial_turn_is_not_written_as_a_full_turn`; Phase 05 transport tests |
| HTTP and handshake rate limits per address | `security.py:34`, `main.py:186`, `router.py:120-124`; `test_the_window_refuses_after_the_limit_and_resets`; refused HTTP is 429, refused handshake 1008 |
| Worker caveat | `docs/operations/RUNBOOK.md` §3: counters are per process; two workers double the bound; no distributed limiter |
| Token and cookie handling | the token is only in the `start` envelope and `Authorization`; no query-string token (`security.spec.ts`); the Supabase SSR adapter copies the library's cookie options unchanged (`apps/web/src/lib/auth/server.ts:81-93`) and does not add or relax flags; the server verifies with `getClaims()`; no token is logged. In local `http` development `Secure` is necessarily off; production is `https`. |
| CORS / WS origin | one allowlist for both; `router.py` checks before `accept()`; `test_origins.py` and the assembled handshake |
| Production boundary | `settings.py:311` refuses loopback origins in production and a Supabase key with no URL; tests in `test_resilience_guards.py`; `next.config.ts:44` refuses a non-wss/loopback production voice URL |
| Dependency audit | `npm audit --omit=dev` = 0; full `npm audit` = W01 (5 high, unchanged, no patch); `npm ls --all` = 0 |
| Secret scan | 0 findings (`secret-scan.log`) |
| No tracked `.env` | only `.env.example` files (`tracked-env-files.log`) |
| New dependency | none added by Phase 07 |

## 9. Observability E

- Every completed turn records **end of turn → first coach audio byte** in a
  bounded registry (last 200 turns, nearest-rank p50/p95):
  `observability/latency.py:27-44`, called from `runtime.py:941-954`.
- `GET /health/latency` is **opt-in**: 404 unless
  `SPEAKING_COACH_HEALTH_TOKEN` is set; then it requires
  `Authorization: Bearer <token>` and returns only
  `{"turns","p50Ms","p95Ms"}` (`main.py:233`). Tests:
  `test_the_latency_endpoint_is_hidden_without_a_configured_token`,
  `test_the_latency_endpoint_needs_its_bearer_token`.
- The live harness is `tests/integration/live/test_latency.py`. It is skipped
  unless `GNANI_LIVE_TESTS=1`, `GNANI_API_KEY`, `GEMINI_API_KEY` and
  `GEMINI_MODEL` are all set; it runs 30 real turns and writes
  `live-latency.json`. **It was not run in Phase 07.**
- The fake-stack stop-time measurement is
  `evidence/interrupt-latency-20-trials.json`:

| Metric | Value |
| --- | --- |
| label | **fake stack; not the real target** |
| trials | 20 |
| p50 | 5.6 ms |
| p95 | 7.7 ms |
| max | 7.9 ms |

  The definition is "last coach audio byte read off the fake transport to the
  `status listening` that follows the interruption". It is not a provider,
  browser or network number. The test has only a 5,000 ms sanity ceiling, not
  a product target.

## 10. Operations F

`docs/operations/RUNBOOK.md` contains: how to run both processes; the config
table (names only); health and the latency endpoint's exposure/auth; the
resource caps and the multi-worker caveat; the failure table and what the
learner sees; storage/consent/delete; ownership; security headers and their
limitations; log-content rules; key rotation; the provider-retention sentence;
the test commands; the live harness; and an incident checklist.

**Provider retention sentence:** *Gnani keeps the raw transcript in its billing
records; our recording-retention toggle cannot waive that.* Our delete removes
our copy and our metrics, not the provider's billing record.

## 11. Limits (what is still fake-proven)

- No live Gnani STT/TTS call and no live Gemini call was made.
- No real microphone, speaker, browser microphone permission prompt or public
  network was used. The worklet, resampler, frame size and endpointing are
  real; the signal is an oscillator.
- No real Supabase project was contacted; the fake implements the same HTTP
  shapes the stores use.
- The interrupt stop time is the fake stack, labelled as such. The live
  harness exists but was not run.
- The assembled browser is Chromium only.
- The CSP keeps `'unsafe-inline'` (styles/hydration) and development
  `'unsafe-eval'`; a nonce-based CSP is out of scope and stated in the
  RUNBOOK.
- The caps and rate limits are per process; a multi-worker deployment
  multiplies them. There is no distributed limiter.
- `npm audit` still reports the W01 dev-only `braces` chain; no patch exists
  and suppression is forbidden by the waiver.
- C2 has no provider-side response schema; the local validation and facts-only
  fallback are the proof.
- C3's stray hoisted eslint copy remains; C5's routes intentionally stay out
  of OpenAPI.

PHASE 07 BUILT — AWAITING B3 TEST
