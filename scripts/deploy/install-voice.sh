#!/usr/bin/env bash
# Install and start the Gnani Coach voice service on this EC2 box.
#
# Run with sudo from the repository root:
#     sudo scripts/deploy/install-voice.sh
#
# Idempotent: safe to run again after a config change. It never prints or
# copies a secret value, and it never overwrites an existing key.
#
# Sources:
#   Caddy install:  https://caddyserver.com/docs/install (Debian/Ubuntu)
#   Caddy auto TLS: https://caddyserver.com/docs/automatic-https
#   uvicorn flags:  https://uvicorn.dev/settings/ ("HTTP")
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VOICE_HOST:-13-205-26-178.sslip.io}"
ENV_DIR="/etc/gnani-coach"
ENV_FILE="${ENV_DIR}/voice.env"
KEYS_FILE="${ENV_DIR}/keys.env"
DATA_DIR="/var/lib/gnani-coach"
APK_DIR="/var/www/gnani-apk"
BACKUP_DIR="/var/backups/gnani-coach"
UNIT_NAME="gnani-voice.service"
UNIT_SRC="${REPO_ROOT}/deploy/systemd/${UNIT_NAME}"
CADDY_SRC="${REPO_ROOT}/deploy/caddy/Caddyfile"
CADDY_DST="/etc/caddy/Caddyfile"
UV_BIN="/home/ubuntu/.local/bin/uv"
VOICE_PROJECT="${REPO_ROOT}/services/voice"

