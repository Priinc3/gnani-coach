# Phase 13 — live-ship — REPORT

**State: BUILT.** The web app is live on Vercel, the voice service is
live and now answers a real provider turn, and the account and limiter
checks pass. **The APK is BLOCKED: GitHub Actions not running (billing).**
The phone fallback is the installed web app (PWA) from Chrome.

## URLs

| Piece | URL |
| --- | --- |
| Web app (production alias) | **https://gnani-coach.vercel.app** |
| Vercel deployment | https://gnani-coach-pxlk5yfc5-0-prince-0s-projects.vercel.app (deployment `dpl_AmJ2eSSgL66wt4temtbuN4gsf6KW`) |
| Voice health | **https://13-205-26-178.sslip.io/health** |
| Voice socket | wss://13-205-26-178.sslip.io/ws/call |
| APK | **not published** — `/apk/speaking-coach.apk` returns 404 |

## Files

| Path | Purpose |
| --- | --- |
| `tests/smoke/check_deploy.py` | public-endpoint smoke: TLS, health, origin allowlist, CSP, manifest, latency 404, APK, unit flags, accounts, limiter, client address |
| `tests/smoke/call_once.py` | three live scenarios: one real turn, 3 s silence, drop + clean second call |
| `tests/smoke/PHONE-CHECKLIST.md` | 13-line phone checklist for the user |
| `tests/smoke/RESULT.md` | the B4 TEST-RESULT |
| `prompts/phase-13-live-smoke/evidence/**` | raw outputs (see RESULT.md) |
| `services/voice/src/gnani_coach/providers/stt.py` | 🔴 D1 minimal fix (lazy connect) |
| `services/voice/src/gnani_coach/providers/tts.py` | 🔴 D1 minimal fix (lazy connect) |
| `services/voice/src/gnani_coach/ports/provider_adapters.py` | 🔴 D2 minimal fix (sample-clock milliseconds) |

## Privileged actions

1. **Vercel project** `gnani-coach` (team `0-prince-0s-projects`) created
   and linked from the repo root. Settings set with
   `vercel project update gnani-coach --root-directory apps/web
   --framework nextjs --node-version 24.x`: Root Directory `apps/web`,
   framework `nextjs`, Node `24.x`. The first `vercel link` wrote a
   `vercel.json` with a "services" config and a `.env.local`; both were
   removed/unlinked from git (`.env.local` is git-ignored), and the
   project was reset to a plain Next.js project.
2. **Vercel env (Production only, values via stdin):**
   `NEXT_PUBLIC_VOICE_WS_URL=wss://13-205-26-178.sslip.io/ws/call`,
   `SPEAKING_COACH_ENVIRONMENT=production`. No secret value was printed.
3. **Vercel production deploy** from the repo root
   (`vercel deploy --prod --yes`), remote build. Deployment
   `dpl_AmJ2eSSgL66wt4temtbuN4gsf6KW` reached `READY`; alias
   `https://gnani-coach.vercel.app`. **Deployment protection was not
   changed**: the public URL returned HTTP 200 without authentication.
4. **Voice env** `/etc/gnani-coach/voice.env`: replaced only
   `SPEAKING_COACH_ALLOWED_ORIGINS` with
   `https://gnani-coach.vercel.app`; `sudo systemctl restart
   gnani-voice`. The APK WebView loads the same Vercel URL, so the
   origin is the same (verified from the Capacitor config: `server.url`
   comes from `APP_URL`, now the Vercel URL).
5. **GitHub**: `gh variable set APP_URL --body
   https://gnani-coach.vercel.app`; one dispatch
   `gh workflow run android-apk.yml -f app_url=...` (run
   `42367877759`). Attempted to cancel the stale run `42357747364`; the
   API answered `409 Cannot cancel a workflow re-run that has not yet
   queued`. No retry.
6. **No AWS change.** No process not started by this phase was stopped.

## Commands and evidence

| Command | Evidence |
| --- | --- |
| `services/voice/.venv/bin/python tests/smoke/check_deploy.py` | `evidence/check_deploy.txt` (16 PASS, 0 FAIL, 1 SKIP) |
| `services/voice/.venv/bin/python tests/smoke/call_once.py` | `evidence/call_once.txt` (3 PASS) |
| bundle marker scan | `evidence/bundle-secret-scan.txt` (0 secret markers) |
| `vercel project inspect gnani-coach --json` | `evidence/vercel-project.json` |
| `vercel inspect gnani-coach.vercel.app --json` | `evidence/vercel-deployment.json` |
| `gh api .../actions/runs/{id}` | `evidence/apk-workflow.txt` |
| web headers / manifest / health | `evidence/web-headers.txt`, `manifest.json`, `health.json` |

