# Phase 01 — Foundation

Type: **NORMAL** · Batch: **B1 (01 → 02 → 03)** · Status: **READY FOR MANUAL EXECUTION**

## Role and context

You are the engineer for **Phase 01 only**. The user is building solo with AI assistance. Read:

1. `prompts/00-plan.md`, especially the DONE condition, §6 privacy rules and §9 frozen phase map.
2. `prompts/stack-decisions.md`.
3. `prompts/language-support.md` and `prompts/research.md`.
4. `challenge.md` as background, not as authority over the newer API evidence.

The workspace currently has challenge/prompt documents and no app. Re-read the actual directory before making changes; preserve anything added since this prompt was written. **Do not launch other phase agents or implement later phases.** The orchestrator has not built or tested anything.

Starting assumptions: browser-based call; adults-only initial pilot; all listed scenario categories; a ten-language capability catalog; four learner turns per coaching round; optional recording retention off by default; guest preview with sign-in for saved history later. User has asked to start, not to provision paid services or publish.

## Sibling context and ownership

**Siblings running now: none.** This phase is sequential; no COMM/STATUS folder is used or created.

| Phase | State | What it owns later |
|---|---|---|
| 02 provider-feasibility | Not running; future NORMAL | Provider adapters, audio probes, synthetic fixtures, feasibility evidence |
| 03 contract-freeze | Not running; future NORMAL | Final contracts, module ports, composition roots, integration harness and dependency freeze |
| 04/05/06 G1 | Locked pending B1 verification | Respectively call UI, coaching/analysis runtime, identity/private history; see plan for disjoint paths |

### Your OWN files

- Root `package.json`, `package-lock.json`, `.gitignore`, `.node-version`, `.env.example`, `README.md`.
- `apps/web/package.json`; `apps/web/tsconfig.json`; `apps/web/next-env.d.ts`; `apps/web/next.config.*`; `apps/web/eslint.config.*`; `apps/web/.env.example`.
- `apps/web/src/app/layout.tsx`, `apps/web/src/app/page.tsx`, `apps/web/src/app/globals.css`.
- `apps/web/public/` for self-created or license-verified local foundation assets only.
- `packages/contracts/**` including its package/config/schema/catalog/example files and validator tooling.
- `services/voice/pyproject.toml`, `services/voice/uv.lock`, `services/voice/.python-version`, `services/voice/.env.example`.
- `services/voice/src/gnani_coach/__init__.py`, `main.py`, `settings.py`.
- `services/voice/tests/foundation/**` and foundation-only test configuration if needed under `services/voice/`.
- Root `playwright.config.*`, `tests/foundation/**`, `scripts/foundation/**` for future batch entry points only.
- `docs/architecture.md`, `docs/toolchain.md`, `docs/design-direction.md`.
- `prompts/phase-01-foundation/REPORT.md` and `prompts/phase-01-foundation/evidence/**`.
- Local Git metadata if initializing this currently non-Git folder; do not commit/push to a remote or overwrite an existing repository.

**DO NOT TOUCH:** `challenge.md`; CEO plan/tracker/research/BUILD/FIX/VERIFY files; any other phase folder; provider/conversation/analysis/identity/persistence implementations; Supabase migrations; deployment/social-post material; or existing files outside this allowlist. Runtime dependencies, caches and build outputs created by tools are allowed only in their normal ignored locations. Do not capture sensitive user audio.

If a required write is outside this scope, stop that portion and report `HELP NEEDED: path — reason` in your REPORT. No silent ownership expansion.

## Goal

Deliver a **locally runnable, truthful foundation**: a distinctive responsive starter screen, a bootable voice-service skeleton, shared draft contracts, and reproducible commands. It must work without provider credentials while clearly stating that live calls are not implemented yet.

This is one phase, not a request to build the entire app. In particular, **no real STT/TTS/LLM adapter, filler detector, account system or persistent recorder** belongs here.

## Deliverables

### 1. Reproducible monorepo scaffold

