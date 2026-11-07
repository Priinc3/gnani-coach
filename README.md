# Speaking Coach

Live voice-conversation practice with audio-grounded coaching: pick a scenario
and a language, hold a real spoken conversation, and get feedback grounded in
what you actually said.

**Current status: Phase 01 (foundation) — awaiting batch tests.** This
repository runs locally with zero credentials. Live calling is **not
implemented**: there is no microphone access, no provider connection, no
recording, and nothing is stored. The starter screen says so on purpose.

> Practice speaking, not just studying.

## Quick start

Prerequisites: Node 24 LTS (tested: **24.22.0** / npm 11.19.1; `nvm use`
reads the committed `.nvmrc`) and [uv](https://docs.astral.sh/uv/) ≥ 0.10.9.
No API keys required.

```sh
# Web + contracts (npm workspaces)
npm install        # first time only: creates package-lock.json
npm ci             # the reproducible install path
npm run dev:web    # → http://localhost:3000

# Voice service skeleton (uv-managed Python)
uv sync --project services/voice
uv run --project services/voice uvicorn gnani_coach.main:app --host 127.0.0.1 --port 8000
# → http://127.0.0.1:8000/health

# Checks
npm run lint            # ESLint (apps/web)
npm run typecheck       # tsc --noEmit (apps/web)
npm run build           # next build
npm run test:contracts  # Ajv over 7 schemas + 46 fixtures + catalog invariants
uv run --project services/voice python -m pytest services/voice/tests
npm run test:e2e        # Playwright (starts its own dev server; install once: npx playwright install chromium)
npm run check:health    # asserts the exact /health contract of a running service
```

## Repository layout

| Path | Purpose |
|---|---|
| `apps/web` | Next.js 16 App Router starter screen (the only UI). |
| `packages/contracts` | Draft v0.1 JSON Schema 2020-12 contracts, the shared language catalog, fixtures, and the Ajv runner. |
| `services/voice` | FastAPI skeleton: `GET /health` + the configuration boundary (`pydantic-settings`). |
| `tests/foundation` | Playwright e2e for the starter screen. |
| `scripts/foundation` | Service health check and screenshot capture. |
| `docs/` | Toolchain versions/sources, architecture boundaries, design direction. |
| `prompts/phase-01-foundation/` | Build spec, `REPORT.md`, and raw command evidence. |

## What is real here

- The starter screen, rendered from the shared catalog: ten documented
  languages (each honestly badged **Not yet verified**), four scenarios,
  separate practice/coaching language selects, recording retention off by
  default.
- The contracts: draft 2020-12 schemas consumed identically by Ajv and Python
  `jsonschema`, with positive/negative fixtures.
- The service skeleton: one health route that proves process readiness only;
  every unimplemented route is simply absent (404).
- A parsed configuration boundary (`GNANI_*`, `GEMINI_*`, `SUPABASE_*`,
  `SPEAKING_COACH_*`) where nothing is required and nothing is called.

## Privacy stance

- No microphone is requested on page load — ever, in this phase.
- Recording retention is off by default; consent to keep audio never extends
  to transcripts or notes.
- Nothing from this repository is sent anywhere: no telemetry, no remote
  calls, no stored sessions.

## Where to read more

- `docs/architecture.md` — boundaries and the explicit list of what is
  missing/unknown.
- `docs/toolchain.md` — exact versions, why each was chosen, and sources.
- `docs/design-direction.md` — the visual/interaction system.
- `packages/contracts/README.md` — contract draft status and rules.
- `prompts/phase-01-foundation/REPORT.md` — the phase report with raw
  command output and evidence.
