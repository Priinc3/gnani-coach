# Phase 11 — deploy-voice — REPORT

**State: BUILT.** The voice service is live on this EC2 box behind Caddy
with a valid Let's Encrypt certificate. One worker, memory-capped, SQLite
data directory ready. Commit: `04a4e8c`.

## Files

| Path | Purpose |
| --- | --- |
| `deploy/systemd/gnani-voice.service` | systemd unit: one uvicorn worker on `127.0.0.1:8000`, `MemoryMax=600M`, `MemoryHigh=500M`, `CPUQuota=150%`, `Nice=5`, sandboxing, proxy headers trusted only from `127.0.0.1` |
| `deploy/caddy/Caddyfile` | host variable `{$VOICE_HOST:13-205-26-178.sslip.io}`, WebSocket proxy with `flush_interval -1`, `/apk/*` from `/var/www/gnani-apk`, 12 MB body cap, compression off on `/ws/*` |
| `deploy/voice.env.example` | production env template, names only, no secret values |
| `scripts/deploy/install-voice.sh` | idempotent install: memory check, Caddy official repo, `uv sync --frozen`, VAD prepare, dirs, env completion, unit + Caddyfile, validate, start, TLS health check |
| `scripts/deploy/open-ports.sh` | verifies instance/group, opens only TCP 80/443 from `0.0.0.0/0`, prints before/after diff |
| `scripts/deploy/update-voice.sh` | `git pull --ff-only`, `uv sync --frozen`, restart, local + public health |
| `scripts/deploy/status.sh` | unit state, limits, memory, swap, health, last 30 log lines |
| `docs/release/DEPLOY.md` | what was done, re-run, env file, key rotation, rollback, certificate failure, SQLite backup, limits |
| `.env.example` | short deployment section pointing at `deploy/voice.env.example` |
| `prompts/phase-11-deploy-voice/evidence/` | raw command output (list below) |

## Privileged actions taken

1. **AWS security group** `sg-0ae5a8799482e1588` (instance
   `i-0c645ae0bd6a0522d`, region `ap-south-1`, account
   `498606688392`): `authorize-security-group-ingress` for TCP **80** and
   **443** from `0.0.0.0/0`. Before: only `tcp/22 0.0.0.0/0`. After:
   `tcp/22`, `tcp/80`, `tcp/443`. No other rule, instance or resource was
   touched. Evidence: `sg-before.json`, `sg-after.json`, `open-ports.log`.
2. **apt**: installed `debian-keyring`, `debian-archive-keyring`,
   `apt-transport-https`, `gnupg` and **Caddy 2.11.9** from the official
   Cloudsmith repository (the distro candidate was 2.6.2).
3. **Files/dirs created**: `/etc/gnani-coach/` (0750 root:ubuntu),
   `/etc/gnani-coach/voice.env` completed with missing non-secret settings
   (existing keys untouched), `/var/lib/gnani-coach/` (0700 ubuntu),
   `/var/www/gnani-apk/` (0755 ubuntu), `/var/backups/gnani-coach/`
   (0700 root), `/etc/systemd/system/gnani-voice.service`,
   `/etc/caddy/Caddyfile`.
4. **systemctl**: `enable` + `restart` on `caddy` and `gnani-voice`;
   `daemon-reload`; `reload caddy` after formatting the Caddyfile.

No process not created by this phase was stopped, killed or restarted.
`Paseo Voice`, `opencode`, `kiro-proxy` and `Paso Daemon` were untouched.

## Verification (raw output in `evidence/`)

