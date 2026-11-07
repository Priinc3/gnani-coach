"""Immutable run evidence.

Every invocation writes to a **new** directory named by a run id. A prior
success, a prior failure and a prior cancellation are all preserved; a
second run of the same command never overwrites the first.

Layout::

    evidence/fix-1/<run-id>/
        run.json          command, cwd, runtime, exit code, timing, verdict
        stdout.txt        full redacted stdout
        stderr.txt        full redacted stderr
        result.json       machine-readable stage results, when any

``evidence/fix-2/<run-id>/`` has the same layout. The two fix cycles keep
separate directories: a fix-2 run never writes into fix-1's history.

A run id is ``<utc-timestamp>-<command>-<short-hash>``. The hash covers
the command, the working directory and the recorded arguments, so two
different invocations cannot collide and the same invocation is still
distinguishable by its timestamp.

Redaction is applied on the way in: the same policy the adapters use, so
an evidence file can never become a leak path.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from gnani_coach.providers.redaction import redact_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "prompts" / "phase-02-provider-feasibility" / "evidence"
FIX_EVIDENCE_ROOT = EVIDENCE_ROOT / "fix-1"
#: The bounded filler experiment (FIX cycle 2) keeps its own immutable
#: run directories, exactly like fix-1, and never writes into fix-1's.
FIX2_EVIDENCE_ROOT = EVIDENCE_ROOT / "fix-2"

#: Characters that are safe inside a run id on every supported platform.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(value: str) -> str:
    return _UNSAFE.sub("-", value).strip("-") or "run"


def new_run_id(command: str, argv: list[str], cwd: str) -> str:
    """A unique, sortable, collision-resistant run identifier."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(
        "\x00".join([command, cwd, *argv]).encode("utf-8")
    ).hexdigest()[:10]
    unique = uuid.uuid4().hex[:6]
    return f"{stamp}-{_slug(command)}-{digest}-{unique}"


@dataclass
class RunRecord:
    """Everything needed to reproduce and to place one invocation."""

    run_id: str
    command: str
    argv: list[str]
    cwd: str
    started_utc: str
    finished_utc: str = ""
    runtime_seconds: float = 0.0
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    platform: str = field(default_factory=lambda: sys.platform)
    exit_code: int | None = None
    overall: str = ""
    allow_live: bool = False
    notes: list[str] = field(default_factory=list)
    attempt_accounting: dict | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "runId": self.run_id,
            "command": self.command,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "startedUtc": self.started_utc,
            "finishedUtc": self.finished_utc,
            "runtimeSeconds": round(self.runtime_seconds, 3),
            "runtime": {
                "python": self.python_version,
                "platform": self.platform,
            },
            "exitCode": self.exit_code,
            "overall": self.overall,
            "allowLive": self.allow_live,
            "attemptAccounting": self.attempt_accounting,
            "notes": list(self.notes),
        }


