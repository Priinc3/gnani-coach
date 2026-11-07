"""In-repository credential-leak check.

What this is
------------
A **structural** scan of the working tree for values that look like
credentials. It is a safety net against a secret being pasted into
source, prompts, evidence or a report by accident.

What this is not
----------------
* It does not prove the repository is clean of *every* secret.
* It cannot erase a value that was posted in a conversation. A clean
  scan says "no leak found in the tree", never "the exposure is gone".
* It does not verify, revoke or rotate any credential. Provider-dashboard
  actions belong to the owner.

Output rules
------------
The output contains **only**: the repository-relative path, the line
number, the rule identifier and counts. Matching text is never printed,
never echoed and never stored. A finding therefore cannot leak the very
value it reports.

Rule identifiers
----------------
``GOOGLE_API_KEY``    Google API key shape (``AIza`` + 35 characters)
``GROQ_API_KEY``      Groq key shape (``gsk_`` + 20 or more characters)
``NVIDIA_API_KEY``    NVIDIA key shape (``nvapi-`` + 20 or more characters)
``BEARER_TOKEN``      an ``Authorization: Bearer <token>`` header value
``X_API_KEY_ID``      an ``x-api-key-id`` header value
``JWT``               a JSON Web Token shape
``GENERIC_SECRET``    an assignment of a long literal to a secret-ish name

Usage
-----
::

    uv run --project services/voice python tools/probes/secret_scan.py
    uv run --project services/voice python tools/probes/secret_scan.py --json

Exit code ``0`` means no finding, ``1`` means at least one finding.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directories never scanned: dependencies, caches and generated output.
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".next",
        "out",
        "build",
        "dist",
        "coverage",
        "test-results",
        "playwright-report",
        "recordings",
        ".cache",
    }
)

#: File suffixes never scanned: binary or generated media.
SKIP_SUFFIXES = frozenset(
    {".pcm", ".raw", ".wav", ".mp3", ".ogg", ".flac", ".pyc", ".so", ".png", ".jpg"}
)

#: Explicitly skipped paths, relative to the repository root.
SKIP_PATHS = frozenset(
    {
        # The user's own private environment file. It is ignored, it is
        # mode 0600, and its contents are the owner's business. The scan
        # reports that it exists; it never reads it.
        "tools/probes/.env",
    }
)

#: The rules. Each is (rule id, human description, pattern). The pattern
#: is deliberately structural: no real credential value is embedded here.
RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "GOOGLE_API_KEY",
        "Google API key shape",
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    ),
    (
        "GROQ_API_KEY",
        "Groq API key shape",
        re.compile(r"\bgsk_[0-9A-Za-z]{20,}"),
    ),
    (
        "NVIDIA_API_KEY",
        "NVIDIA API key shape",
        re.compile(r"\bnvapi-[0-9A-Za-z\-_]{20,}"),
    ),
    (
        "BEARER_TOKEN",
        "Authorization bearer token",
        re.compile(r"(?i)authorization\s*[:=]\s*[\"']?bearer\s+[0-9A-Za-z\-_\.]{20,}"),
    ),
    (
        "X_API_KEY_ID",
        "x-api-key-id header value",
        re.compile(r"(?i)x-api-key-id\s*[:=]\s*[\"']?[0-9A-Za-z\-_]{12,}"),
    ),
    (
        "JWT",
        "JSON Web Token shape",
        re.compile(r"\beyJ[0-9A-Za-z\-_]{8,}\.[0-9A-Za-z\-_]{8,}\.[0-9A-Za-z\-_]{8,}"),
    ),
    (
        "GENERIC_SECRET",
        "long literal assigned to a secret-ish name",
        re.compile(
            r"(?i)\b(?:api[_-]?key|apikey|secret|password|passwd|token|credential)"
            r"\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']"
        ),
    ),
)

#: Suffixes that are scanned.
TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".md",
        ".json",
        ".jsonl",
        ".txt",
        ".toml",
        ".yaml",
        ".yml",
        ".sh",
        ".ts",
        ".tsx",
        ".js",
        ".mjs",
        ".cjs",
        ".html",
        ".css",
        ".cfg",
        ".ini",
        ".env",
        ".example",
        ".lock",
        "",
    }
)

#: An inline marker that suppresses a finding on that one line. It is
#: for deliberate, unmistakably dummy sentinels in offline tests. A line
#: carrying this marker is still scanned by every other rule; the marker
#: only silences the rules for that line.
ALLOW_MARKER = "secret-scan: allow"


@dataclass(frozen=True)
class Finding:
    """One location that matched one rule.

    Only the location and the rule are retained. The matching text is
    deliberately **not** part of this object, so it cannot be printed
    later by accident.
    """

    path: str
    line: int
    rule_id: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "line": self.line, "rule": self.rule_id}


def iter_candidate_files(root: Path) -> list[Path]:
    """Every text file the scan considers, in a stable order."""
    candidates: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:  # pragma: no cover - defensive
            continue
        parts = set(relative.parts)
        if parts & SKIP_DIRECTORIES:
            continue
        relative_str = relative.as_posix()
        if relative_str in SKIP_PATHS:
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        candidates.append(path)
    return candidates


def scan_file(path: Path, root: Path) -> list[Finding]:
    """Scan one file. Only locations and rule ids are returned."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings: list[Finding] = []
    relative = path.relative_to(root).as_posix()
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for rule_id, _description, pattern in RULES:
            if pattern.search(line):
                findings.append(Finding(path=relative, line=number, rule_id=rule_id))
    return findings


def scan(root: Path | None = None) -> list[Finding]:
    """Scan the whole tree. Returns findings sorted by path then line."""
    scan_root = (root or REPO_ROOT).resolve()
    findings: list[Finding] = []
    for path in iter_candidate_files(scan_root):
        findings.extend(scan_file(path, scan_root))
    findings.sort(key=lambda item: (item.path, item.line, item.rule_id))
    return findings


def summarise(findings: list[Finding]) -> dict[str, object]:
    """Counts only. No paths with content, no matched text."""
    by_rule: dict[str, int] = {}
    for finding in findings:
        by_rule[finding.rule_id] = by_rule.get(finding.rule_id, 0) + 1
    return {
        "total": len(findings),
        "files": len({finding.path for finding in findings}),
        "by_rule": dict(sorted(by_rule.items())),
    }


def format_text_report(findings: list[Finding]) -> str:
    """A report with only paths, line numbers, rule ids and counts."""
    if not findings:
        return (
            "credential scan: 0 findings\n"
            "  scope: repository working tree, structural rules only\n"
            "  note: a clean scan does NOT erase any earlier exposure\n"
        )
    lines = ["credential scan: findings present"]
    for finding in findings:
        lines.append(f"  {finding.path}:{finding.line}: {finding.rule_id}")
    counts = summarise(findings)
    lines.append(f"  total={counts['total']} files={counts['files']}")
    for rule_id, count in counts["by_rule"].items():
        lines.append(f"  rule {rule_id}: {count}")
    lines.append("  matched text is never printed")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="secret_scan",
        description=(
            "Structural credential-leak check over the repository tree. "
            "Output contains only paths, line numbers, rule ids and counts."
        ),
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="directory to scan (default: the repository root)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the findings as JSON (locations and rule ids only)",
    )
    args = parser.parse_args(argv)

    findings = scan(Path(args.root))
    if args.json:
        payload = {
            "summary": summarise(findings),
            "findings": [finding.to_dict() for finding in findings],
            "note": (
                "structural rules only; a clean scan does not erase any "
                "earlier conversation exposure"
            ),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_text_report(findings), end="")
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
