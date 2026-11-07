# Speaking Coach — operations runbook (Phase 07)

This runbook is for the person running the voice service and the web app, and
for the person reading what the Phase 07 tests actually prove. It states the
limits as plainly as the behaviour. Nothing here has been exercised against a
live provider, a real microphone or a real Supabase project: the assembled
suite uses doubles, and the live harness is opt-in.

## 1. What runs where

| Piece | Default local address | Notes |
| --- | --- | --- |
| Web (Next.js) | `http://localhost:3000` | `npm run dev:web` |
| Voice (FastAPI) | `http://127.0.0.1:8000` | `uv run --project services/voice uvicorn gnani_coach.main:app --port 8000` |
| Voice WebSocket | `ws://localhost:8000/ws/call` | the only URL the browser opens for a call |
| Voice HTTP | `http://localhost:8000` | history, consent, recordings |
| Supabase | configured project | identity and storage; never read by the browser bundle |

The browser origin allowlist (`SPEAKING_COACH_ALLOWED_ORIGINS`) is **one
list, two jobs**: the CORS allowlist for the HTTP routes and the handshake
allowlist for `/ws/call`. The default is the local web origin. `*` is refused
at parse time.

`NEXT_PUBLIC_VOICE_WS_URL` is inlined into the browser at build time. For a
built image it must be set when the image is built, not only when it starts.
The history/consent base URL is derived from it.

## 2. Health and latency

### `GET /health`

The existing liveness/readiness surface. It reports configuration
**readiness**, not live inference, and keeps
`liveCallingImplemented: false`; no code path in this phase opens a live
provider session.

### `GET /health/latency` (opt-in, protected)

Set `SPEAKING_COACH_HEALTH_TOKEN` to a non-empty value to mount it. Unset, the
route answers `404` (it is not advertised). When set, it requires
`Authorization: Bearer <token>` and answers only numbers:

```json
{"turns": 42, "p50Ms": 730, "p95Ms": 1180}
```

What the number means: **end of the learner's turn → the first coach audio
byte**, measured in this process. The window is the last 200 measured turns;
percentiles are nearest-rank. It contains no transcript, reply, session id or
user id, so it can be scraped without leaking learner content.

Limits that must be quoted with any number:

- **Per process.** A multi-worker deployment reports one worker's window.
  There is no shared aggregation.
- **It is a service-side number.** It includes the model and the first TTS
  chunk, but not a real browser, a real microphone or the public network.
- The fake-stack measurement recorded in
  `prompts/phase-07-resilience/evidence/interrupt-latency-20-trials.json` is
  labelled **"fake stack; not the real target"**. The live harness is the only
  thing that can produce a real number, and it is opt-in.

The Phase 05 lifecycle tests still own the 10-minute session cap and the idle
timeout; Phase 07 did not duplicate them.

## 3. Resource guards

All values are settings, so an operator can lower them without a code change.

| Setting | Default | Meaning |
| --- | --- | --- |
| `SPEAKING_COACH_MAX_CONNECTIONS_PER_ADDRESS` | 4 | live calls per source address |
| `SPEAKING_COACH_MAX_CONNECTIONS_PER_USER` | 2 | live calls per verified account |
| `SPEAKING_COACH_MAX_CONNECTIONS_PER_PROCESS` | 10 | live calls in one process |
| `SPEAKING_COACH_HTTP_REQUESTS_PER_MINUTE` | 120 | per-address HTTP budget |
| `SPEAKING_COACH_WS_HANDSHAKES_PER_MINUTE` | 120 | per-address handshake budget |

- The **address** and **handshake** checks happen before the socket is
  accepted; a refused handshake is closed with `1008` and never reaches the
  runtime. A refused HTTP request gets the frozen `rate_limited` error.
- The **user** check happens after the token is verified, because the user id
  is not known before then. The excess connection is accepted and then told
  the frozen error shape; it does not run a call.
- The counters are **per process**. Two workers double every bound. A
  distributed limiter needs shared state (Redis or the edge) and is outside
  this phase's dependency budget.

## 4. What a learner sees when a dependency fails

The product never shows a stack trace, a provider name, a status code or a
score. The server sends the frozen error shape; the web app renders a plain
title, the service's plain sentence and an advice line. The session ends (or
continues) as described.

