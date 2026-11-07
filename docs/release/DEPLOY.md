# Voice service deployment (EC2 + Caddy + systemd)

The voice service is the whole backend: FastAPI, SQLite on local disk and
the local email/password identity (Phase 14). It runs on this EC2 box
(2 GB RAM, 2 vCPU, public IPv4 `13.205.26.178`) behind Caddy, which
terminates TLS for the free `13-205-26-178.sslip.io` name.

| Piece | Where | How |
| --- | --- | --- |
| Voice API + WebSocket | this box, `127.0.0.1:8000` | systemd unit `gnani-voice.service` |
| TLS + static APK | this box, ports 80/443 | Caddy, `/etc/caddy/Caddyfile` |
| SQLite + recordings | `/var/lib/gnani-coach` (0700, `ubuntu`) | `SPEAKING_COACH_DATA_DIR` |
| APK files | `/var/www/gnani-apk/` | `https://13-205-26-178.sslip.io/apk/...` |
| Web app | Vercel (Phase 13) | `NEXT_PUBLIC_VOICE_WS_URL` |

## What was done on this box

1. Opened TCP **80** and **443** from `0.0.0.0/0` on security group
   `sg-0ae5a8799482e1588` (instance `i-0c645ae0bd6a0522d`, region
   `ap-south-1`). Port 22 and all other rules were left unchanged.
2. Installed Caddy from the official Cloudsmith repository
   (<https://caddyserver.com/docs/install>), not the older distro package.
3. Created `/etc/gnani-coach/voice.env` (0640 `root:ubuntu`) with the
   non-secret settings and the two provider keys.
4. Installed `deploy/systemd/gnani-voice.service` and
   `deploy/caddy/Caddyfile`, then `systemctl enable --now` for both.
5. Synced `services/voice` from its frozen lock file and prepared the
   Silero VAD asset once.

Re-run everything (idempotent):

```bash
cd /home/ubuntu/prince/gnani
scripts/deploy/open-ports.sh                 # no sudo; AWS CLI already logged in
sudo scripts/deploy/install-voice.sh         # Caddy, unit, dirs, health
```

Daily operations:

```bash
scripts/deploy/status.sh                     # state, memory, 30 log lines
sudo scripts/deploy/update-voice.sh          # git pull --ff-only, sync, restart, health
```

## The environment file

`/etc/gnani-coach/voice.env` (mode 0640, owner `root:ubuntu`) is the only
place production values live. The template is
`deploy/voice.env.example`; it is committed with empty secrets.

The unit loads `voice.env` first and the optional
`/etc/gnani-coach/keys.env` second. Put the two provider keys in either
file; `keys.env` wins when both exist. **Never pass a key as a command-line
argument**: shell history and `ps` expose it.

### Rotate a key

```bash
sudoedit /etc/gnani-coach/voice.env      # or keys.env
sudo systemctl restart gnani-voice
curl -fsS https://13-205-26-178.sslip.io/health
```

The install script prints only `SET`/`EMPTY` per credential name, never a
value.

## Rollback

The deploy is just the checked-out commit plus the systemd unit:

```bash
cd /home/ubuntu/prince/gnani
git log --oneline -10                     # pick the last good sha
sudo -u ubuntu git checkout <sha>
sudo -u ubuntu /home/ubuntu/.local/bin/uv sync --frozen --project services/voice
sudo systemctl restart gnani-voice
curl -fsS https://13-205-26-178.sslip.io/health
```

To return to `main` afterwards: `sudo -u ubuntu git checkout main`.

## If the certificate fails

Caddy obtains a Let's Encrypt certificate automatically over HTTP-01. Both
ports must be open and the name must resolve to this box:

```bash
getent hosts 13-205-26-178.sslip.io     # must print 13.205.26.178
sudo journalctl -u caddy -n 100 --no-pager
```

- **Rate limits.** `sslip.io` is a shared public suffix; repeated failed
  issuance can hit Let's Encrypt's per-registered-domain limits
  (<https://letsencrypt.org/docs/rate-limits/>). Wait, or use the staging
  CA while debugging (`acme_ca https://acme-staging-v02.api.letsencrypt.org/directory`).
- **Custom domain.** Point an A record at `13.205.26.178`, then set
  `VOICE_HOST=voice.example.com` for Caddy (the Caddyfile reads
  `{$VOICE_HOST:13-205-26-178.sslip.io}`) and re-run the install script.
- **Render fallback.** A free Render web service (512 MB, WebSockets
  supported, no maximum WebSocket duration) sleeps after 15 minutes idle,
  giving roughly a one-minute cold start:
  <https://render.com/docs/free>, <https://render.com/docs/websocket>.
  It has ephemeral disk, so SQLite and recordings would not survive a
  restart — use it only as a last-resort demo host.

## SQLite backup

The database and recordings live in `/var/lib/gnani-coach`. Use SQLite's
online backup (safe while the service runs), not `cp`:

```bash
sudo install -d -o root -g root -m 0700 /var/backups/gnani-coach
sudo sqlite3 /var/lib/gnani-coach/gnani-coach.sqlite3 \
  ".backup '/var/backups/gnani-coach/gnani-coach-$(date +%Y%m%dT%H%M%SZ).sqlite3'"
```

Restore: stop `gnani-voice`, replace the database file with the backup,
keep owner `ubuntu` and mode `0600`, start the unit. Recordings are WAV
files under the same data directory and need their own copy.

## What this deployment does not do

- **One worker.** Rate limits, connection caps and the latency window are
  per process (RUNBOOK §3); a second worker would double every bound and
  split the counters. `MemoryMax=600M` and `CPUQuota=150%` are sized for
  one process on this box.
- **No CDN and no load balancer.** Caddy is the only edge; the box is a
  single point of failure.
- **No automatic database vacuum/retention job.** Recording expiry and
  quotas are enforced by the service, but backups are manual.
- **TLS certificate renewal is automatic** through Caddy; nothing else on
  the box is hardened or backed up by this phase.
