# Starter stack decisions — 2026-10-16

Status: selected planning baseline; not installed or tested by the orchestrator. Exact release pins must be verified and recorded by Phase 01; live model access by Phase 02. These decisions follow web searches, not assumed API recollections.

Review update (2026-10-18): FIX-1's inspected files and builder evidence support the corrected Node 24.22.0 LTS baseline, npm 11.19.1, closed durable provenance and metric-domain constraints. `phase-01-foundation/VERIFY.md` accepts those scoped corrections but does not declare batch verification. The braces development advisory and EOL ESLint 9 have separate short-lived dispositions in `waivers.md`, expiring at Phase 03 freeze or 2026-10-25. User-selected visual reference remains `UI.png`, detailed in `phase-04-call-ui/UI-REFERENCE.md`; it does not change this technology selection.

## Selected components

| Area | Decision | Primary source and rationale |
|---|---|---|
| Web | Next.js App Router + TypeScript, npm workspace at `apps/web`; ordinary CSS variables/modules initially | [Next installation](https://nextjs.org/docs/app/getting-started/installation) documents TypeScript and dev/build/start/lint commands. A familiar web structure for onboarding, call view and account history; no native app initially. |
| Runtime/tooling | Supported Node LTS with exact patch recorded; npm root lock; Python version compatible with selected stable packages, managed with uv | [Node releases](https://nodejs.org/en/about/previous-releases), [npm workspaces](https://docs.npmjs.com/cli/v7/using-npm/workspaces/), [uv projects](https://docs.astral.sh/uv/guides/projects/). The searched npm page is older: Phase 01 must verify syntax against installed npm before documenting commands. No global tool upgrade required without user approval. |
| Voice backend | FastAPI in one long-lived Python service, `services/voice`; do not put the live audio loop in a short-lived web route | [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) and [Gnani realtime STT](https://docs.gnani.ai/api/STT/stt-websocket). Python keeps audio processing near the speech adapters; one service avoids an unnecessary broker/microservice fleet. Deployment hosting remains a later decision. |
| Browser audio | AudioWorklet-based capture/playback where supported, with a browser capability check | [MDN AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet). Gnani requires paced PCM, not MediaRecorder containers. Actual capture rates and browser behavior must be measured. Never claim raw/unprocessed acoustic measurements if browser processing altered the signal. |
| STT/TTS | Gnani realtime Prisma and Timbre. Start validation with documented v2.5-compatible voices; v3.0 only after access/capability evidence | [STT](https://docs.gnani.ai/api/STT/stt-websocket), [TTS](https://docs.gnani.ai/api/TTS/tts-websocket), [voice catalog](https://docs.gnani.ai/api/TTS/available-voices). Keep credentials behind the backend. Validate streaming format and cancellation; no undocumented stop frame. |
| External reasoning | Gemini first, behind one provider interface; no hardcoded unverified model ID | [Audio understanding](https://ai.google.dev/gemini-api/docs/audio), [structured output](https://ai.google.dev/gemini-api/docs/structured-output). One provider can serve conversation/coaching and optional audio review. This is a scope choice, not a superiority claim. Groq is an alternative if evaluation justifies changing. |
| Audio measurements | Silero VAD for estimated speech intervals; separate verified disfluency/alignment approach must be established in Phase 02 | [Silero repository](https://github.com/snakers4/silero-vad), [forced alignment guide](https://montreal-forced-aligner.readthedocs.io/en/latest/user_guide/index.html). Do not present VAD as word recognition or force-alignment as missing-filler recovery. Exact audio runtime and licenses must be checked before install. |
| Identity and saved data | Supabase Auth + Postgres metrics + private Storage recordings | [SSR auth](https://supabase.com/docs/guides/auth/server-side/creating-a-client), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [private buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals). Policy enforcement is implementation work, not automatically achieved by choosing Supabase. Phase 01 only scaffolds boundaries; do not provision a project. |
| Shared contracts | Authoritative JSON Schema draft 2020-12 files in `packages/contracts`; Ajv for TypeScript boundary validation and Python `jsonschema` for matching validation | [Ajv schema versions](https://ajv.js.org/json-schema.html), [Python schema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/). Both consume the same schema and positive/negative examples. Use explicit draft support and local references; do not rely on implicit defaults or remote schema fetches. |
| Automated acceptance | Playwright for browser/cross-service flows; pytest for backend; shared validator fixtures for contracts | [Playwright installation](https://playwright.dev/docs/intro), [pytest guides](https://docs.pytest.org/en/stable/how-to/index.html). Formal acceptance is batched after three phases/one parallel group, not replaced by per-phase screenshots. |

## Version policy

1. Use supported stable releases, not guessed future versions, prereleases, or an unpinned `latest` in committed manifests.
2. Phase 01 opens the relevant current installation/release pages, resolves a compatible toolchain, and records versions, URLs and date in `docs/toolchain.md` and REPORT. It must verify Python/audio compatibility rather than assume it from this plan.
3. Commit reproducible npm and uv lockfiles. Generated framework files are allowed within Phase 01's allowlist; do not let a scaffold tool overwrite the existing prompt documents.
4. Add only foundation dependencies in Phase 01. Phase 02 has an explicit sequential handoff for provider/audio dependency additions; Phase 03 then freezes all manifests before G1.
5. If official documentation conflicts or a version is inaccessible, record the issue and a supported option in REPORT; do not fabricate a successful install or silently change the architecture.

## Security and privacy references

- [OWASP WebSocket security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): authenticated origin-checked connections, message authorization, expiry, limits, backpressure, no sensitive-content logs. Adapt rate limits to audio frame cadence, not a generic chat threshold.
- [OWASP prompt injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html): speech-derived instructions are untrusted input; no tool access or policy override simply because a learner says it.
- [OWASP upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): type/size/duration validation for any persisted audio/fixtures.
- Never place provider keys or a privileged Supabase key in client-visible variables. Missing live configuration must be explicit; a demo fixture must not masquerade as a real API response.
- App-level opt-out does not establish zero provider retention. The Gnani STT billing-record note and unresolved provider/legal terms remain launch gates in `research.md`.

## Phase 01 command contract

These are **required commands for the builder to make available**, not commands executed or claimed to work by the orchestrator:

- Repository root: `npm install` for initial lock creation, subsequently `npm ci`.
- Repository root: `npm run dev:web`, `npm run lint`, `npm run typecheck`, `npm run build`.
- Repository root: `uv sync --project services/voice` for the foundation environment.
- Repository root: `uv run --project services/voice uvicorn gnani_coach.main:app --host 127.0.0.1 --port 8000` for the local service.
- B1 batch entry points to author now but formally execute in the batch: `npm run test:contracts`, `uv run --project services/voice python -m pytest services/voice/tests`, `npm run test:e2e`.

Phase 01 maps root scripts to the actual workspaces, installs an importable Python package, and reports real command outcomes. No global install, secrets, paid API calls, or hosted service provisioning is needed for a working foundation.

## Search limitations

Some second-wave search requests returned 429. The essential pytest/Ajv/Python-validator/Node queries were retried once and succeeded. The cited pages establish candidate features/patterns, not tested package compatibility. Pinning and execution evidence are still mandatory builder deliverables.
