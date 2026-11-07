#!/usr/bin/env bash
# Phase 02 evidence capture. Runs the offline command contract and the batch
# entry points, recording exact commands, runtime versions, exit statuses and
# full output. No secrets are printed and nothing is staged or committed.
set -u
EV="prompts/phase-02-provider-feasibility/evidence"
mkdir -p "$EV"

hdr() {
  echo "=============================================================="
  echo "command : $1"
  echo "cwd     : $(pwd)"
  echo "utc     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "python  : $(uv run --project services/voice python --version 2>&1)"
  echo "node    : $(node --version 2>&1)  npm: $(npm --version 2>&1)"
  echo "=============================================================="
}

cap() { # cap <outfile> <command...>
  local out="$1"; shift
  { hdr "$*"; echo; "$@" 2>&1; echo; echo "--- exit status: $? ---"; } > "$out"
  echo "captured $out"
}

{
  echo "# Phase 02 environment capture"
  echo "utc        : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "cwd        : $(pwd)"
  echo "toplevel   : $(git rev-parse --show-toplevel)"
  echo "uname      : $(uname -srm)"
  echo "uv         : $(uv --version)"
  echo "node       : $(node --version)"
  echo "npm        : $(npm --version)"
  echo
  echo "--- python packages in services/voice ---"
  uv run --project services/voice python - <<'PY' 2>&1
import importlib.metadata as m
names = {"gnani-coach","websockets","google-genai","numpy","onnxruntime","fastapi","pydantic","pydantic-settings","uvicorn","pytest","httpx2","jsonschema"}
rows=[]
for d in m.distributions():
    n=(d.metadata["Name"] or "").lower()
    if n in {x.lower() for x in names}:
        rows.append(f"{d.metadata['Name']}=={d.version}")
print("\n".join(sorted(rows)))
PY
  echo
  echo "--- symlinks under version control scope ---"
  find . -type l -not -path "./node_modules/*" -not -path "./services/voice/.venv/*" -not -path "./.git/*" 2>/dev/null | head -20
  echo "(none listed above means no symlinks found)"
  echo
  echo "--- git status (nothing staged) ---"
  git status --porcelain
} > "$EV/00-environment.txt"
echo "captured $EV/00-environment.txt"

cap "$EV/01-uv-sync.txt"            uv sync --project services/voice
cap "$EV/02-probe-help.txt"         uv run --project services/voice python tools/probes/run.py --help
cap "$EV/03-preflight-offline.txt"  uv run --project services/voice python tools/probes/run.py preflight
cap "$EV/04-fixtures-offline.txt"   uv run --project services/voice python tools/probes/run.py fixtures --offline
cap "$EV/05-analysis-offline.txt"   uv run --project services/voice python tools/probes/run.py analysis --offline
cap "$EV/06-analysis-allow-live.txt" uv run --project services/voice python tools/probes/run.py analysis --allow-live
cap "$EV/07-pytest-services.txt"    uv run --project services/voice python -m pytest services/voice/tests -q
cap "$EV/08-capabilities-build.txt" uv run --project services/voice python tools/probes/capabilities.py
echo "--- done ---"
