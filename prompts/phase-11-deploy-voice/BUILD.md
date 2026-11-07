# Phase 11 — deploy-voice (B4, PARALLEL:G2)

You are Phase 11 (G2). **Siblings running now:** [10 mobile-ui: `apps/web/src/**` except auth, `apps/web/public/**`, `apps/web/tests/**`], [12 apk-ci: `apps/mobile/**`, `.github/workflows/android-apk.yml`], [14 sqlite-backend: `services/voice/src/gnani_coach/{identity,persistence}/**`, `apps/web/src/{lib/auth,app/auth}/**`, `apps/web/src/proxy.ts`].
Your OWN files: `deploy/**`, `scripts/deploy/**`, `docs/release/DEPLOY.md`, root `.env.example`, your `prompts/phase-11-deploy-voice/REPORT.md` + `evidence/`. Plus the **server state** this phase creates on this box and in the AWS security group (below).
DO NOT TOUCH: `apps/**`, `services/**`, `packages/**`, `supabase/**`, `.github/**`, `tests/**`, other root files, CEO files.
Shared read-only: `services/voice/**` (learn the entry point, health route, env names), `docs/operations/RUNBOOK.md`.
Comm folder: `prompts/parallel-G2/`.

## Context
Goal (`prompts/00-plan.md` §10): the voice service is the whole backend and runs **on this EC2 box** (2 GB RAM, 2 CPUs, public IPv4 `13.205.26.178`) behind HTTPS so phone microphones work. Web goes to Vercel and the APK to GitHub Actions (Phase 13 does Vercel; Phase 12 does the APK). Storage is **SQLite on local disk** (Phase 14), not Supabase. **You deploy it yourself** (user-authorized, waiver W08).

## Authorised actions (exactly these, nothing wider)
- `sudo` on this box for: installing Caddy, writing `/etc/gnani-coach/`, `/var/lib/gnani-coach/`, `/var/www/gnani-apk/`, the two systemd units, `systemctl` for **our** units and `caddy`.
- AWS CLI (already authenticated, region `ap-south-1`): **only** `aws ec2 authorize-security-group-ingress` for TCP **80** and **443** from `0.0.0.0/0` on the group of instance `i-0c645ae0bd6a0522d` (group `sg-0ae5a8799482e1588`, verify with `describe-instances` first), after `describe-security-groups` shows whether the rules already exist (idempotent). Do **not** touch port 22 or any other rule, IAM, other instances or other resources. Save the before/after `describe-security-groups` output in `evidence/`.
- Do **not** stop, kill or restart any process you did not create (in particular `Paseo Voice`, `opencode`, `kiro-proxy`, `Paso Daemon`). Memory is tight: use the swap, the unit's `MemoryMax`, and `nice`.

## Secrets
Never write a key value into the repo, a prompt, a report, a log or a command line argument (shell history/`ps` leak). The user creates `/etc/gnani-coach/voice.env` (mode 0600, owner root:ubuntu 0640 is fine) with `GNANI_API_KEY`, `GEMINI_API_KEY`. Your script creates the file **from the example with empty values only if missing** and then stops with "fill these two lines, then run `sudo systemctl restart gnani-voice`". If the keys are already present, never print them (print `SET`/`EMPTY` per name only). If keys are empty the service must still start (providers report `unavailable`, `/health` still 200) and the smoke phase flags it.

## Box limits (hard)
Install and run only what is needed. No `next build`, no Playwright, no Docker, no Gradle. One heavy command at a time. Check `free -m` before each step.

## Goal
After you finish: `https://13-205-26-178.sslip.io/health` answers 200 over a valid certificate from the open internet, the voice service runs under systemd with one worker and a memory cap, a WebSocket handshake from an allowed origin works, and `/apk/` serves files from `/var/www/gnani-apk/`.