| Check | Result | Evidence |
| --- | --- | --- |
| `bash -n` on all four scripts | pass | run in transcript |
| `caddy validate` | `Valid configuration` | `caddy-validate.txt` |
| `systemd-analyze verify` on the unit | no finding for `gnani-voice`; only pre-existing warnings for `xfs_scrub*` and `paseo.service` | `systemd-verify.txt` |
| `https://13-205-26-178.sslip.io/health` | HTTP/2 **200**, body `{"status":"ok",...}` | `health-headers.txt`, `health-body.json` |
| TLS certificate | subject `CN=13-205-26-178.sslip.io`, issuer `Let's Encrypt`, valid 2026-11-07 → 2027-02-05 | `cert.txt` |
| WebSocket, allowed origin | **HTTP/1.1 101 Switching Protocols**, server `status connecting` envelope | `ws-handshake-allowed.txt` |
| WebSocket, foreign origin | **403 Forbidden** (origin refused before accept) | `ws-handshake-foreign.txt` |
| HTTP → HTTPS | `308 Permanent Redirect` to the https URL | transcript |
| `/apk/test.apk` | 200, `content-type: application/vnd.android.package-archive`, `content-disposition: attachment; filename=test.apk` | `apk-headers.txt`, `apk-body.txt` |
| `/apk/nope.apk` | 404, no directory listing | transcript |
| Public reachability from outside this box | fetched through `r.jina.ai` and returned the same `/health` JSON | `external-fetch.txt` |
| `MemoryCurrent` after start | **60,821,504 bytes ≈ 58 MB** (peak 58 MB) | `status.txt` |
| Memory limits | `MemoryHigh=524288000` (500 MB), `MemoryMax=629145600` (600 MB), `CPUQuotaPerSecUSec=1.5` | `status.txt` |
| Secret scan | 1 finding, **pre-existing Phase 14 test literal** `PASSWORD = "a-long-test-password"` in `services/voice/tests/identity/test_local.py`; no production value found | `secret-scan.txt` |

Box memory at install: 1.9 GB total, ~805 MB available, 4 GB swap
(`/swapfile` + `/swapfile2`). The service uses ~58 MB; the 600 MB cap is
headroom for SQLite/ONNX work.

## Sources

- Caddy install (official Debian/Ubuntu repository):
  <https://caddyserver.com/docs/install>
- Caddy automatic HTTPS: <https://caddyserver.com/docs/automatic-https>
- Caddy `reverse_proxy` — WebSocket tunnelling, `flush_interval`,
  `stream_timeout`, `X-Forwarded-*` defaults that ignore client-sent
  values: <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>
- uvicorn `--proxy-headers` / `--forwarded-allow-ips` (trust only
  `127.0.0.1`, never `*`): <https://uvicorn.dev/settings/>
- `sslip.io` free IP-embedded DNS: <https://sslip.io/>
- Let's Encrypt rate limits: <https://letsencrypt.org/docs/rate-limits/>
- Render free fallback limits: <https://render.com/docs/free>,
  <https://render.com/docs/websocket>
- AWS `authorize-security-group-ingress`:
  <https://docs.aws.amazon.com/cli/latest/reference/ec2/authorize-security-group-ingress.html>
- Settings guards (production refuses loopback origins and `*`):
  `services/voice/src/gnani_coach/settings.py` (read-only)
- Rate-limit/log-content behaviour: `docs/operations/RUNBOOK.md` (read-only)

## What the user must still do

1. **Keys are already present.** `/etc/gnani-coach/voice.env` reports
   `GNANI_API_KEY=SET` and `GEMINI_API_KEY=SET`; no value was printed or
   copied. To rotate, edit that file (or `/etc/gnani-coach/keys.env`) and
   run `sudo systemctl restart gnani-voice`.
2. **Phase 13 must replace the placeholder origin.** The allowlist is
   currently `https://13-205-26-178.sslip.io` so that the production
   settings guard passes before the web app exists. Set
   `SPEAKING_COACH_ALLOWED_ORIGINS=<Vercel URL>` in
   `/etc/gnani-coach/voice.env` and restart; the browser/APK origin must
   match exactly.
3. **Phase 13 publishes the APK** to `/var/www/gnani-apk/speaking-coach.apk`
   (directory exists, `/apk/` already serves it).
4. **Backups are manual.** See `docs/release/DEPLOY.md` for the
   `sqlite3 .backup` command.

## Limits and honest notes

- **One worker.** Rate limits, connection caps and the latency window are
  per process; a second worker would double every bound and split counters.
- **Single box, no CDN / load balancer.** Caddy is the only edge.
- The public check used `r.jina.ai` (a fetch proxy) because this box is the
  only host available; `api.allorigins.win` returned its own 522, which is
  not evidence about this service.
- The Caddyfile is formatted (`caddy fmt`); the installed copy was
  reloaded after formatting.
- `services/voice/**` was not edited. No `HELP:` was needed.
- The pre-existing dirty files (`fixtures/`, `prompts/00-plan.md`,
  `prompts/_tracker.md`, `prompts/waivers.md`, Phase 02 evidence) and
  sibling paths (`apps/**`, `.github/**`, `prompts/parallel-G2/**`) were
  left alone.

## Commit

`04a4e8c` — `phase-11: Caddy + systemd voice deployment on EC2`

PHASE 11 BUILT
