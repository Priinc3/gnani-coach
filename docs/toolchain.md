# Toolchain — exact versions and sources

Verified against authoritative sources on **2026-10-16**. No version was chosen
from memory. All dependencies are exact-pinned; lockfiles are the
reproducible install path.

## Runtimes and package managers

| Tool | Version | Source / reason |
|---|---|---|
| Node.js | **26.7.0** (local; recorded in `.node-version`) | nodejs.org "previous releases": v26.x is the current line; Next.js 16 requires Node ≥ 20.9. `engines.node >= 22` in root `package.json`. |
| npm | 11.19.0 | Ships with Node 26.7.0. |
| Python | **3.12.12** (uv-managed CPython; `.python-version` = `3.12`) | uv resolves `.python-version`; `requires-python >=3.12,<3.13` pins the minor family. |
| uv | **0.10.9** | Project manager + `uv_build` backend (`uv_build>=0.10.9,<0.11.0` in `services/voice/pyproject.toml`). Source: docs.astral.sh/uv. |
| Git | 2.51.0 | Used only for the local repository; no remote. |

## JavaScript / web (npm workspaces)

| Package | Version | Source / reason |
|---|---|---|
| next | **16.4.2** | Latest stable at check time; App Router. Source: nextjs.org installation docs + npm registry. |
| react / react-dom | **19.3.1** | Paired with Next 16. |
| typescript | **6.0.3** | TypeScript 7.0.2 is the latest stable, but `typescript-eslint@8.71.2` declares peer `typescript >=4.8.4 <6.1.0`, so TS 7 would fail `npm ci` with ERESOLVE. 6.0.3 is the newest compatible release. Source: npm registry metadata. |
| eslint | **9.39.5** | ESLint 10.13.0 is the latest stable, but `eslint-plugin-react`, `eslint-plugin-import` and `eslint-plugin-jsx-a11y` (via `eslint-config-next`) declare peer support only up to `^9`. 9.39.5 is the newest 9.x. **Known trade-off:** npm prints "eslint@9.39.5 is no longer supported"; accepted until the plugin chain supports ESLint 10. |
| eslint-config-next | **16.4.2** | Matches Next. Flat config via `eslint-config-next/core-web-vitals` + `/typescript`. |
| @types/node | 26.6.5 | npm registry. |
| @types/react / @types/react-dom | 19.3.0 | npm registry. |
| @playwright/test | **1.64.1** | Source: playwright.dev. Supports Node 26.x. Browsers: `npx playwright install chromium` installs headless Chromium 156.0.8078.4 (playwright v1248). |
| ajv | **8.20.0** | JSON Schema validator for the web side. Used as `Ajv2020` from `ajv/dist/2020.js` (draft 2020-12). |
| ajv-formats | **3.0.1** | Provides `date`, `date-time`, `uri` formats for Ajv. |

## Python (`services/voice`)

| Package | Version | Source / reason |
|---|---|---|
| fastapi | **0.143.3** | Latest stable at check time. Source: PyPI (checked 2026-10-16). |
| uvicorn | **0.54.0** | ASGI server for the local command. Source: PyPI. |
| pydantic | **2.14.1** | Settings models. Source: PyPI. |
| pydantic-settings | **2.16.0** | Env parsing with prefixes and `SecretStr`. Source: PyPI. |
| pytest | **9.1.1** | dev group. Source: PyPI. |
| httpx2 | **2.13.1** | dev group; starlette 1.8.0's test client deprecates `httpx` and prefers `httpx2` (PyPI, uploaded 2026-09-23). |
| jsonschema[format-nongpl] | **4.26.0** | dev group; draft 2020-12 + `FormatChecker`. The extra installs `rfc3339-validator`/`rfc3986-validator` so `date`, `date-time`, `uri` are genuinely checked. Source: PyPI + python-jsonschema docs. |

## Lockfiles (the reproducible path)

- `package-lock.json` — repo root, covers `apps/web`, `packages/contracts`, root tooling.
- `services/voice/uv.lock` — created by `uv sync --project services/voice`.

`npm install` creates/updates the npm lockfile once; **`npm ci` is the
reproducible install path** afterwards. `uv sync` is deterministic from
`uv.lock`.

## Install prerequisites

1. Node ≥ 22 (tested with 26.7.0) and npm ≥ 10 (tested with 11.19.0).
2. uv ≥ 0.10.9 (https://docs.astral.sh/uv/).
3. One-time browser install for tests: `npx playwright install chromium`.
4. No API keys are needed: the foundation runs with zero credentials.

## Root command map

| Command | What it does |
|---|---|
| `npm install` / `npm ci` | Install all npm workspaces from the lockfile. |
| `npm run dev:web` | `next dev` in `apps/web` → http://localhost:3000 |
| `npm run lint` | ESLint 9 flat config over `apps/web`. |
| `npm run typecheck` | `tsc --noEmit` in `apps/web`. |
| `npm run build` | `next build` (production build). |
| `uv sync --project services/voice` | Create/update the Python venv from `uv.lock`. |
| `uv run --project services/voice uvicorn gnani_coach.main:app --host 127.0.0.1 --port 8000` | Start the voice-service skeleton → http://127.0.0.1:8000/health |
| `npm run test:contracts` | Ajv runner: 7 schemas, 36 examples, catalog invariants. |
| `uv run --project services/voice python -m pytest services/voice/tests` | 21 Python tests: contract parity, health, settings boundary, privacy shapes. |
| `npm run test:e2e` | 12 Playwright tests against http://localhost:3000 (starts its own dev server). |
| `npm run check:health` | Fetches `/health` and asserts the exact foundation contract. |

## Notes observed during the build

- `next build` rewrites two values in `apps/web/tsconfig.json`
  (`jsx: "react-jsx"`, and adds `.next/dev/types/**/*.ts` to `include`).
  This is standard Next 16 behavior and was kept.
- npm prints an `install-scripts` warning for `unrs-resolver` (transitive of
  the ESLint resolver chain; this project does not rely on its postinstall).
- `npm audit` reports 5 high findings in the dev-only lint chain
  (`braces` → `micromatch` → `fast-glob` → `@next/eslint-plugin-next` →
  `eslint-config-next`). npm's suggested fix is a downgrade to
  `eslint-config-next@14`, which is a breaking change; not acted on. No
  production runtime dependency is affected.
