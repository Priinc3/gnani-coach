# The integration seam test

Phase 03 built this suite to prove the **frozen seams** work, not to
prove the product. Batch B2 extends it with the real call, the real
history and the real recording lifecycle.

```sh
# from the repository root
npm run test:integration
```

That runs two halves:

| Half | Command | What it does |
|---|---|---|
| The service seams | `npm run test:integration:service` → `uv run --project services/voice python -m pytest tests/integration -v` | Boots the FastAPI application in-process and checks every mounted seam against its stated unavailable behaviour. |
| The browser seams | `npm run test:integration:web` → `playwright test --config=playwright.integration.config.ts` | Boots the **real** web app and the **real** uvicorn service (Playwright's `webServer`), then checks the home page, `/health`, the history seam and the call socket from outside the process. |

## What it checks today

* `GET /health` works, leaks no configuration, and is still the only
  documented route in the OpenAPI document.
* `GET /api/history`, `POST /api/consent` and
  `GET/DELETE /api/recordings/{id}` answer a guest with `401` and the
  frozen error shape (`code: unauthenticated`,
  `category: unauthenticated`, `retryable: false`). A guest
  `DELETE /api/recordings/x` is refused the same way, and no recording
  route ever returns audio to a guest.
* The call socket's first message is `status` with `state: "connecting"`;
  an invalid `start` closes it with **1008**, and a wrong sample rate
  answers `unsupported_audio_format`.
* The identity port is the anonymous guest; the analysis port measures
  `turn.duration_ms`, makes a missing transcription's rates
  `unavailable` with reason `stt_unavailable` (never `0`), and keeps
  `filler.count` at `insufficient_evidence` with
  `filler_detection_unvalidated` and a null value.
* The Phase 02 provider adapters satisfy the frozen ports, and no
  provider module depends on the port package (so no provider file had to
  be edited).
* Readiness is `unconfigured` / `configured`, never `live` from
  presence, and the speech and reasoning views never mention Supabase.
* The filler capability is `unvalidated` and renders as
  `insufficient_evidence`; no catalog capability flag is true.
* **The origin allowlist (Phase 03 FIX-1).** The default allowlist is the
  local web origin only; the wildcard `*` and a malformed entry are
  refused while the settings parse; an allowlisted origin passes the CORS
  preflight and opens the call socket; a foreign origin
  (`https://evil.example`) fails both — the preflight answers `400` and
  the handshake is refused with close `1008`; a **missing** `Origin`
  header identifies a non-browser client and is allowed.
* **The browser-visible voice URL (Phase 03 FIX-1).**
  `NEXT_PUBLIC_VOICE_WS_URL` is the only `NEXT_PUBLIC_` value in the
  repository, no secret uses the prefix, and the development default is
  `ws://localhost:8000/ws/call`.

## What B2 adds

The assembled browser + voice + identity/storage system: an authenticated
call with recording OFF and ON, an interrupted coach turn, a four-turn
coaching round, a retry comparison, and an unauthorised access attempt.