class RunEvidence:
    """A single invocation's evidence directory. Never overwrites."""

    def __init__(
        self,
        command: str,
        argv: list[str] | None = None,
        *,
        cwd: str | None = None,
        root: Path | None = None,
    ) -> None:
        argv = list(argv if argv is not None else sys.argv[1:])
        cwd = cwd or str(Path.cwd())
        self.record = RunRecord(
            run_id=new_run_id(command, argv, cwd),
            command=command,
            argv=argv,
            cwd=cwd,
            started_utc=utcnow(),
        )
        base = (root or FIX_EVIDENCE_ROOT) / self.record.run_id
        self.root = base.parent
        # O_EXCL semantics: refuse to reuse a directory rather than
        # clobbering an earlier run's evidence.
        self.directory = base
        suffix = 1
        while self.directory.exists():
            self.directory = base.with_name(f"{base.name}-{suffix}")
            suffix += 1
        self.record.run_id = self.directory.name
        self._started = datetime.now(UTC)
        #: A run directory is written exactly once. A second call is a
        #: no-op, so the context-manager's automatic finish cannot
        #: overwrite the explicit one with empty fields.
        self._finalized = False

    # -- lifecycle ----------------------------------------------------
    def __enter__(self) -> RunEvidence:
        self.directory.mkdir(parents=True, exist_ok=False)
        return self

    def __exit__(self, *_exc: object) -> None:
        self.finish()

    def finish(
        self,
        *,
        exit_code: int | None = None,
        overall: str = "",
        stdout: str = "",
        stderr: str = "",
        attempt_accounting: dict | None = None,
        result: dict | None = None,
        notes: list[str] | None = None,
    ) -> Path:
        """Write the immutable run directory. Safe to call once.

        Calling it again is a no-op: the recorded exit code, overall
        state and index entry are never rewritten.
        """
        if self._finalized:
            return self.directory
        self._finalized = True
        self.record.finished_utc = utcnow()
        self.record.runtime_seconds = (
            datetime.now(UTC) - self._started
        ).total_seconds()
        if exit_code is not None:
            self.record.exit_code = exit_code
        self.record.overall = overall
        self.record.attempt_accounting = attempt_accounting
        if notes:
            self.record.notes = list(notes)

        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "stdout.txt").write_text(
            redact_evidence(stdout, max_length=4_000_000), encoding="utf-8"
        )
        (self.directory / "stderr.txt").write_text(
            redact_evidence(stderr, max_length=4_000_000), encoding="utf-8"
        )
        if result is not None:
            (self.directory / "result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        (self.directory / "run.json").write_text(
            json.dumps(self.record.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.index_entry()
        return self.directory

    # -- index --------------------------------------------------------
    def index_entry(self) -> None:
        """Append one line to the append-only fix-1 index."""
        index = self.root / "run-index.jsonl"
        index.parent.mkdir(parents=True, exist_ok=True)
        try:
            path = str(self.directory.relative_to(REPO_ROOT))
        except ValueError:
            path = str(self.directory)
        line = json.dumps(
            {
                "runId": self.record.run_id,
                "recordedAt": self.record.finished_utc,
                "command": self.record.command,
                "cwd": self.record.cwd,
                "exitCode": self.record.exit_code,
                "overall": self.record.overall,
                "allowLive": self.record.allow_live,
                "runtimeSeconds": round(self.record.runtime_seconds, 3),
                "attemptAccounting": self.record.attempt_accounting,
                "path": path,
            },
            sort_keys=True,
            default=str,
        )
        with index.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def relative(self) -> str:
        try:
            return str(self.directory.relative_to(REPO_ROOT))
        except ValueError:
            return str(self.directory)


def summarise_attempts(budget) -> dict:
    """The attempt accounting, in a form safe for the report and the index."""
    if budget is None:
        return {"status": "no budget object was attached to this run"}
    summary = budget.summary()
    summary["unknownNote"] = (
        "runs recorded before wire-attempt accounting carry "
        "'unknown' wire attempts and are never reconstructed as zero"
    )
    return summary


def ledger_totals(root: Path | None = None) -> dict:
    """Reconcile the append-only index into totals, without hiding failures."""
    index = (root or FIX_EVIDENCE_ROOT) / "run-index.jsonl"
    if not index.is_file():
        return {"runs": 0, "source": "no fix-1 index yet"}
    entries: list[dict] = []
    for line in index.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"overall": "UNPARSEABLE"})
    totals: dict[str, object] = {
        "runs": len(entries),
        "successful_runs": sum(1 for e in entries if e.get("exitCode") == 0),
        "failed_or_blocked_runs": sum(1 for e in entries if e.get("exitCode") not in (0, None)),
        "cancelled_runs": sum(1 for e in entries if e.get("overall") == "CANCELLED"),
        "by_command": {},
        "measured_wire_attempts": 0,
        "unmeasured_wire_attempts": [],
    }
    commands: dict[str, int] = {}
    for entry in entries:
        key = str(entry.get("command", "?"))
        commands[key] = commands.get(key, 0) + 1
        accounting = entry.get("attemptAccounting") or {}
        used = accounting.get("wire_attempts_used")
        if isinstance(used, int):
            totals["measured_wire_attempts"] = int(totals["measured_wire_attempts"]) + used
        elif used == "unknown":
            totals["unmeasured_wire_attempts"].append(entry.get("runId"))
    totals["by_command"] = dict(sorted(commands.items()))
    return totals


def environment() -> dict[str, object]:
    """Runtime facts recorded with every run."""
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "cwd": os.getcwd(),
        "utc": utcnow(),
    }
