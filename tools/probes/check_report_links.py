"""Check that every relative link in the Phase 02 report resolves.

A relative Markdown link is relative to the **file that contains it**.
The FIX-1 brief asked for the report's document links to be "fixed" with
a three-level remedy. That remedy was checked against the filesystem
and does **not** resolve from
``prompts/phase-02-provider-feasibility/`` — the repository root is two
levels up from there.

This tool is the check, so the claim is verifiable rather than asserted.
It reports only paths and outcomes; it never prints file contents.

Usage::

    uv run --project services/voice python tools/probes/check_report_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "prompts" / "phase-02-provider-feasibility" / "REPORT.md"

#: A Markdown link target: `(target)` or `(target "title")`.
_LINK_RE = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

#: Targets that are not files on disk.
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")


def check(report: Path = REPORT) -> list[tuple[str, str, str]]:
    """Return (target, status, detail) for every relative link."""
    if not report.is_file():
        raise SystemExit(f"report not found: {report}")
    text = report.read_text(encoding="utf-8")
    base = report.parent
    results: list[tuple[str, str, str]] = []
    for match in _LINK_RE.finditer(text):
        target = match.group(1)
        if target.startswith(SKIP_PREFIXES):
            continue
        candidate = (base / target).resolve()
        if candidate.exists():
            results.append((target, "OK", ""))
            continue
        # Try the repository-root-relative form as a second chance.
        alt = (REPO_ROOT / target.lstrip("./")).resolve()
        if alt.exists():
            results.append((target, "OK-ALT", str(alt.relative_to(REPO_ROOT))))
            continue
        results.append((target, "MISSING", "not found relative to the report"))
    return results


def main() -> int:
    results = check()
    broken = [row for row in results if row[1] == "MISSING"]
    for target, status, detail in results:
        suffix = f"  ({detail})" if detail else ""
        print(f"  {status:<9} {target}{suffix}")
    print()
    print(f"links checked: {len(results)}  broken: {len(broken)}")
    if broken:
        return 1
    print("every relative link in the report resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