| Failure | Behaviour | UI |
| --- | --- | --- |
| Gnani STT network / auth / throttle | the call **continues**; the failed turn is not counted; recognition reopens | "The speech service is having trouble." / that request was refused / too many requests |
| Gnani TTS fails mid-sentence | the call **continues**; the learner may speak again | "The speech service is having trouble." |
| Gemini timeout | the call **continues** | "That took too long." |
| Gemini malformed feedback JSON | facts-only fallback: empty strengths/improvements/notes, measured evidence retained; filler stays `insufficient_evidence` | normal feedback, nothing invented |
| Supabase Auth down at call start | the token cannot be confirmed; the call **continues as a guest**, nothing is written; the `ready` status carries `notice:` | a visible call notice: "Your sign-in could not be confirmed…" |
| Supabase REST down at end | metrics cannot be written; the call ends normally | summary notice: "This session was not saved…" |
| Supabase Storage down at end | metrics are written; the audio is not; the audio failure has its own sentence | summary notice: "The recording could not be saved, so this session has no audio. Your practice metrics were saved." |
| socket drops | the client reconnects; the server keeps the session it has; a turn is not duplicated | "Reconnecting…" then "Listening" |
| microphone unplugged | the call is released and cannot continue | "Your microphone was disconnected…" |
| tab closed | the server persists the session on disconnect | (no UI; History shows it) |
| signed out | the live call socket is closed | the sign-in screen |
| double Start | exactly one call socket | normal |
| expired token during a call | the token was verified once at start; expiry does not move or drop the session | normal |
| per-address/per-user cap | refused before or at acceptance with the frozen shape | plain rate/limit message |

Messages are bounded (200 characters for the status `detail`) and the
`notice:` prefix keeps a learner-facing notice distinct from an ordinary
status detail. On a narrow screen the notice is rendered in the call and in
the summary.

## 5. Storage, consent and deletion

- A **guest writes nothing**. No session row, no object, no log content.
- An **authenticated** call writes metrics to `session_metrics`; the audio is
  written only when `recordingRetention` is on **and** consent is still
  granted **at write time**.
- Withdrawing consent between Start and End stops the write. The metrics are
  still saved; the recording is not; this is intentional, not an error.
- A recording is WAV (RIFF/WAVE), mono, 16 kHz, and is parsed with Python's
  `wave` in the tests before it is offered to the browser. History uses
  `preload="metadata"`; the assembled test waits for `readyState >= 2` and a
  duration greater than zero.
- Delete is two-step in the UI ("Delete the recording" → "Yes, delete it") and
  a `DELETE` on the route; a second `GET` of the same id is `404`.

### Ownership

The bearer token is the only credential; there are no cookies on the voice
service. Ownership comes from the verified token, never from a request field.
Another user's id, a missing id and a forged `user_id` all produce the **same**
`404`; the delete path uses the same rule. The assembled A7 test asserts this
shape, not just the status code.

## 6. Security headers and the browser

`apps/web/next.config.ts` sets the headers on every response:

- `Content-Security-Policy` with `default-src 'self'`, `object-src 'none'`,
  `base-uri 'self'`, `frame-ancestors 'none'`, `worker-src 'self' blob:`
  (the capture AudioWorklet) and a `connect-src` for the voice HTTP/WS
  origins and the Supabase project.
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy` allowing the microphone for self only and denying the
  camera, `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy`.

Known limitations, stated rather than hidden:

- The CSP keeps `'unsafe-inline'` for the styles and the hydration bootstrap.
  A nonce-based CSP needs a middleware nonce on every render and is out of
  scope for this phase.
- `'unsafe-eval'` is present **only in development** (bundler eval source maps
  and React Refresh).
- A production start refuses a loopback browser origin and refuses a Supabase
  key with no `SUPABASE_URL`, so the two most common "it worked locally"
  mistakes fail at startup instead of silently degrading.

Secrets: the access token travels only in the `start` envelope and the
`Authorization` header; never in a query string or a log line. The service
logs ids, counts, durations and failure categories, never transcript text,
reply text or a custom topic. The A8 test scans the assembled service log and
the project's temporary/cache directories for the sentinels.

## 7. Running the tests

```sh
# foundation / contracts
npm run test:contracts

# the voice service's own suite
uv run --project services/voice python -m pytest services/voice/tests -q

# existing integration (Python service tests + the two Playwright configs)
npm run test:integration
npm run test:e2e

