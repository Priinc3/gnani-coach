#!/usr/bin/env python3
"""Fill the REPORT's placeholders from the immutable fix-1 ledger.

Run after the final verification capture. Every value it writes comes
from an evidence file or from the ledger — nothing is invented.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIX = REPO_ROOT / "prompts" / "phase-02-provider-feasibility" / "evidence" / "fix-1"
REPORT = REPO_ROOT / "prompts" / "phase-02-provider-feasibility" / "REPORT.md"
INDEX = FIX / "run-index.jsonl"


def latest(command: str) -> dict:
    rows = [
        json.loads(line)
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching = [row for row in rows if row.get("command") == command]
    if not matching:
        raise SystemExit(f"no run recorded for {command}")
    return matching[-1]


def stdout_of(run: dict) -> str:
    return (REPO_ROOT / run["path"] / "stdout.txt").read_text(encoding="utf-8")


def main() -> int:
    providers = latest("pytest-providers")
    services = latest("pytest-services")
    contracts = latest("test-contracts")
    preflight = latest("preflight")
    scan = latest("secret-scan")
    analysis = latest("analysis")
    links = latest("report-links")

    providers_out = stdout_of(providers)
    services_out = stdout_of(services)
    preflight_out = stdout_of(preflight)

    def summary(text: str) -> tuple[str, str]:
        match = re.search(r"=+ (\d+ passed, \d+ skipped) in (\S+) =+", text)
        if not match:
            raise SystemExit("could not read the pytest summary")
        return match.group(1), match.group(2)

    providers_count, providers_time = summary(providers_out)
    services_count, services_time = summary(services_out)

    elapsed = re.search(r"elapsed_s   : (\S+)", preflight_out)
    started = re.search(r"started_utc  : (\S+)", preflight_out)
    index_count = re.search(r"run index   : (\d+) invocations", preflight_out)
    if not (elapsed and started and index_count):
        raise SystemExit("could not read the preflight summary")

    rows = [
        json.loads(line)
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("command"))
        counts[key] = counts.get(key, 0) + 1

    replacements = {
        "__P_PROVIDERS__": providers["runId"],
        "__P_SERVICES__": services["runId"],
        "__P_CONTRACTS__": contracts["runId"],
        "__P_PREFLIGHT__": preflight["runId"],
        "__P_SCAN__": scan["runId"],
        "__P_LINKS__": links["runId"],
        "__P_PREFLIGHT_ID__": preflight["runId"],
        "__P_PREFLIGHT_UTC__": started.group(1),
        "__P_PREFLIGHT_ELAPSED__": elapsed.group(1),
        "__P_INDEX_COUNT__": index_count.group(1),
        "__P_PROVIDERS_COUNT__": providers_count,
        "__P_PROVIDERS_TIME__": providers_time,
        "__P_SERVICES_COUNT__": services_count,
        "__P_SERVICES_TIME__": services_time,
        "__N_PROVIDERS__": str(counts.get("pytest-providers", 0)),
        "__N_SERVICES__": str(counts.get("pytest-services", 0)),
        "__N_CONTRACTS__": str(counts.get("test-contracts", 0)),
        "__N_PREFLIGHT__": str(counts.get("preflight", 0)),
        "__N_SCAN__": str(counts.get("secret-scan", 0)),
        "__N_LINKS__": str(counts.get("report-links", 0)),
        "__N_ANALYSIS__": str(counts.get("analysis", 0)),
        "__N_TOTAL__": str(len(rows)),
    }

    text = REPORT.read_text(encoding="utf-8")
    if "--reset" in sys.argv:
        text = reset(text)
    for key, value in replacements.items():
        text = text.replace(key, value)
    REPORT.write_text(text, encoding="utf-8")

    leftovers = re.findall(r"__[A-Z_]+__", text)
    if leftovers:
        raise SystemExit(f"unfilled placeholders remain: {sorted(set(leftovers))}")
    print(f"patched {REPORT.relative_to(REPO_ROOT)}")
    print(f"  fix-1 ledger runs: {len(rows)}")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")
    return 0


#: The command whose run id replaces each placeholder.
_PLACEHOLDER_COMMAND = {
    "__P_PROVIDERS__": "pytest-providers",
    "__P_SERVICES__": "pytest-services",
    "__P_CONTRACTS__": "test-contracts",
    "__P_PREFLIGHT__": "preflight",
    "__P_SCAN__": "secret-scan",
    "__P_LINKS__": "report-links",
}


def reset(text: str) -> str:
    """Turn the filled-in values back into placeholders.

    The report is regenerated from the ledger on every cycle, so the
    reset has to work from the values currently in the file rather than
    from a saved template.
    """
    rows = [
        json.loads(line)
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    known: dict[str, str] = {}
    for row in rows:
        run_id = str(row.get("runId"))
        command = str(row.get("command"))
        for placeholder, wanted in _PLACEHOLDER_COMMAND.items():
            if command == wanted:
                known[run_id] = placeholder
        known[run_id] = known.get(run_id, run_id)

    # Longest first, so a run id is not partially replaced.
    for run_id in sorted(known, key=len, reverse=True):
        placeholder = known[run_id]
        if placeholder == run_id:
            continue
        text = text.replace(run_id, placeholder)

    text = re.sub(
        r"run_id       : 20261020T\d{6}Z-preflight-[0-9a-f]{10}-[0-9a-f]{6}",
        "run_id       : __P_PREFLIGHT_ID__",
        text,
    )
    text = re.sub(
        r"started_utc  : \S+", "started_utc  : __P_PREFLIGHT_UTC__", text
    )
    text = re.sub(r"elapsed_s   : \S+", "elapsed_s   : __P_PREFLIGHT_ELAPSED__", text)
    text = re.sub(
        r"run index   : \d+ invocations recorded",
        "run index   : __P_INDEX_COUNT__ invocations recorded",
        text,
    )
    text = re.sub(
        r"=+ \d+ passed, \d+ skipped in \S+ =+",
        "======================== __P_PROVIDERS_COUNT__ in __P_PROVIDERS_TIME__ ========================",
        text,
    )
    text = re.sub(
        r"\| Provider test suite \| \*\*\d+ passed, \d+ skipped\*\* \|",
        "| Provider test suite | **__P_PROVIDERS_COUNT__** |",
        text,
    )
    text = re.sub(
        r"\| Full voice suite \| \*\*\d+ passed, \d+ skipped\*\* \|",
        "| Full voice suite | **__P_SERVICES_COUNT__** |",
        text,
    )
    text = re.sub(
        r"\| `pytest-providers` \| \d+ \|",
        "| `pytest-providers` | __N_PROVIDERS__ |",
        text,
    )
    text = re.sub(
        r"\| `pytest-services` \| \d+ \|", "| `pytest-services` | __N_SERVICES__ |", text
    )
    text = re.sub(
        r"\| `test-contracts` \| \d+ \|", "| `test-contracts` | __N_CONTRACTS__ |", text
    )
    text = re.sub(r"\| `preflight` \| \d+ \|", "| `preflight` | __N_PREFLIGHT__ |", text)
    text = re.sub(r"\| `secret-scan` \| \d+ \|", "| `secret-scan` | __N_SCAN__ |", text)
    text = re.sub(
        r"\| `report-links` \| \d+ \|", "| `report-links` | __N_LINKS__ |", text
    )
    text = re.sub(
        r"\| `analysis --offline` \| \d+ \|", "| `analysis --offline` | __N_ANALYSIS__ |", text
    )
    text = re.sub(
        r"\| \*\*Total\*\* \| \*\*\d+\*\* \|", "| **Total** | **__N_TOTAL__** |", text
    )
    text = re.sub(
        r"All \d+ runs exited 0", "All __N_TOTAL__ runs exited 0", text
    )
    text = re.sub(
        r"\d+ immutable run directories", "__N_TOTAL__ immutable run directories", text
    )
    # The second pytest summary line (the services run) needs its own pair.
    parts = text.split(
        "======================== __P_PROVIDERS_COUNT__ in __P_PROVIDERS_TIME__ ========================"
    )
    if len(parts) == 3:
        text = (
            parts[0]
            + "======================== __P_PROVIDERS_COUNT__ in __P_PROVIDERS_TIME__ ========================"
            + parts[1]
            + "======================== __P_SERVICES_COUNT__ in __P_SERVICES_TIME__ ========================"
            + parts[2]
        )
    return text


if __name__ == "__main__":
    raise SystemExit(main())