- Use Next.js App Router/TypeScript with `apps/web` and a `packages/contracts` npm workspace; a uv-managed importable Python/FastAPI package at `services/voice`.
- Follow the stack source links. Verify current compatible stable releases before installing; record exact package/runtime versions and sources in `docs/toolchain.md`. Do not select versions from memory. If research is unavailable, report the blocker rather than invent compatibility.
- Create committed-format lockfiles; ignore dependencies, build output, caches, real `.env` files and recordings while keeping sanitized `.env.example` files. Never include a real secret, access token or personal audio in source or evidence.
- Preserve the root challenge and prompt documents if using a generator. Inspect generator defaults before running it; no blanket root overwrite.
- Root scripts must expose the command contract below. Avoid bringing in an agent framework, queue broker, component library, native-app tooling or voice cloning.

### 2. Honest starter UI

- Product name can remain **Speaking Coach**; no branding questionnaire needed.
- Design direction: a calm **conversation studio**, warm ivory/ink with a restrained green accent, generous space, editorial heading treatment and readable Indic text. A single central practice panel—not a grid of fake dashboard numbers or a generic purple AI gradient. Self-host any added font only after checking licensing and script coverage; fallback must not render Indic scripts as missing glyphs.
- Show “Practice speaking, not just studying.” Include scenario selection (interview, workplace, everyday, travel/social), separate practice/coaching language selectors, and a clearly explained recording-retention option defaulting off.
- Display the ten documented languages from the shared catalog, not a copied list. Capability badges must say **not yet verified**. French must not appear as a working option.
- No microphone starts on page load. The live start action must be visibly unavailable with a plain reason such as “Live calling will be enabled after speech-provider setup.” Do not show fake connection, recording, transcript or scores.
- If an illustrative preview is included, label it **sample preview — no live AI or recording**, and make it optional. A waveform cannot pretend to reflect the user's microphone.
- Keyboard operability, visible focus, associated labels, sensible narrow-screen layout and reduced-motion behavior are required. No inert mystery buttons or links to nonexistent pages; state clearly when history/sign-in is planned rather than working.

### 3. Bootable service skeleton and configuration boundary

- `gnani_coach.main:app` starts locally and exposes a minimal health response that contains no configuration values or secrets. Health proves process readiness only, **not provider connectivity**.
- Centralize configuration parsing in `settings.py`; missing speech/LLM/storage credentials do not crash foundation startup. Document provider readiness as unavailable, not healthy/live.
- Prepare sanitized environment-variable documentation for later Gnani/Gemini/Supabase setup. No guessed model ID or endpoint beyond researched docs; no secret in a public-prefixed variable. No paid calls or new remote project creation.
- No open speech relay, permissive WebSocket stub or fake authentication. Unimplemented live routes must be absent or fail closed explicitly. Do not persist session content.

### 4. Shared contract draft — not yet frozen

Author authoritative JSON Schema draft 2020-12 definitions and compact positive/negative examples in `packages/contracts`. Ajv and Python `jsonschema` should consume the same files. Validate without remote schema fetching; account for explicit draft and format behavior in both runtimes. These are **draft v0.1**, finalized only in Phase 03 after real provider observations.

Capture the necessary boundaries without implementing the engines:

- **Language/scenario catalog:** stable IDs; STT/TTS codes and code-mixed distinctions; documented/account-enabled/conversation-tested/assessment-validated states. No runtime capability starts verified just because documentation lists it.
- **Session settings:** practice and coaching language, scenario/level, coaching-round length, optional recording retention, session limit, versioned consent fields. No inference that consent to save audio permits permanent transcripts.
- **Event envelope:** explicit version/type, session/connection/round/turn identifiers, ordered sequence, and distinct sample-time versus emitted-time concepts. Define text control events separately from a proposed binary audio profile; never put base64 audio or transcripts in durable metrics by convenience.
- **Transient analysis observation:** measured versus inferred source, evidence span when known, unit, reliability/limitations, and nullable/unavailable values. Zero fillers is different from unmeasurable fillers.
- **Durable metrics shape:** allowlisted numeric results and necessary metadata only, rejecting extra content-bearing fields such as audio, transcript, quoted mistakes, arbitrary model text and embeddings.
- **Recording metadata boundary:** ownership, consent version, expiry/deletion state and private reference—not a public audio URL. No storage implementation yet.
- **Error shape:** plain-word user message, stable error category and retryability; no raw provider stack trace, secret, or raw learner content.

