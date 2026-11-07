#!/usr/bin/env bash
# Update the running voice service to the current main branch.
#
#     sudo scripts/deploy/update-voice.sh
#
# Fast-forward only: a divergent checkout stops instead of merging. The
# service is restarted only after the frozen environment syncs cleanly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VOICE_HOST:-13-205-26-178.sslip.io}"
UV_BIN="/home/ubuntu/.local/bin/uv"
VOICE_PROJECT="${REPO_ROOT}/services/voice"
UNIT_NAME="gnani-voice.service"

say() { printf '%s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "run this script with sudo"

say "== git pull --ff-only (as ubuntu) =="
sudo -u ubuntu git -C "${REPO_ROOT}" pull --ff-only origin main

say "== syncing the frozen environment =="
sudo -u ubuntu env HOME=/home/ubuntu \
    "${UV_BIN}" sync --frozen --project "${VOICE_PROJECT}"

say "== restarting ${UNIT_NAME} =="
systemctl restart "${UNIT_NAME}"

say "== health =="
for _ in $(seq 1 15); do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null; then
        say "PASS local /health"
        break
    fi
    sleep 1
done

for _ in $(seq 1 20); do
    if curl -fsS --max-time 10 "https://${HOST}/health" >/dev/null; then
        say "PASS https://${HOST}/health"
        say "UPDATE OK (commit $(sudo -u ubuntu git -C "${REPO_ROOT}" rev-parse --short HEAD))"
        exit 0
    fi
    sleep 3
done
say "FAIL public health; recent logs:"
journalctl -u "${UNIT_NAME}" -n 30 --no-pager || true
exit 1
