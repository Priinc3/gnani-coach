# Phase 09 — release-package (B3, NORMAL)

You are Phase 09. **Siblings running now: none.** Phases 07 and 08 are finished. Comm folder: none.

Goal link: `prompts/00-plan.md` §2, and the contest rules in `challenge.md` (read it fully: the **Nov 10, 2026** deadline, the public demo post on LinkedIn or X with `#GreatIndianAIInternshipChallenge` and `#GnaniAI`, the Stage 3 submission, no real personal data, Gnani tech genuinely load-bearing and named). You make the product reproducibly deployable and write the **honest** handoff materials. **You do not publish, post, provision paid services, deploy, or submit.** Those need the user's explicit action.

## OWN (write)
`deploy/**` · `.github/**` · root `README.md`, `CHANGELOG.md`, `.env.example` · `docs/release/**` · `tests/release/**` · `scripts/release/**` · your own `prompts/phase-09-release-package/REPORT.md` + `evidence/`.
DO NOT TOUCH: app code (`apps/**`, `services/**`), `packages/**`, `supabase/**`, `tests/{integration,acceptance,foundation}/**`, `docs/{contracts,feasibility,operations,evaluation}/**` (read them; link to them), `tools/**`, `fixtures/**`, `UI.png`, CEO files. A defect found goes into REPORT with file:line.

## Read first
`challenge.md`, `docs/operations/**`, `docs/evaluation/RELEASE-CAPABILITIES.md` and the Phase 07 and 08 REPORTs. **Every claim in your materials must trace to those. If Phase 08 says a language or feature is unverified, you say so.**

## Deliverables

### A. Deployment config (research each choice. Cite official docs. Don't provision)
The web app (Next.js 16) and the voice service (FastAPI, needs **long-lived WebSockets**) have different hosting needs: check each candidate host's current WebSocket and timeout limits before choosing. Provide: a `Dockerfile` for the voice service (non-root user, pinned base image by tag + digest if you can verify the digest, health check, no secrets baked in, the VAD model prepared via the documented command at build or first run with the sha256 check); a build/run recipe for the web app on the chosen host; `deploy/README.md` with the exact steps, the **env table by name only**, which values are public (`NEXT_PUBLIC_VOICE_WS_URL`) and which are secret, the production origins to set (`SPEAKING_COACH_ALLOWED_ORIGINS`, `SPEAKING_COACH_ENVIRONMENT=production`), the Supabase project setup (apply `supabase/migrations`, allow-listed redirect URLs, private bucket check), and a rollback note. Validate what you can without a host: `docker build` only if Docker exists, otherwise a static lint of the Dockerfile and `BLOCKED: no Docker` in REPORT.

### B. CI (`.github/workflows/`)
One workflow, **no secrets**, running: contracts tests, voice tests, lint, typecheck, build, integration + assembled tests (Playwright browsers installed with caching), secret scan. Pin action versions to full commit SHAs after verifying each from its official repo (cite). Least privilege `permissions: contents: read`. No deploy job. Opt-in live tests are excluded and skipped.

### C. Reproducible release
`scripts/release/` — a check script (`verify-release.sh`/`.mjs`) that, from a clean clone, installs from lockfiles (`npm ci`, `uv sync --frozen`), runs the CI commands, runs the secret scan, confirms that no `.env` is tracked, confirms the prepared VAD asset's sha256, and prints a pass/fail table. `tests/release/` tests that the script's checks detect: a tracked `.env`, a missing lockfile, a `NEXT_PUBLIC_` secret-looking name, and a filler count anywhere in the shipped UI strings. Provide `CHANGELOG.md` (what exists, honest) and a root `README.md` with: what it is, a 5-command quickstart, the architecture in 10 lines, the env names, test commands, the licence/asset provenance, and a **Known limitations** section copied from Phase 08's disclosed list.

### D. Contest handoff materials (`docs/release/`) — all drafts for the user to review and publish
1. `PROJECT-EXPLANATION.md` (the Stage 3 written explanation, ≤ 900 words): the problem, the product, the architecture and **what Gnani does vs what we do vs why** (Gnani realtime STT and TTS are in the live path of every call. Gemini only reasons over text. Silero VAD estimates speech regions. Supabase holds identity and metrics), the contribution (solo, with AI agents: say exactly how: prompt-driven engineer agents, human-run), the models and technologies used with versions, the privacy design (recording off by default; metrics-only; provider retention caveat), and **honest limits** (filler localisation unvalidated and shown as "not enough evidence", synthetic-only accuracy, languages by evidence).
2. `DEMO-SCRIPT.md`: a 60-second video script (shot list with timings, what is shown on screen, which states are real vs fixture). Use **synthetic speech only, no real personal data**. Plus a 3–5 minute extended walkthrough outline. Never show a state you can't reproduce live. If the live path is unproven at that time, the script says "record only after the B3 live checks pass".
3. `POST-DRAFTS.md`: LinkedIn and X drafts with both hashtags and the live demo link as a placeholder `<DEMO_URL>`, claims limited to verified ones, no engagement-bait, no invented numbers. A checklist to nominate the posts.
4. `SUBMISSION-CHECKLIST.md`: each Stage 3 item from `challenge.md` (demo/video, written explanation, models used, contributions, nominated post links) → file → status (`READY | NEEDS USER | BLOCKED`). Deadline date and a day-by-day countdown from the date of REPORT.
5. `ATTRIBUTION.md`: licences and sources for every dependency and asset (Silero VAD MIT with its URL and sha256; fonts if any; the SVG coach is original; icons original). `npm ls --prod` and `uv` tree summarised with the licences found. Unknown licence = flagged.
6. `PRIVACY-NOTICE.md`: plain-words user-facing text: what is processed live, what is saved only if the learner opts in, how to delete, who the providers are, the Gnani retention caveat. Only claims the code enforces (trace each to a test).

### E. Honesty audit (automated, in `tests/release/`)
Fail the release check if any shipped UI string, README or release doc contains: "10+ languages" or an all-ten claim while Phase 08 enabled fewer, a filler count or "um/uh detection" claim, "guaranteed", an overall score, "confidence" as a score, "pronunciation score", or "end-to-end encrypted" or "never stored anywhere".

## Criteria / commands (repo root, full output into `evidence/`)
The CI commands · `tests/release` suite (document the command) · the verify-release script · `secret_scan.py` (0) · Docker build or a recorded `BLOCKED`. Everything must exit 0, or be `BLOCKED` with the reason.

## Constraints
No publishing, no posting, no purchases, no provisioning, no commit/push. Placeholders for URLs and names. No real personal data in any doc. Search before every host, action or version decision and cite it.

## REPORT.md
Files; commands with raw output paths; host decision with sources and limits; what is READY, NEEDS USER and BLOCKED in the checklist; the honesty-audit results; defects found (file:line). End `PHASE 09 BUILT — AWAITING B3 TEST` or `BLOCKED: reason`. Stop there.
