#!/usr/bin/env bash
# Read-only status for the voice service. Safe to run without sudo.
#
#     scripts/deploy/status.sh
#
# Logs are content-free by design (docs/operations/RUNBOOK.md): they carry
# no transcript, reply, user id or session id.
set -euo pipefail

UNIT_NAME="gnani-voice.service"
HOST="${VOICE_HOST:-13-205-26-178.sslip.io}"

say() { printf '%s\n' "$*"; }

say "== ${UNIT_NAME} =="
systemctl status "${UNIT_NAME}" --no-pager --lines=0 || true

say ""
say "== unit limits and current usage =="
systemctl show "${UNIT_NAME}" \
    -p ActiveState -p SubState -p MemoryCurrent -p MemoryMax -p MemoryHigh \
    -p CPUQuotaPerSecUSec -p NRestarts -p ExecMainStartTimestamp || true

say ""
say "== memory (MB) =="
free -m

say ""
say "== swap =="
swapon --show || true

say ""
say "== caddy =="
systemctl is-active caddy || true

say ""
say "== local health =="
curl -fsS --max-time 5 http://127.0.0.1:8000/health || say "local health FAILED"
say ""

say "== public health =="
curl -fsS --max-time 10 "https://${HOST}/health" || say "public health FAILED"
say ""

say "== last 30 log lines =="
journalctl -u "${UNIT_NAME}" -n 30 --no-pager || true
