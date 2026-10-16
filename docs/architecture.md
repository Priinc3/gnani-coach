# Architecture — what exists, what does not (Phase 01)

Status context: this documents the **foundation build** only. Live speech
providers, analysis engines, identity and storage are deliberately absent.
Every absence below is a decision, not an oversight.

## Component map

```
apps/web                    Next.js 16 App Router starter screen (the only UI)
  └─ reads packages/contracts/data/catalog.json (ten languages, scenarios, levels)

packages/contracts          Draft v0.1 JSON Schema 2020-12 contracts
  ├─ schemas/*.schema.json  (7 schemas)
  ├─ data/catalog.json      (language/scenario catalog; the shared source of truth)
  ├─ examples/<schema>/{valid,invalid}/*.json  (36 fixtures)
  └─ scripts/test-…         Ajv runner (npm run test:contracts)
       ↑ same files consumed by Python jsonschema in services/voice tests

services/voice              FastAPI skeleton
  ├─ main.py                GET /health only; lifespan parses settings once
  └─ settings.py            the configuration boundary (SecretStr, env prefixes,
                            provider_readiness() — always unavailable)

tests/foundation            Playwright e2e for the starter screen (12 tests)
scripts/foundation          service health check, screenshot capture
```

Data flow **today**: browser renders from the catalog JSON at build time;
nothing calls the network except the developer running the service by hand.
The web app does not yet talk to `services/voice`; that seam is for a later
phase after the transport contract is frozen.

## What is real in this phase

1. **The starter screen** — setup form, honest status copy, ten-language list
   with "Not yet verified" badges, disabled start action with a plain reason,
   optional labeled sample preview. No microphone access, no fake data.
2. **The contracts** — seven draft 2020-12 schemas plus the catalog, enforced
   identically by Ajv (strict, `allowUnionTypes`, ajv-formats) and Python
   `Draft202012Validator` + `FormatChecker`, with a shared fixture inventory.
3. **The service skeleton** — `GET /health` proves process readiness only.
   Unimplemented routes do not exist: probes of `/stt`, `/tts`, `/ws`,
   `/api`, `/session` return 404 (fail closed).
4. **The configuration boundary** — `GNANI_*`, `GEMINI_*`, `SUPABASE_*` and
   `SPEAKING_COACH_*` env prefixes, `SecretStr` for every secret,
   optional everything. Missing credentials never crash startup; present
   credentials never get reported as "live".

## Contract boundaries worth restating

- **Transient vs durable.** Transcripts, quoted mistakes, model prose and
  audio references are rejected by name in the durable metrics shape
  (`transcript`, `quotedMistakes`, `modelText`, `audioUrl`, `embedding`).
  They may exist only inside transient envelopes.
- **Zero is not "unmeasurable".** `status: available` with `value: 0` is a
  real measured zero (e.g. zero fillers). `unavailable` and
  `insufficient_evidence` must carry `null` — never a fabricated number.
- **No word timings.** The reviewed Gnani realtime STT documentation provides
  emission timestamps and audio duration only — not word-level alignment.
  The contracts therefore contain **no word-timing field to fill by
  inference**, and `sampleTimeMs` must come from the learner-audio sample
  clock, never from server timestamps.
- **Stale identifiers are runtime checks.** `ses_`/`con_`/`rnd_`/`trn_`/
  `rec_`/`usr_`/`cor_` prefixes and shapes are schema-checked; whether an
  identifier belongs to a *current* session/connection is identity logic for
  a later phase.
- **Consent is audio-only.** Recording retention consent never implies
  permission to durably keep transcripts or notes.
- **No public audio URLs.** Recording metadata carries a private opaque
  reference; deletion is a state with a `deletedAt` timestamp, not an
  erasure of the record.

## Explicitly missing / unknown

| Area | Status |
|---|---|
| STT/TTS/LLM adapters | None. Phase 02 probes providers; Phase 03 freezes the seam. |
| WebSocket transport | The event envelope schema exists; the transport, authentication, origin checks, rate limits and backpressure are unimplemented. OWASP WebSocket cheat sheet is the standing reference. |
| Word-level alignment | Not obtainable from reviewed provider docs; not synthesized anywhere. |
| Disfluency algorithm | Not chosen in Phase 01 (deliberate). |
| Analysis measurements | Schema only. No metric has ever been produced. |
| Identity / accounts | None. `usr_` references exist as schema shapes. |
| Storage | None. Supabase settings are a parsed-but-unused boundary. |
| Retention/deletion mechanics | Metadata shape only; no storage, no deletion job. |
| All-ten language support | Catalog lists ten documented languages; every capability state except `documented` is `false`. Hinglish is a separate code-mixed mode, also untested. |
| Recording capture format | Drafted as wav/pcm_s16le for the stored profile; the real capture format is unresolved until Phase 02 probes. |
| Coaching-language pairs | UI allows choosing any pair; no pair has been validated. |
| Deployment | None. Local only, no remote, no CI. |

## Security posture in this phase

- No secrets in the repository; sanitized `.env.example` files only.
- Provider keys are server-side variables with dedicated prefixes; the
  browser must never receive them (documented in `apps/web/.env.example`).
- No open relay: there are no WebSocket or streaming endpoints at all.
- No persistent session content: the service stores nothing.
- The health response contains no configuration values (asserted by tests).