# the Phase 07 assembled suite: A1–A8, F1–F10, security headers
npm run test:assembled
```

The assembled suite starts a fake Supabase HTTP service, the **real** FastAPI
app with its real lifespan, the **real** Next.js dev server and Chromium. The
only fakes are the speech/reasoning/analysis provider ports, the microphone
(an oscillator behind the real worklet) and Supabase. It is deliberately
single-worker: the tests share one fake database and reset it per test.

### The live harness (opt-in, billable)

`tests/integration/live/test_latency.py` is skipped by default. To run it, a
person with credentials must set all four values:

```sh
GNANI_LIVE_TESTS=1 GNANI_API_KEY=... GEMINI_API_KEY=... GEMINI_MODEL=... \
  uv run --project services/voice python -m pytest tests/integration/live -q -s
```

It drives 30 turns through the real runtime and prints/writes the
end-of-turn → first-audio percentiles. The "learner" audio is synthesised by
the live TTS and replayed as frames, so the number is not a real microphone or
browser measurement. Phase 08 and the final test can run it; Phase 07 never
did.

## 8. Incident checklist

1. **Everyone is told "not signed in" but the web page shows signed in.**
   Check the voice service's `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` and
   the fake/real issuer. The service verifies the token against the exact
   issuer; a mismatch is a guest, not an error.
2. **Calls end immediately at the handshake.**
   Check `SPEAKING_COACH_ALLOWED_ORIGINS`; the browser origin must match
   exactly (scheme, host, port). Check the per-address cap and the handshake
   budget for the proxy's source address.
3. **Every call says "not saved".**
   This is the REST/storage path, not the microphone. Check the Supabase URL,
   the service-role key and the table/object policies. The call itself ended
   normally; the learner was told the truth.
4. **Recordings are missing but metrics are present.**
   Read the summary notice: the recording message means consent was granted
   but Storage failed. Metrics are still in History.
5. **A learner reports hearing the coach after interrupting.**
   The service fences the turn and the browser stops the player. The assembled
   A5 test asserts that late reply/audio never reaches the page and writes the
   fake-stack stop-time evidence; a live recurrence needs the live harness,
   not the fake number.
6. **Latency endpoint returns 404.**
   `SPEAKING_COACH_HEALTH_TOKEN` is unset. Set it, restart, and send
   `Authorization: Bearer <token>`.
7. **Latency looks too good or too bad.**
   Check the worker count and the window caveat above; one worker's last 200
   turns is not a fleet metric.

## 9. Log content, key rotation and provider retention

### Log content

The service logs **ids, counts, durations and error categories only**. It must
never log a transcript, a coach reply, a custom topic, an access token or a
cookie. The A8 test scans the assembled service log and the project's
temporary/cache directories for the transcript, reply and topic sentinels and
finds none. If a new log line is added, the rule is: a number, an id or a
category; never the learner's words. The root logger is DEBUG in the assembled
launcher so the tests can catch a mistake; production should run at INFO.

### Key rotation

1. Rotate the key in the provider's console: Gnani (`GNANI_API_KEY`), Google
   (`GEMINI_API_KEY`), Supabase service role and publishable keys, and the
   latency token (`SPEAKING_COACH_HEALTH_TOKEN`).
2. Update the process environment or the secret manager. Never write a value
   into the repository, an `.env.example`, a log, a screenshot or a prompt.
3. Restart the voice service so every worker reads the new value, then run
   `GET /health` and one short call. A stale worker keeps the old key until it
   restarts.
4. Remove the old key at the provider once the new one is confirmed. Rotate
   the Supabase keys in the dashboard and redeploy the web app; the browser
   only reads the server-side session route, never a key.
5. If a key was ever exposed, a clean secret scan does not erase the exposure:
   rotate first, then record what was exposed and where.

### Provider retention

**Gnani keeps the raw transcript in its billing records; the
recording-retention toggle cannot waive that.** The toggle controls *our*
stored audio and metrics, not the speech provider's own records. The same
caveat applies to the reasoning provider's handling under its terms. Say this
to a learner who asks for deletion; our History delete removes our copy, not
the provider's billing record.

## 10. What is still fake-proven

- No live Gnani STT/TTS call and no live Gemini call was made in Phase 07.
- No real microphone or speaker was used; the worklet, resampler, frame size
  and endpointing are real, the signal is an oscillator.
- No real Supabase project was contacted; the fake speaks the same HTTP
  shapes the stores use.
- The interrupt stop time is the fake stack, labelled as such.
- The CSP is compatibility-tested in Chromium, not audited against every
  browser; the nonce limitation above stands.

The repository was uncommitted at the start of Phase 07 and remains
uncommitted. The start state is recorded in
`prompts/phase-07-resilience/evidence/start-manifest.sha256`.
