# B4 TEST-RESULT — live smoke (Phase 13)

Date: 2026-11-07. Box: the EC2 voice host (2 GB RAM). All checks below ran
against the public URLs, not against an in-process test client.

## URLs

| Piece | URL |
| --- | --- |
| Web app | https://gnani-coach.vercel.app |
| Voice health | https://13-205-26-178.sslip.io/health |
| Voice socket | wss://13-205-26-178.sslip.io/ws/call |
| APK | **not published** — GitHub Actions did not run (see below) |

## Raw outputs

| File | What it is |
| --- | --- |
| `prompts/phase-13-live-smoke/evidence/check_deploy.txt` | full `check_deploy.py` run |
| `prompts/phase-13-live-smoke/evidence/call_once.txt` | full `call_once.py` run |
| `prompts/phase-13-live-smoke/evidence/bundle-secret-scan.txt` | JS bundle marker scan |
| `prompts/phase-13-live-smoke/evidence/web-headers.txt` | web response headers (CSP) |
| `prompts/phase-13-live-smoke/evidence/health.json` | voice `/health` body |
| `prompts/phase-13-live-smoke/evidence/manifest.json` | web app manifest |
| `prompts/phase-13-live-smoke/evidence/vercel-project.json` | Vercel project settings |
| `prompts/phase-13-live-smoke/evidence/vercel-deployment.json` | Vercel production deployment |
| `prompts/phase-13-live-smoke/evidence/apk-workflow.txt` | APK workflow run state and cancel attempt |

## Pass/fail

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| S1 | TLS certificate valid | **PASS** — Let's Encrypt, `13-205-26-178.sslip.io`, expires 2027-02-05 | `check_deploy.txt` |
| S2 | `/health` 200 | **PASS** — HTTP 200, `status:ok` | `check_deploy.txt`, `health.json` |
| S3 | WS accepted from the Vercel origin | **PASS** — accepted, `status` envelope received | `check_deploy.txt` |
| S4 | WS refused from `https://evil.example` | **PASS** — HTTP 403 before accept | `check_deploy.txt` |
| S5 | Web `/` 200 and CSP `connect-src` has the wss origin | **PASS** | `check_deploy.txt`, `web-headers.txt` |
| S6 | `/manifest.webmanifest` 200, `display: standalone` | **PASS** | `check_deploy.txt`, `manifest.json` |
| S7 | `/health/latency` 404 without a token | **PASS** — HTTP 404 | `check_deploy.txt` |
| S8 | APK served with matching size/sha256 | **SKIP** — not published (blocked, see below) | `check_deploy.txt`, `apk-workflow.txt` |
| S9 | Unit trusts proxy headers only from `127.0.0.1` | **PASS** — `--proxy-headers --forwarded-allow-ips 127.0.0.1` | `check_deploy.txt` |
| A1 | Account register | **PASS** — HTTP 201 | `check_deploy.txt` |
| A2 | Account login | **PASS** — HTTP 200 | `check_deploy.txt` |
| A3 | `GET /api/auth/me` | **PASS** — HTTP 200, opaque userId | `check_deploy.txt` |
| A4 | Wrong password gets the generic error | **PASS** — HTTP 401, `That email or password is not correct.` | `check_deploy.txt` |
| A5 | User B cannot read user A's history | **PASS** — B's history is empty; A's `userId` query is ignored | `check_deploy.txt` |
| A6 | Account delete | **PASS** — HTTP 204 | `check_deploy.txt` |
| L1 | Per-address login limiter | **PASS** — 10 × 401 then 429 on the 11th | `check_deploy.txt` |
| L2 | Client address reaches the app | **PASS** — 1 distinct peer host in the access log, none loopback | `check_deploy.txt` |
| H | One real turn, synthetic English speech, guest, recording OFF | **PASS** — `transcript_final` and `coach_text` received; first coach audio received | `call_once.txt` |
| E1 | 3 s of digital silence | **PASS** — no coach turn, no fake score, no error, socket healthy | `call_once.txt` |
| E2 | Socket dropped mid-turn, then a clean second call | **PASS** — second call got `coach_text` and first audio | `call_once.txt` |
| X | Vercel origin serves browser and APK WebView; CSP has the wss origin | **PASS for the browser**; APK part **unproven** (no APK) | `check_deploy.txt` |
| Z | No secret marker in the web JS bundle | **PASS** — 0 hits for `GNANI_API_KEY`, `GEMINI_API_KEY`, `AQ.`, `GEMINI_MODEL`, `SPEAKING_COACH_` across 684 KB of JS | `bundle-secret-scan.txt` |

## Latency (labelled)

`call_once.py` measures **end of the learner's synthetic speech audio →
first coach audio byte**, over the public internet, including the
provider calls and the 1.28 s trailing-silence/hold window:

| Run | Latency |
| --- | --- |
| H (final run, after the last restart) | **11,997 ms** |
| E2 (final run, clean second call) | **16,363 ms** |

An earlier run of the same script measured 9,698 ms and 9,753 ms, so the
observed range is roughly **9.7–16.4 s**. The variance is provider/queue
time, not a changed code path. This is **not** a product target and not a
browser/microphone number. It includes the fixed end-of-turn hold, the
recogniser's trailing silence, the model and the first TTS chunk. The
voice service's own `/health/latency` window is not exposed because no
health token is set (it correctly returns 404).

## Small model and key

`GEMINI_MODEL=gemini-3.5-flash-lite` answered a real reasoning request
(reply length 106; model id echoed `gemini-3.5-flash-lite`). It accepted
the adapter's `thinking_level=low`. The Gemini key is an auth key
(`AQ.` prefix) and the pinned SDK accepted it without a change. The
published model page (now served at
<https://aistudio.google.com/docs/models>, redirected from
<https://ai.google.dev/gemini-api/docs/models>) lists both
`gemini-3.5-flash-lite` and `gemini-3.8-flash`; no fallback was needed.

## What remains unproven

- Real phone microphone audio, real speakers, real background noise.
- The Android APK and its WebView microphone path (no APK built).
- Other browsers (Firefox, Safari) and iOS.
- The other nine languages; only English was exercised.
- Filler/hesitation detection and any coaching-quality claim.
- Load, multiple concurrent calls, and the per-process nature of the
  limits (one worker).
- The literal phrase "not enough speech" is only produced in
  `round_feedback` after a completed round; a single 3 s silent turn
  produces no coach turn and no fake score (recorded as E1, not as a
  message).
- A real user's address was not printed; only the count of distinct
  peer hosts (1, none loopback) is recorded.

## APK status

**BLOCKED: GitHub Actions not running (billing).** The stale run
`42357747364` stayed `queued` with zero jobs for 2 h 22 m and cannot be
cancelled (`409 Cannot cancel a workflow re-run that has not yet
queued`). One dispatch with the real `APP_URL` (`42367877759`) ended in
`startup_failure` after 1 s with zero jobs. Actions is enabled for the
repo; the failure is at the account/runner level, which this token cannot
read. The phone fallback is the installed web app (PWA) from Chrome.