## Deliverables
1. `deploy/systemd/gnani-voice.service`: `uv run --project services/voice uvicorn gnani_coach.main:app --host 127.0.0.1 --port 8000 --workers 1` (verify the module path), `User=ubuntu`, `EnvironmentFile=/etc/gnani-coach/voice.env` and a second `EnvironmentFile=-/etc/gnani-coach/keys.env` (the dash makes it optional; the user creates it, it holds only the two provider keys), `Restart=on-failure`, `RestartSec=3`, `MemoryMax=600M`, `MemoryHigh=500M`, `CPUQuota=150%`, `Nice=5`, `NoNewPrivileges=true`, `ProtectSystem=full`, `PrivateTmp=true`, `ReadWritePaths=/var/lib/gnani-coach`, `StateDirectory`-style data dir mode 0700 owned by `ubuntu`. **Client address (CEO addendum, from the Phase 14 review):** the rate limiters key on `request.client.host`, so behind Caddy the unit must let uvicorn read Caddy's `X-Forwarded-For`: do **not** pass `--no-proxy-headers`; pass `--proxy-headers --forwarded-allow-ips 127.0.0.1` explicitly (uvicorn trusts only that address; source https://uvicorn.dev/settings/ , "HTTP" section), and keep Caddy's default of ignoring client-sent `X-Forwarded-*` (source: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy , "Defaults"). Do not trust `*`. Phase 13 verifies that two different outside addresses are not counted as one. Env also sets `PYTHONDONTWRITEBYTECODE=1`, `UV_NO_SYNC`-style flags if useful so the unit never downloads at runtime.
2. `deploy/caddy/Caddyfile`: host `13-205-26-178.sslip.io` (variable for a future domain) → `reverse_proxy 127.0.0.1:8000` (WebSockets pass through; verify in https://caddyserver.com/docs/caddyfile/directives/reverse_proxy), `handle_path /apk/*` → `root * /var/www/gnani-apk` + `file_server` (no browse), `header` set `Content-Disposition` for `.apk`, request body limit `12MB`, compress off for the WS path. Calls up to 15 minutes must not be cut by timeouts.
3. `deploy/voice.env.example` (names only): `GNANI_API_KEY=`, `GEMINI_API_KEY=`, `GEMINI_MODEL=gemini-3.5-flash-lite`, `GNANI_STT_WS_URL` and `GNANI_TTS_WS_URL` (defaults from `services/voice/.env.example`), `SPEAKING_COACH_ENVIRONMENT=production`, `SPEAKING_COACH_ALLOWED_ORIGINS=` (comma list; no `*`, no loopback in production, see `settings.py`; filled by Phase 13 with the Vercel URL), `SPEAKING_COACH_STORAGE_BACKEND=sqlite`, `SPEAKING_COACH_DATA_DIR=/var/lib/gnani-coach`. Leave caps at defaults. No Supabase names active.
4. `scripts/deploy/install-voice.sh` (`set -euo pipefail`, run with sudo, idempotent): memory check (warn < 400 MB free, confirm swap, print how to add if missing), apt-install Caddy from the official repo (https://caddyserver.com/docs/install), `uv sync --frozen --project services/voice` as `ubuntu`, VAD model via `python -m gnani_coach.analysis.prepare`, create dirs/env as above, install the unit and Caddyfile, `caddy validate`, `systemctl enable --now`, then `curl -fsS https://<host>/health` with retries (certificate issuance takes seconds) printing PASS/FAIL. Add `scripts/deploy/open-ports.sh` for the AWS step (idempotent, prints the diff).
5. `scripts/deploy/update-voice.sh` (`git pull --ff-only`, `uv sync --frozen`, restart, health check), `scripts/deploy/status.sh` (unit state, `free -m`, 30 log lines; logs are content-free by design, see RUNBOOK).
6. `docs/release/DEPLOY.md`: short and exact: what was done on this box, how to re-run, where the env file is, how to rotate a key, rollback (`git checkout <sha>` + update script), "if the certificate fails" (Let's Encrypt rate limits for sslip.io, custom-domain alternative, Render free fallback with its limits: https://render.com/docs/free , https://render.com/docs/websocket), SQLite backup (`sqlite3 .backup` into `/var/backups/gnani-coach`), what is not done (one worker so rate limits are per process, no CDN).
7. Root `.env.example`: a short deployment section pointing to `deploy/voice.env.example`. Names only.
8. **Run it.** Execute `open-ports.sh`, then `install-voice.sh`, then verify from this box and, where possible, from the outside (`curl https://13-205-26-178.sslip.io/health`; also confirm port 443 is reachable from a public checker via `curl` only, no scanners). If the service is on `main` before Phase 14 lands, deploy what exists; Phase 13 re-runs `update-voice.sh`.

## Criteria
`bash -n` passes on every script; `caddy validate` and `systemd-analyze verify` pass; `/health` is 200 over valid TLS; the unit has `MemoryMax`; memory used by the service after start is reported (`systemctl show -p MemoryCurrent`); no secret value anywhere (run `python tools/probes/secret_scan.py` once if present); port 22 rule unchanged (show the diff).

## Constraints
Search before choosing any install method or flag; cite URLs. Production settings must satisfy `settings.py` guards. Do not edit `services/voice`; need a change → `HELP:` in COMM and wait for a CEO FIX.

## Parallel rules (G2)
- First agent to start creates `prompts/parallel-G2/COMM.md` and `STATUS.md` if missing. COMM stub: `# G2 COMM`. STATUS stub: header `| Phase | State | Updated | Doing now | Need |`, separator, rows 10, 11, 12, 14 as `NOT STARTED`.
- COMM.md: `## NN HH:MM — <≤25 words>` + tag `INFO|HELP|DECISION|BLOCKED`. No code/logs. Author appends `RESOLVED: reason`. Keep < 60 lines.
- STATUS.md: update **only your row** at start, on change, at finish. `ACTIVE|BLOCKED|DONE`; Doing < 15 words.
- Read COMM + STATUS at start and before REPORT. Editing sibling files is 🔴. Blocked > 1 cycle → REPORT with `BLOCKED BY:`.

## Git (autonomous, user-authorized W08)
`git add` **only your OWN paths** (never `-A`/`.`), commit `phase-11: <what>`, `git pull --rebase origin main`, `git push origin main`. No force-push, no `.env*` except `*.example`, leave the pre-existing dirty files alone.

## REPORT.md (required)
Files; every privileged action taken (sudo commands summary, the SG diff); commands + raw output paths in `evidence/`; sources; memory numbers; what the user must still do (fill the two keys); limits; help needed; commit hash. End `PHASE 11 BUILT` or `BLOCKED: reason`. Stop there.
