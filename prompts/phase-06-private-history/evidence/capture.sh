#!/usr/bin/env bash
# Phase 06: capture the evidence of the criteria commands.
#
# The output of every command lands in this folder, one file per command,
# so the report can point at the raw output instead of a summary.
#
# One caveat, recorded honestly: the criterion command
# ``pytest services/voice/tests`` also runs **Phase 05's** tree, and
# their in-flight websocket test hangs while they are still building it
# (see ``pytest-voice-full.txt``). The green run is therefore captured
# with their two directories excluded, and the hang is captured
# separately.
#
# Usage: bash prompts/phase-06-private-history/evidence/capture.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
EVIDENCE="$REPO_ROOT/prompts/phase-06-private-history/evidence"
cd "$REPO_ROOT"

run() {
  local name="$1"
  shift
  echo "=== $name ===" | tee "$EVIDENCE/$name.txt"
  "$@" >> "$EVIDENCE/$name.txt" 2>&1
  local code=$?
  echo "--- exit code: $code ---" | tee -a "$EVIDENCE/$name.txt"
  return 0
}

# The full criterion command, with a wall-clock guard.
run_with_timeout() {
  local name="$1"
  local seconds="$2"
  shift 2
  echo "=== $name ===" | tee "$EVIDENCE/$name.txt"
  python3 - "$seconds" "$@" >> "$EVIDENCE/$name.txt" 2>&1 <<'PY'
import subprocess, sys
seconds = int(sys.argv[1])
command = sys.argv[2:]
try:
    code = subprocess.call(command, timeout=seconds)
    print(f"--- exit code: {code} ---")
except subprocess.TimeoutExpired:
    print(f"--- TIMED OUT after {seconds}s (Phase 05's in-flight tree) ---")
PY
  return 0
}

run_with_timeout pytest-voice-full 180 \
  uv run --project services/voice python -m pytest services/voice/tests -v

run pytest-voice \
  uv run --project services/voice python -m pytest \
  services/voice/tests/identity \
  services/voice/tests/persistence \
  services/voice/tests/foundation \
  services/voice/tests/providers -v

run pytest-integration uv run --project services/voice python -m pytest tests/integration -v
run secret-scan uv run --project services/voice python tools/probes/secret_scan.py
run npm-lint npm run lint
run npm-typecheck npm run typecheck
run npm-build npm run build
run npm-test-contracts npm run test:contracts
run eslint-phase06-files bash -c "cd apps/web && npx eslint src/lib/auth src/app/auth src/proxy.ts && echo 'no findings in the Phase 06 web files'"
run playwright-phase06 npx playwright test --config=prompts/phase-06-private-history/web-tests/playwright.config.ts
run local-postgres-sql bash prompts/phase-06-private-history/evidence/local_postgres_check.sh

echo "the evidence is in $EVIDENCE"