say() { printf '%s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "run this script with sudo"
[[ -x "${UV_BIN}" ]] || fail "uv not found at ${UV_BIN}"
[[ -f "${UNIT_SRC}" ]] || fail "missing ${UNIT_SRC}"
[[ -f "${CADDY_SRC}" ]] || fail "missing ${CADDY_SRC}"

# ---------------------------------------------------------------------------
# 0. Box health. Memory is the binding constraint on this 2 GB machine.
# ---------------------------------------------------------------------------
say "== memory before install =="
free -m | sed -n '1,3p'
AVAILABLE_MB="$(free -m | awk '/^Mem:/{print $7}')"
if [[ "${AVAILABLE_MB}" -lt 400 ]]; then
    say "WARNING: only ${AVAILABLE_MB} MB available (want >= 400 MB)."
fi
if ! swapon --show | grep -q .; then
    say "WARNING: no swap. Add 2 GB with:"
    say "  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile"
    say "  sudo mkswap /swapfile && sudo swapon /swapfile"
    say "  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab"
else
    say "swap:"
    swapon --show
fi

# ---------------------------------------------------------------------------
# 1. Caddy from the official package repository (not the distro build).
# ---------------------------------------------------------------------------
if command -v caddy >/dev/null 2>&1; then
    say "== Caddy already installed: $(caddy version | head -1) =="
else
    say "== installing Caddy from the official repository =="
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq debian-keyring debian-archive-keyring \
        apt-transport-https curl gnupg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    chmod o+r /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy
    say "Caddy installed: $(caddy version | head -1)"
fi

# ---------------------------------------------------------------------------
# 2. Python environment (frozen lock file; no runtime downloads afterwards).
# ---------------------------------------------------------------------------
say "== syncing the voice environment (as ubuntu) =="
sudo -u ubuntu env HOME=/home/ubuntu \
    "${UV_BIN}" sync --frozen --project "${VOICE_PROJECT}"

# ---------------------------------------------------------------------------
# 3. VAD model asset. The command is idempotent: an existing, checksum-valid
#    asset is reused; nothing downloads in the request path.
# ---------------------------------------------------------------------------
say "== preparing the Silero VAD asset =="
sudo -u ubuntu env HOME=/home/ubuntu \
    "${UV_BIN}" run --project "${VOICE_PROJECT}" \
    python -m gnani_coach.analysis.prepare

# ---------------------------------------------------------------------------
# 4. Directories. StateDirectory in the unit also enforces 0700.
# ---------------------------------------------------------------------------
install -d -o root   -g ubuntu -m 0750 "${ENV_DIR}"
install -d -o ubuntu -g ubuntu -m 0700 "${DATA_DIR}"
install -d -o ubuntu -g ubuntu -m 0755 "${APK_DIR}"
install -d -o root   -g root   -m 0700 "${BACKUP_DIR}"

# ---------------------------------------------------------------------------
# 5. Environment file. Create it only when missing, then stop so the two
#    provider keys are filled deliberately (never on a command line).
# ---------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
    install -o root -g ubuntu -m 0640 \
        "${REPO_ROOT}/deploy/voice.env.example" "${ENV_FILE}"
    say ""
    say "Created ${ENV_FILE} from deploy/voice.env.example."
    say "Fill these two lines, then run: sudo systemctl restart gnani-voice"
    say "  GNANI_API_KEY="
    say "  GEMINI_API_KEY="
    exit 0
fi

# Existing file: add any missing non-secret setting from the template, but
# never touch a line that is already present (the keys stay as they are).
say "== completing missing settings in ${ENV_FILE} (values are not printed) =="
while IFS= read -r line; do
    [[ "${line}" =~ ^([A-Z_][A-Z0-9_]*)= ]] || continue
    name="${BASH_REMATCH[1]}"
    if ! grep -q "^${name}=" "${ENV_FILE}"; then
        printf '%s\n' "${line}" >> "${ENV_FILE}"
        say "  added ${name}"
    fi
done < "${REPO_ROOT}/deploy/voice.env.example"
chown root:ubuntu "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"

# Report presence only. A key may be in voice.env or in the optional
# keys.env, which the unit loads second and therefore lets it win.
say "== credential presence =="
for name in GNANI_API_KEY GEMINI_API_KEY; do
    value=""
    if [[ -f "${KEYS_FILE}" ]]; then
        value="$(grep -E "^${name}=" "${KEYS_FILE}" | tail -1 | cut -d= -f2- || true)"
    fi
    if [[ -z "${value}" ]]; then
        value="$(grep -E "^${name}=" "${ENV_FILE}" | tail -1 | cut -d= -f2- || true)"
    fi
    if [[ -n "${value//[[:space:]]/}" ]]; then
        say "  ${name}=SET"
    else
        say "  ${name}=EMPTY (providers will report unavailable; /health still 200)"
    fi
done

# ---------------------------------------------------------------------------
# 6. systemd unit and Caddyfile.
# ---------------------------------------------------------------------------
say "== installing ${UNIT_NAME} =="
install -o root -g root -m 0644 "${UNIT_SRC}" "/etc/systemd/system/${UNIT_NAME}"

say "== installing ${CADDY_DST} (host ${HOST}) =="
install -d -o root -g root -m 0755 /etc/caddy
install -o root -g root -m 0644 "${CADDY_SRC}" "${CADDY_DST}"

say "== validating Caddyfile =="
caddy validate --config "${CADDY_DST}" --adapter caddyfile

say "== validating systemd unit =="
systemd-analyze verify "/etc/systemd/system/${UNIT_NAME}"

systemctl daemon-reload

# ---------------------------------------------------------------------------
# 7. Start. Caddy first (it needs to answer the ACME HTTP-01 challenge), then
#    the voice service.
# ---------------------------------------------------------------------------
say "== starting caddy =="
systemctl enable caddy >/dev/null
systemctl restart caddy

say "== starting ${UNIT_NAME} =="
systemctl enable "${UNIT_NAME}" >/dev/null
systemctl restart "${UNIT_NAME}"

# ---------------------------------------------------------------------------
# 8. Verify. Certificate issuance can take a few seconds; retry.
# ---------------------------------------------------------------------------
say "== local health =="
LOCAL_OK=0
for _ in $(seq 1 15); do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null; then
        LOCAL_OK=1
        break
    fi
    sleep 1
done
if [[ "${LOCAL_OK}" -eq 1 ]]; then
    say "PASS local http://127.0.0.1:8000/health"
else
    say "FAIL local health; recent logs:"
    journalctl -u "${UNIT_NAME}" -n 30 --no-pager || true
    exit 1
fi

say "== public health over TLS (certificate issuance may take ~30 s) =="
PUBLIC_OK=0
for _ in $(seq 1 40); do
    if curl -fsS --max-time 10 "https://${HOST}/health" >/dev/null; then
        PUBLIC_OK=1
        break
    fi
    sleep 3
done
if [[ "${PUBLIC_OK}" -eq 1 ]]; then
    say "PASS https://${HOST}/health"
    say "memory used by ${UNIT_NAME}: $(systemctl show -p MemoryCurrent --value "${UNIT_NAME}") bytes"
    say "INSTALL OK"
else
    say "FAIL https://${HOST}/health (see /var/log/caddy/ and journalctl -u caddy)"
    exit 1
fi
