"""Capture the FIX-1 verification commands as immutable run evidence.

Each command runs as a subprocess. Its exact argv, working directory,
runtime, exit code and **full redacted stdout/stderr** are written to a
fresh directory under
``prompts/phase-02-provider-feasibility/evidence/fix-1/<run-id>/``.
Nothing is ever overwritten: a prior success, a prior failure and a
prior cancellation all stay on disk.

The commands are the four the FIX-1 brief names, plus the credential
leak scan. Every one of them is offline: no inference call, no socket,
no credential is read.

Usage::

    uv run --project services/voice python tools/probes/capture_fix1_evidence.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.probes.evidence import FIX_EVIDENCE_ROOT, RunEvidence, ledger_totals  # noqa: E402

#: The verification commands, in the order the FIX-1 brief lists them.
COMMANDS: tuple[tuple[str, list[str]], ...] = (
    (
        "pytest-providers",
        [
            "uv",
            "run",
            "--project",
            "services/voice",
            "python",
            "-m",
            "pytest",
            "services/voice/tests/providers",
            "-v",
        ],
    ),
    (
        "pytest-services",
        [
            "uv",
            "run",
            "--project",
            "services/voice",
            "python",
            "-m",
            "pytest",
            "services/voice/tests",
            "-v",
        ],
    ),
    ("test-contracts", ["npm", "run", "test:contracts"]),
    (
        "preflight",
        [
            "uv",
            "run",
            "--project",
            "services/voice",
            "python",
            "tools/probes/run.py",
            "preflight",
        ],
    ),
    (
        "secret-scan",
        [
            "uv",
            "run",
            "--project",
            "services/voice",
            "python",
            "tools/probes/secret_scan.py",
        ],
    ),
    (
        "report-links",
        [
            "uv",
            "run",
            "--project",
            "services/voice",
            "python",
            "tools/probes/check_report_links.py",
        ],
    ),
)


def capture(name: str, argv: list[str]) -> tuple[int, Path]:
    """Run one command and record it. Returns (exit code, run directory)."""
    evidence = RunEvidence(name, argv, cwd=str(REPO_ROOT))
    with evidence:
        started = time.time()
        completed = subprocess.run(  # noqa: S603 - a fixed, local command list
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        elapsed = time.time() - started
        overall = "PASSED" if completed.returncode == 0 else "FAILED"
        evidence.finish(
            exit_code=completed.returncode,
            overall=overall,
            stdout=completed.stdout,
            stderr=completed.stderr,
            notes=[
                f"command: {name}",
                f"wall_clock_seconds: {elapsed:.3f}",
                "offline: no inference call, no socket, no credential read",
            ],
        )
    return completed.returncode, evidence.directory


def main() -> int:
    print(f"evidence root: {FIX_EVIDENCE_ROOT.relative_to(REPO_ROOT)}")
    results: list[tuple[str, int, Path]] = []
    for name, argv in COMMANDS:
        print(f"running {name} …", flush=True)
        code, directory = capture(name, argv)
        print(f"  exit={code}  {directory.relative_to(REPO_ROOT)}")
        results.append((name, code, directory))

    totals = ledger_totals()
    print()
    print(f"runs recorded in this capture: {len(results)}")
    for name, code, _directory in results:
        print(f"  {name}: exit {code}")
    print()
    print("fix-1 ledger totals:")
    for key, value in totals.items():
        print(f"  {key}: {value}")

    failed = [name for name, code, _ in results if code != 0]
    if failed:
        print()
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print()
    print("all verification commands exited 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
