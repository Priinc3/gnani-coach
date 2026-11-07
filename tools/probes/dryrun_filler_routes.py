"""Offline dry run of the two **live** filler routes (E1 and E2).

What this is
------------
The E1 (Gnani STT) and E2 (Gemini audio review) routes cannot run
without credentials. This script exercises **their code paths** against
fakes — a fake WebSocket transport and a fake Gemini client — so that a
route reported as BLOCKED is known to be *runnable code that is waiting
for a credential*, not code that has never been executed.

What this is **not**
--------------------
It proves **nothing about any provider**. The fakes are written here;
no socket is opened, no request is sent, and no credential is read. The
recognised text it prints is a canned string, not a recognition.

The offline route (E3) is **not** exercised here: it runs for real in
``run.py filler``.

Usage::

    uv run --project services/voice python tools/probes/dryrun_filler_routes.py

The run is recorded as immutable evidence under
``prompts/phase-02-provider-feasibility/evidence/fix-2/``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.probes.evidence import FIX2_EVIDENCE_ROOT, RunEvidence  # noqa: E402

#: A placeholder, never a credential. The fakes do not use it.
PLACEHOLDER = "not-a-real-key"


class FakeTransport:
    """A transport that answers the handshake and one transcript."""

    instances: list["FakeTransport"] = []

    def __init__(self, url: str, headers: dict) -> None:
        self.url = url
        self.headers = headers
        self.sent: list[bytes] = []
        self.control: list[str] = []
        self._transcript_sent = False
        FakeTransport.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def send(self, data):
        if isinstance(data, (bytes, bytearray)):
            self.sent.append(bytes(data))
        else:
            self.control.append(str(data))

    async def recv(self, timeout: float = 30.0):
        await asyncio.sleep(0.01)
        if not self.sent:
            return json.dumps(
                {
                    "type": "connected",
                    "timestamp": "2026-10-20T00:00:00.000Z",
                    "config": {"sample_rate": 16000, "chunk_size": 512},
                }
            )
        if not self._transcript_sent:
            self._transcript_sent = True
            return json.dumps(
                {
                    "type": "transcript",
                    "timestamp": "2026-10-20T00:00:01.000Z",
                    "text": "so um i think the timeline is uh probably next month",
                    "segment_id": "seg-0",
                    "segment_index": 0,
                    "audio_duration_ms": 3600,
                    "latency": 120,
                }
            )
        raise asyncio.TimeoutError

    async def close(self):
        return None


class FakeGemini:
    """A Gemini client that returns one canned JSON review."""

    calls: list[dict] = []

    def __init__(self, api_key: str, http_options=None) -> None:
        self.api_key = api_key
        self.http_options = http_options
        self.aio = self
        self.interactions = self

    async def create(self, **kwargs):
        FakeGemini.calls.append(
            {
                "model": kwargs.get("model"),
                "inputItems": len(kwargs.get("input") or []),
                "store": kwargs.get("store"),
            }
        )

        class Response:
            output_text = json.dumps(
                {
                    "transcript": "So um I think the timeline is, uh, probably next month.",
                    "filled_pauses": [
                        {"word": "um", "start": "00:00", "end": "00:01"},
                        {"word": "uh", "start": "00:02", "end": "00:03"},
                    ],
                }
            )
            steps = []

        return Response()

    async def aclose(self):
        return None

    def close(self):
        return None


def main() -> tuple[int, list[str]]:
    from gnani_coach.providers import stt as stt_mod
    from gnani_coach.providers.limits import ProbeBudget
    from tools.probes import fixtures_io
    from tools.probes.live import filler_experiment as experiment
    from tools.probes.run import Reporter

    stt_mod.WebSocketTransport = FakeTransport
    reporter = Reporter("dryrun-filler-routes", verbose=False)

    manifest = fixtures_io.load_manifest()
    fixture = fixtures_io.resolve_fixture(experiment.FILLER_FIXTURE, manifest)
    negative = fixtures_io.resolve_fixture(experiment.NEGATIVE_FIXTURE, manifest)
    budget = ProbeBudget(max_operations=16)

    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text)

    say("== offline dry run of E1 and E2 (fakes only; no provider is contacted) ==")
    say("")
    say("-- E1: one unbiasved variant --")
    e1 = asyncio.run(
        experiment._run_e1(
            list(experiment.STT_VARIANTS)[:1],
            fixture,
            PLACEHOLDER,
            "en-IN",
            budget,
            reporter,
        )
    )
    row = e1[0]
    transport = FakeTransport.instances[-1]
    say(f"  status         : {row.status}")
    say(f"  observed text  : {row.observed_text!r}   (canned by the fake transport)")
    say(f"  um / uh        : {row.um_present} / {row.uh_present}")
    say(f"  wire attempts  : {row.wire_attempts}")
    say(f"  frames sent    : {len(transport.sent)}")
    say(f"  headers        : {json.dumps(_safe_headers(transport.headers))}")

    say("")
    say("-- E1: one boosted variant --")
    e1_boost = asyncio.run(
        experiment._run_e1(
            [experiment.STT_VARIANTS[3]],
            fixture,
            PLACEHOLDER,
            "en-IN",
            budget,
            reporter,
        )
    )
    transport = FakeTransport.instances[-1]
    say(f"  status         : {e1_boost[0].status}")
    say(f"  boost headers  : {json.dumps(_safe_headers(transport.headers))}")
    say(f"  control frame  : {transport.control}")
    say(f"  boost echo     : {e1_boost[0].notes[-1]}")

    say("")
    say("-- E2: the audio review --")
    import google.genai as genai

    genai.Client = FakeGemini
    e2 = asyncio.run(
        experiment._run_e2(
            fixture,
            negative,
            "gemini-3.8-flash",
            PLACEHOLDER,
            budget,
            reporter,
        )
    )
    for row in e2:
        say(f"  {row.variant}: status={row.status} um={row.um_present} uh={row.uh_present}")
        say(f"    positions: {json.dumps(row.positions)}")
    say(f"  fake client calls: {json.dumps(FakeGemini.calls)}")

    say("")
    say(f"  budget: {json.dumps(budget.summary())}")
    say("")
    say("  NOTE: the fake transport returns a canned transcript and the fake")
    say("  client a canned review. This proves the routes' code runs end to end;")
    say("  it proves nothing about any provider, and no request was sent.")
    return 0, lines


def _safe_headers(headers: dict) -> dict:
    """The headers with the credential value dropped."""
    return {
        name: ("<dropped>" if name.lower() == "x-api-key-id" else value)
        for name, value in headers.items()
    }


if __name__ == "__main__":
    evidence = RunEvidence(
        "dryrun-filler-routes", cwd=str(REPO_ROOT), root=FIX2_EVIDENCE_ROOT
    )
    with evidence:
        code, output = main()
        evidence.finish(
            exit_code=code,
            overall="PASSED" if code == 0 else "FAILED",
            stdout="\n".join(output),
            stderr="",
            notes=[
                "fakes only: no socket, no request, no credential read",
            ],
        )
    sys.exit(code)