Define what is missing/unknown in `docs/architecture.md`. Do not conjure word timestamps from Gnani's server timestamps. Do not choose a disfluency algorithm in this phase. Add fixtures for unavailable metrics, null/zero/empty distinctions, invalid language codes, stale identifiers, and forbidden fields in metrics-only payloads. Actual protocol/identity implementations arrive later.

### 5. Future batch checks, authored now

- Create genuine foundation test cases for contract parity, health/config behavior, privacy-shape rejection, and the truthful accessible starter screen.
- Supply root `test:contracts` and `test:e2e` scripts and the backend pytest layout, so B1 can execute them after Phase 03. These must not be empty success scripts or “pass with no tests.”
- Do not write `batch-B1-TEST.md`, `TEST-RESULT.md`, VERIFY or tracker verdicts: those belong to the later batch workflow. Authoring tests is not evidence that they passed.

## Criteria and exact commands

From the repository root, make these commands real and document prerequisites:

1. `npm install` — initial lock creation; then `npm ci` must be the reproducible install path.
2. `npm run lint`
3. `npm run typecheck`
4. `npm run build`
5. `uv sync --project services/voice`
6. `npm run dev:web` — document the actual local URL/port.
7. `uv run --project services/voice uvicorn gnani_coach.main:app --host 127.0.0.1 --port 8000`

Run static/build and startup diagnostics for your implementation and include actual output/exit status. Do not turn those into a per-phase acceptance verdict. Formal tests remain batched after 01–03. Stop any foreground/background development processes you started before finishing unless the user explicitly wants them left running.

Author for B1, with exact root invocation documented:

- `npm run test:contracts`
- `uv run --project services/voice python -m pytest services/voice/tests`
- `npm run test:e2e`

If an environment/tool prerequisite is unavailable, distinguish `NOT RUN` from `FAIL` and report the next action. Do not replace missing execution with expected output. A missing key cannot block this phase because live inference is out of scope.

## Constraints and sources

- Web/toolchain: https://nextjs.org/docs/app/getting-started/installation · https://nodejs.org/en/about/previous-releases · https://docs.astral.sh/uv/guides/projects/
- Backend: https://fastapi.tiangolo.com/advanced/websockets/
- Schemas: https://ajv.js.org/json-schema.html · https://python-jsonschema.readthedocs.io/en/stable/validate/
- Test infrastructure: https://playwright.dev/docs/intro · https://docs.pytest.org/en/stable/how-to/index.html
- Speech boundaries: https://docs.gnani.ai/api/STT/stt-websocket · https://docs.gnani.ai/api/TTS/tts-websocket
- Security: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
- Full rationale, limitations and remaining source checks: `prompts/stack-decisions.md` and `prompts/research.md`.

Never normalize away disfluencies in an analysis contract; never equate transcription confidence with a speaking score; no emotion/personality/clinical scoring. No persistent raw content in metrics-only examples. Any new library/API/version/security decision requires checking an authoritative source and recording its URL.

## Required REPORT.md — files, not chat-only

Always write **`prompts/phase-01-foundation/REPORT.md`**, including if blocked. Use these sections:

1. **Status:** `BUILT — AWAITING B1 TEST` or `BLOCKED`; never `✅ VERIFIED`.
2. **Scope/ownership:** files changed with purposes; any attempted or needed out-of-scope change.
3. **Toolchain:** actual selected versions, documentation URLs, exact install prerequisites and lockfile locations.
4. **Commands and raw output:** command, working directory, exit status and output; long content-free logs may be linked under your evidence folder. Redact secrets, not error evidence. Explicit `NOT RUN` for anything unexecuted.
5. **Manual observation:** URLs/steps actually checked, what was visible, and optional screenshots; do not claim browser testing if no browser was available.
6. **Contract draft:** files, examples, differences between transient observations and durable metrics, and unresolved questions for Phase 03.
7. **Known limits:** live calls/providers, audio analysis, auth/storage and all-ten runtime support are unimplemented/unverified; list any additional gaps.
8. **Help needed / blocked by:** concrete missing input and smallest next action. Do not ask for secret values in this file.
9. **Handoff:** what Phase 02 may build on and whether any development process was left running.

Stop after writing REPORT. Do not run Phase 02, create a FIX for yourself outside this scope, or edit CEO documents. The user returns the report path to the orchestrator; the batch is not done without its eventual batch TEST evidence.