## App-code edits (successor right, each minimal)

### 🔴 D1 — live STT and TTS sessions were never connected

The port wrappers `open_session()` return a session and the runtime calls
`stream_pcm()` / `synthesize()` directly, without entering the async
context. Both provider classes checked `self._transport is None` and
raised `CancelledError("session is closed")`. A live call could never
reach either provider. This blocks the phase goal, so it could not wait.

- `services/voice/src/gnani_coach/providers/stt.py:557-563`
  - before: `if self._transport is None or self._closed: raise CancelledError(...)`
  - after: raise only when `_closed`; if `_transport is None`, `await self._connect()`
- `services/voice/src/gnani_coach/providers/tts.py:522-528`
  - before: `if self._transport is None or self._closed: raise CancelledError(...)`
  - after: raise only when `_closed`; if `_transport is None`, `await self._connect()`

Why it could not wait: with this bug, every live turn failed before the
first provider frame; the whole B4 happy path was unreachable.

### 🔴 D2 — the STT adapter read milliseconds that `SampleClock` does not have

`SampleClock` exposes `genuine_seconds`/`submitted_seconds`/`padding_seconds`
and a `summary()` dict with `*_ms`; the adapter read `clock.genuine_ms`
etc. and raised `AttributeError` on the first successful live transcript.

- `services/voice/src/gnani_coach/ports/provider_adapters.py:55-66`
  - before: `genuine_ms=clock.genuine_ms`, `submitted_ms=clock.submitted_ms`, `padding_ms=clock.padding_ms`
  - after: `summary = clock.summary()` and read `summary["genuine_ms"]`, etc.

Why it could not wait: the first live STT result crashed the turn before
the coach could reply.

No `apps/web/**` edit was needed. No `deploy/**`, `apps/mobile/**` or
`.github/**` edit was made.

## Small model + key check

- `GEMINI_MODEL=gemini-3.5-flash-lite` answered a real request; the model
  id echoed back was `gemini-3.5-flash-lite`.
- `thinking_level=low` was accepted (no 🟠).
- The key is an auth key (`AQ.` prefix); the pinned SDK accepted it (no
  🟠). Checked against
  <https://ai.google.dev/gemini-api/docs/models> (redirects to
  <https://aistudio.google.com/docs/models>; both `gemini-3.5-flash-lite`
  and `gemini-3.8-flash` are listed).
- No fallback to `gemini-3.8-flash` was needed.

## Defects by severity

| Severity | Defect | Status |
| --- | --- | --- |
| 🔴 | D1: STT/TTS sessions never connected; every live turn failed | fixed (two files) |
| 🔴 | D2: STT adapter read non-existent `SampleClock` ms attributes | fixed (one file) |
| 🟠 | APK not built: GitHub Actions `startup_failure` with zero jobs, stale run queued 2 h 22 m; Actions is enabled but the account/runner/billing layer is not readable with this token | **BLOCKED**, not retried; PWA fallback documented |
| 🟡 | `/health` still says `phase:foundation`, `liveCallingImplemented:false`; the BUILD says this is stale hard-coded text, and calling is proven by `call_once.py` | not fixed (not in the minimal-fix scope) |
| 🟡 | A single 3 s silent turn produces no explicit "not enough speech" message; the literal sentence exists only in round feedback | observed, not fixed (no crash, no fake score) |
| 🟡 | A normal client disconnect during the "ended" status logs a handled `WebSocketDisconnect` traceback before the `error envelope could not be sent` notice; the service stays healthy and the next call works | observed, not fixed (log noise only) |
| 🟡 | The synthetic spoken fixture `fixtures/synthetic/audio/spoken-smoke.wav` is git-ignored (`*.wav`), so a fresh clone must regenerate it with the live TTS provider | documented in `call_once.py` |

## What the user must do

1. **Phone check:** follow `tests/smoke/PHONE-CHECKLIST.md` on
   https://gnani-coach.vercel.app (about 10 minutes). Send screenshots and
   local times for anything that fails; never send keys or passwords.
2. **APK:** the only blocker is GitHub Actions. Either fix billing
   (https://github.com/settings/billing → payment method or spending
   limit) and ask for one dispatch, or use the installed web app (PWA).
   I will not make the repo public or change billing.
3. **Rotate both provider keys after the contest (2026-11-10).**
4. If the APK is built later: download the artifact, copy it to
   `/var/www/gnani-apk/speaking-coach.apk` (0644), record its sha256, and
   re-run `check_deploy.py --apk-sha256 <hex> --apk-size <bytes>`.

## Commit hashes

- Phase 13 build: `19be981`
- Report hash: `<pending>`

PHASE 13 BUILT — AWAITING B4 VERDICT
