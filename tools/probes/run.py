#!/usr/bin/env python
"""Root-invoked diagnostic probe CLI for Phase 02 provider feasibility.

    uv run --project services/voice python tools/probes/run.py --help

Design commitments
------------------
* **No import-time work.** Importing this module performs no inference,
  opens no socket, captures no microphone and downloads no model asset.
* **Live requires ``--allow-live``.** Without it a command that would need
  a provider refuses and exits nonzero.
* **Content-free default output.** Names and counts, never secret values,
  never audio, never learner or model prose in the operational stream.
* **Honest states.** ``PASSED`` / ``FAILED`` / ``BLOCKED`` / ``NOT RUN`` /
  ``INCONCLUSIVE``. A missing key never becomes a simulated pass.
* **Bounded.** 40 provider operations and 300 s of STT audio per live
  invocation, at most two retries per transient operation, bounded
  timeouts and queues. An over-limit plan is refused *before* the first
  call.
* **Aggregate run index.** Every invocation appends a content-free record
  to ``tools/probes/.cache/runs.jsonl`` so repeated invocations stay
  visible rather than overwriting one another.

Commands
--------
``preflight``   configuration/endpoint diagnostics. Never calls a provider.
``fixtures``    build or inventory the synthetic fixture set.
``speech``      bounded Gnani STT probe over prepared fixtures.
``chain``       one real STT -> Gemini -> TTS chained turn.
``matrix``      the ten catalog languages plus Hinglish.
``analysis``    offline audio measurement, or an explicit model prepare.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import platform
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_PROJECT = REPO_ROOT / "services" / "voice"
CACHE_DIR = REPO_ROOT / "tools" / "probes" / ".cache"
RUN_INDEX = CACHE_DIR / "runs.jsonl"
EVIDENCE_DIR = REPO_ROOT / "prompts" / "phase-02-provider-feasibility" / "evidence"

# Make the service importable when invoked from the repository root.
sys.path.insert(0, str(VOICE_PROJECT / "src"))
sys.path.insert(0, str(REPO_ROOT))

PASSED = "PASSED"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
NOT_RUN = "NOT RUN"
INCONCLUSIVE = "INCONCLUSIVE"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2

#: The reasoning adapter's documented defaults, mirrored here so the CLI
#: shows exactly the numbers the adapter uses.
DEFAULT_ATTEMPT_TIMEOUT_S = 15.0
DEFAULT_DEADLINE_S = 45.0

#: Secret *names* only. Values are never read into a message.
REQUIRED_SECRET_NAMES = ("GNANI_API_KEY", "GEMINI_API_KEY")
OPTIONAL_SECRET_NAMES = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


class Reporter:
    """Content-free operational output plus a machine-readable result."""

    def __init__(self, command: str, *, verbose: bool = True) -> None:
        self.command = command
        self.verbose = verbose
        self.lines: list[str] = []
        self.rows: list[dict] = []
        self.started = time.time()

    def say(self, message: str = "") -> None:
        self.lines.append(message)
        if self.verbose:
            print(message)

    def section(self, title: str) -> None:
        self.say("")
        self.say(f"== {title} ==")

    def status(self, name: str, state: str, detail: str = "", **extra: object) -> dict:
        row = {"check": name, "status": state, "detail": detail, **extra}
        self.rows.append(row)
        suffix = f" — {detail}" if detail else ""
        self.say(f"[{state:<12}] {name}{suffix}")
        return row

    def json_result(self, payload: dict) -> dict:
        return payload

    def result_state(self) -> str:
        states = {row["status"] for row in self.rows}
        if FAILED in states:
            return FAILED
        if BLOCKED in states:
            return BLOCKED
        if INCONCLUSIVE in states:
            return INCONCLUSIVE
        if states == {PASSED}:
            return PASSED
        return INCONCLUSIVE


# ---------------------------------------------------------------------------
# aggregate run index
# ---------------------------------------------------------------------------


def append_run_index(record: dict) -> None:
    """Append one content-free record per invocation. Never overwrites."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    record = {"recordedAt": utcnow(), "command": record.get("command"), **record}
    with RUN_INDEX.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_run_index(limit: int = 20) -> list[dict]:
    """The most recent ``limit`` index records.

    The default limit is a **read window**, not a total. Use
    :func:`count_run_index` for the true count.
    """
    if not RUN_INDEX.is_file():
        return []
    lines = [line for line in RUN_INDEX.read_text(encoding="utf-8").splitlines() if line.strip()]
    out: list[dict] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def count_run_index() -> int:
    """Every recorded invocation, counted — not a read window.

    A truncated window reported as a total is exactly the kind of quiet
    miscount this phase is supposed to remove.
    """
    if not RUN_INDEX.is_file():
        return 0
    return sum(1 for line in RUN_INDEX.read_text(encoding="utf-8").splitlines() if line.strip())


# ---------------------------------------------------------------------------
# environment / configuration (names only, never values)
# ---------------------------------------------------------------------------


@dataclass
class Preflight:
    """Which *names* are configured and what endpoints would be used."""

    gnani_key: bool
    gemini_key: bool
    gemini_model: str | None
    stt_url: str
    tts_url: str
    env_file_supplied: str | None
    missing: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "configured": {
                "GNANI_API_KEY": self.gnani_key,
                "GEMINI_API_KEY": self.gemini_key,
                "GEMINI_MODEL": bool(self.gemini_model),
            },
            "missing": list(self.missing),
            "intendedEndpoints": {"stt": self.stt_url, "tts": self.tts_url},
            "intendedModel": self.gemini_model,
            "supabaseRequired": False,
            "note": (
                "provider_readiness() is deliberately unavailable and includes "
                "Supabase; speech probes do not use it and do not need Supabase."
            ),
            "valuesPrinted": "never",
        }


def load_settings_for_probe(env_file: str | None):
    """Reuse the foundation settings factory. Never prints values."""
    from gnani_coach.settings import load_settings

    path = Path(env_file).expanduser() if env_file else None
    if path is not None:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"env file not found: {env_file}")
    return load_settings(env_file=path)


def run_preflight(reporter: Reporter, env_file: str | None) -> Preflight:
    from gnani_coach.providers.gemini import CANDIDATE_MODELS
    from gnani_coach.providers.stt import DEFAULT_STT_URL
    from gnani_coach.providers.tts import DEFAULT_TTS_URL

    reporter.section("configuration (names only, no values)")
    try:
        settings = load_settings_for_probe(env_file)
    except FileNotFoundError as exc:
        reporter.status("settings-load", BLOCKED, str(exc))
        return Preflight(
            gnani_key=False,
            gemini_key=False,
            gemini_model=None,
            stt_url=DEFAULT_STT_URL,
            tts_url=DEFAULT_TTS_URL,
            env_file_supplied=env_file,
            missing=["GNANI_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL"],
        )

    gnani = bool(settings.voice.api_key and settings.voice.api_key.get_secret_value())
    gemini = bool(settings.gemini.api_key and settings.gemini.api_key.get_secret_value())
    model = settings.gemini.model

    missing: list[str] = []
    if not gnani:
        missing.append("GNANI_API_KEY")
    if not gemini:
        missing.append("GEMINI_API_KEY")
    if not model:
        missing.append("GEMINI_MODEL")

    reporter.status(
        "GNANI_API_KEY",
        "configured" if gnani else "missing",
        "value never printed",
    )
    reporter.status(
        "GEMINI_API_KEY",
        "configured" if gemini else "missing",
        "value never printed",
    )
    reporter.status(
        "GEMINI_MODEL",
        "selected" if model else "missing",
        f"selector={model!r}" if model else "no model id is defaulted by design",
    )
    reporter.status(
        "SUPABASE_*",
        PASSED,
        "not required for any speech or reasoning probe",
    )
    reporter.status("provider_readiness()", NOT_RUN, "deliberately unavailable; unused by probes")
    reporter.status(
        "env file",
        PASSED if env_file else NOT_RUN,
        f"explicitly supplied ({Path(env_file).name})" if env_file else "process environment only",
    )

    preflight = Preflight(
        gnani_key=gnani,
        gemini_key=gemini,
        gemini_model=model,
        stt_url=settings.voice.stt_ws_url,
        tts_url=settings.voice.tts_ws_url,
        env_file_supplied=env_file,
        missing=missing,
    )
    reporter.section("intended endpoints and model selection")
    reporter.say(f"  STT websocket : {preflight.stt_url}")
    reporter.say(f"  TTS websocket : {preflight.tts_url}")
    reporter.say(f"  Gemini model  : {preflight.gemini_model or '(unset)'}")
    reporter.say(f"  documented Gemini candidates: {', '.join(CANDIDATE_MODELS)}")
    reporter.say("  inference calls made by preflight: 0")
    reporter.say(f"  missing names : {', '.join(missing) if missing else '(none)'}")
    return preflight


# ---------------------------------------------------------------------------
# live guards
# ---------------------------------------------------------------------------


class LiveRefused(RuntimeError):
    """A live command was requested without the required opt-in."""


def require_live(args: argparse.Namespace) -> None:
    if not getattr(args, "allow_live", False):
        raise LiveRefused(
            "live provider calls require the explicit --allow-live switch; "
            "no inference was attempted"
        )


def plan_budget(args: argparse.Namespace, operations: int, audio_seconds: float = 0.0):
    """Print a content-free plan, then refuse it if it does not fit.

    ``operations`` is a count of **wire attempts the probe actually
    needs**, not of visible stages. A chained turn really costs five
    (STT connect, STT session, reasoning attempt, TTS connect, TTS
    synthesise); planning four made a tight budget fail only after
    credit had been spent.

    ``--max-requests`` is the caller's **authorisation ceiling**, so it
    tightens the budget rather than replacing the requirement. If the
    probe needs more attempts than the caller authorised, the plan is
    refused **before any side effect**.

    ``audio_seconds`` must be the **framed submitted** audio, including
    the trailing silence that closes the provider's VAD window. A plan
    sized on the clip's own duration is under-counted.
    """
    from gnani_coach.providers.limits import MAX_OPERATIONS, ProbeBudget

    ceiling = getattr(args, "max_requests", None)
    if ceiling is None:
        ceiling = MAX_OPERATIONS
    if ceiling > MAX_OPERATIONS:
        raise SystemExit(
            f"--max-requests {ceiling} exceeds the probe limit of "
            f"{MAX_OPERATIONS} wire attempts"
        )
    budget = ProbeBudget(max_operations=int(ceiling))
    try:
        budget.check_plan(operations, audio_seconds)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    print(
        f"[plan] wire_operations_needed={operations} "
        f"authorised_ceiling={budget.max_operations} "
        f"stt_audio_submitted={audio_seconds:.1f}s/{budget.max_audio_seconds:.0f}s "
        f"retries<={budget.max_retries_per_operation} "
        f"allow_live={bool(getattr(args, 'allow_live', False))} "
        "(no content, no paths)"
    )
    return budget


# ---------------------------------------------------------------------------
# fixtures command
# ---------------------------------------------------------------------------


def cmd_fixtures(args: argparse.Namespace, reporter: Reporter) -> int:
    from tools.probes import fixtures_gen, fixtures_io

    reporter.section("synthetic fixtures")
    manifest = fixtures_gen.build_manifest(fixtures_io.FIXTURE_ROOT)
    reporter.status("manifest-written", PASSED, "fixtures/synthetic/manifest.json")
    reporter.status(
        "generator",
        PASSED,
        f"{fixtures_gen.GENERATOR_NAME}@{fixtures_gen.GENERATOR_VERSION} seed={fixtures_gen.RNG_SEED}",
    )

    if getattr(args, "prepare_spoken", False):
        # Real spoken audio needs a real speech source. The only source
        # used here is our own TTS endpoint: synthetic, non-personal, and
        # recorded in the manifest with generator/model/voice/hash.
        require_live(args)
        _prepare_spoken_fixtures(args, reporter, manifest)
        manifest = fixtures_io.load_manifest()

    ready, missing = fixtures_io.available(manifest)
    for entry in manifest["fixtures"]:
        state = PASSED if entry["fixtureId"] in ready else BLOCKED
        reporter.status(
            f"fixture:{entry['fixtureId']}",
            state,
            entry.get("description", "")[:110]
            if state == PASSED
            else (entry.get("labelProvenance") or {}).get("smallest_user_action", "no prepared speech source"),
            kind=entry["kind"],
        )
    reporter.section("audio ignore policy")
    reporter.say("  generated audio is ignored by the existing *.wav rule (unmodified)")
    reporter.say(f"  available={len(ready)} missing={len(missing)}")
    reporter.say(f"  missing ids: {', '.join(missing) if missing else '(none)'}")
    reporter.status("live-fixture-calls", NOT_RUN, "analytic fixtures need no provider call")
    return EXIT_OK if ready else EXIT_BLOCKED


def _prepare_spoken_fixtures(args, reporter: Reporter, manifest: dict) -> None:
    """Render the spoken fixture set with the project's own TTS endpoint."""
    import asyncio

    from gnani_coach.providers.limits import ProbeBudget
    from tools.probes import fixtures_io, spoken_gen

    preflight = run_preflight(reporter, args.env_file)
    if preflight.missing:
        for name in preflight.missing:
            reporter.status(f"missing:{name}", BLOCKED, "spoken fixtures need GNANI_API_KEY")
        return

    settings = load_settings_for_probe(args.env_file)
    api_key = settings.voice.api_key.get_secret_value()
    recipes = spoken_gen.RECIPES
    parts = sum(len(r.parts) for r in recipes)
    budget = ProbeBudget()
    print(
        f"[plan] spoken_fixtures={len(recipes)} tts_syntheses={parts}/"
        f"{budget.max_operations} operations allow_live=True (no content, no paths)"
    )

    outcomes = asyncio.run(
        spoken_gen.build_spoken_fixtures(api_key, fixtures_io.FIXTURE_ROOT, budget=budget)
    )
    updated = spoken_gen.write_manifest_entries(
        manifest, outcomes, recipes, root=fixtures_io.FIXTURE_ROOT
    )
    reporter.section("spoken fixture synthesis (own TTS, synthetic and non-personal)")
    for outcome in outcomes:
        state = PASSED if outcome.ok else FAILED
        detail = (
            f"sha256={outcome.detail['sha256'][:16]}... {outcome.detail['durationMs']}ms"
            if outcome.ok
            else json.dumps(outcome.detail.get("parts", []))[:140]
        )
        reporter.status(f"spoken:{outcome.fixture_id}", state, detail)
    reporter.say(f"  manifest entries updated: {updated}")
    reporter.say(f"  budget: {json.dumps(budget.summary())}")
    reporter.status(
        "filler-labels",
        NOT_RUN,
        "a TTS script is not proof a rendered hesitation is audible; labels stay "
        "UNVERIFIED until a named reviewer listens",
    )


# ---------------------------------------------------------------------------
# speech command
# ---------------------------------------------------------------------------


def cmd_speech(args: argparse.Namespace, reporter: Reporter) -> int:
    require_live(args)
    from tools.probes import fixtures_io
    from tools.probes.live import run_speech_probe

    reporter.section("speech probe")
    preflight = run_preflight(reporter, args.env_file)
    if preflight.missing:
        for name in preflight.missing:
            reporter.status(f"missing:{name}", BLOCKED, "live speech requires this variable name")
        return EXIT_BLOCKED

    try:
        manifest = fixtures_io.load_manifest()
        fixture = fixtures_io.resolve_fixture(args.fixture, manifest)
    except Exception as exc:  # noqa: BLE001
        reporter.status("fixture-resolution", BLOCKED, str(exc))
        return EXIT_BLOCKED

    reporter.status(
        "fixture",
        PASSED,
        f"{fixture.fixture_id} sha256={fixture.sha256[:16]}… "
        f"language={fixture.language_code} rate={fixture.sample_rate}",
    )
    reporter.status(
        "label-provenance",
        NOT_RUN,
        f"review_state={fixture.label_provenance.get('review_state')}",
    )
    result = run_speech_probe(fixture, args, reporter)
    return EXIT_OK if result.ok else EXIT_FAILED


# ---------------------------------------------------------------------------
# chain command
# ---------------------------------------------------------------------------


def cmd_chain(args: argparse.Namespace, reporter: Reporter) -> int:
    require_live(args)
    from tools.probes import fixtures_io
    from tools.probes.live import run_chain_probe

    reporter.section("chained STT -> Gemini -> TTS probe")
    preflight = run_preflight(reporter, args.env_file)
    if preflight.missing:
        for name in preflight.missing:
            reporter.status(f"missing:{name}", BLOCKED, "the chain requires this variable name")
        return EXIT_BLOCKED

    try:
        manifest = fixtures_io.load_manifest()
        fixture = fixtures_io.resolve_fixture(args.fixture, manifest)
    except Exception as exc:  # noqa: BLE001
        reporter.status("fixture-resolution", BLOCKED, str(exc))
        return EXIT_BLOCKED

    result = run_chain_probe(fixture, args, reporter)
    return EXIT_OK if result.ok else EXIT_FAILED


# ---------------------------------------------------------------------------
# matrix command
# ---------------------------------------------------------------------------


def cmd_matrix(args: argparse.Namespace, reporter: Reporter) -> int:
    require_live(args)
    from tools.probes import fixtures_io
    from tools.probes.live import run_matrix_probe

    reporter.section("language capability matrix")
    preflight = run_preflight(reporter, args.env_file)
    if preflight.missing:
        for name in preflight.missing:
            reporter.status(f"missing:{name}", BLOCKED, "the matrix requires this variable name")
        return EXIT_BLOCKED
    manifest = fixtures_io.load_manifest()
    return run_matrix_probe(manifest, args, reporter)


# ---------------------------------------------------------------------------
# analysis command
# ---------------------------------------------------------------------------


def cmd_analysis(args: argparse.Namespace, reporter: Reporter) -> int:
    from tools.probes import fixtures_io
    from tools.probes.analysis import vad as vad_mod
    from tools.probes.offline import run_offline_analysis

    if args.prepare_models:
        reporter.section("model asset preparation (explicit opt-in)")
        asset = vad_mod.prepare_model(force=args.force)
        reporter.status("silero-vad-onnx", PASSED, f"sha256={asset.sha256[:16]}… bytes={asset.bytes}")
        reporter.status("license", PASSED, asset.license)
        reporter.status("cache", PASSED, "tools/probes/.cache/models (ignored by .gitignore)")
        return EXIT_OK

    if args.allow_live:
        reporter.status(
            "audio-review",
            NOT_RUN,
            "optional Gemini clip review is a separate explicit operation; "
            "this phase reports it as NOT RUN rather than billing for it",
        )
        return EXIT_OK

    return run_offline_analysis(reporter, fixtures_io, vad_mod)


def cmd_filler(args: argparse.Namespace, reporter: Reporter) -> int:
    """The bounded filler experiment: three routes, one clip, one budget."""
    from tools.probes.live.filler_experiment import run_filler_experiment

    reporter.section("bounded filler experiment (Phase 02, FIX cycle 2)")
    exit_code, payload = run_filler_experiment(args, reporter)
    # The machine-readable result and the measured attempt accounting are
    # stored with the run's own evidence.
    args._result_payload = payload
    budget = payload.get("budget")
    if isinstance(budget, dict) and budget:
        args._attempt_accounting = budget
    summary = (
        f"passed={payload.get('passedRoutes') or '(none)'} "
        f"failed={payload.get('failedRoutes') or '(none)'} "
        f"blocked={payload.get('blockedRoutes') or '(none)'}"
    )
    reporter.status("routes", str(payload.get("overall", INCONCLUSIVE)), summary)
    return exit_code


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description=(
            "Phase 02 provider/audio feasibility probes. Offline by default; "
            "live provider calls require --allow-live."
        ),
    )
    parser.add_argument("--env-file", default=None, metavar="PATH",
                        help="explicitly load settings from this file (never an implicit .env)")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable summary")
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight", help="configuration/endpoint diagnostics; makes no inference call")
    preflight.set_defaults(func=lambda a, r: (run_preflight(r, a.env_file), EXIT_OK)[1])

    fixtures = sub.add_parser("fixtures", help="build/inventory the synthetic fixture set")
    fixtures.add_argument("--offline", action="store_true", help="generate without any provider access")
    fixtures.add_argument("--allow-live", action="store_true", help="required for --prepare-spoken")
    fixtures.add_argument(
        "--prepare-spoken",
        action="store_true",
        help=(
            "render the real spoken fixtures using this project's own Gnani "
            "TTS endpoint (synthetic, non-personal). Requires --allow-live."
        ),
    )
    fixtures.set_defaults(func=cmd_fixtures)

    speech = sub.add_parser("speech", help="bounded Gnani realtime STT probe")
    speech.add_argument(
        "--language",
        default="english",
        help=(
            "catalog language selector: an id, a display name or an STT/TTS "
            "code, all resolved through packages/contracts/data/catalog.json"
        ),
    )
    speech.add_argument("--fixture", default="clear-utterance", help="prepared synthetic fixture id")
    speech.add_argument("--allow-live", action="store_true")
    speech.add_argument("--max-requests", type=int, default=8)
    speech.add_argument("--realtime", action="store_true", default=True,
                        help="pace frames at the real sample rate (documented as required)")
    speech.add_argument("--burst", action="store_true",
                        help="send without pacing; records the documented VAD-accuracy degradation")
    speech.set_defaults(func=cmd_speech)

    chain = sub.add_parser("chain", help="one real STT -> Gemini -> TTS turn")
    chain.add_argument("--language", default="english")
    chain.add_argument("--fixture", default="clear-utterance")
    chain.add_argument("--voice", default="Kaveri", help="documented Timbre v2.5 English voice")
    chain.add_argument("--tts-model", default="timbre-v2.5")
    chain.add_argument("--scenario", default="everyday")
    chain.add_argument("--level", default="beginner")
    chain.add_argument(
        "--reply-language",
        default="english",
        help="catalog language selector for the reply language",
    )
    chain.add_argument("--allow-live", action="store_true")
    chain.add_argument("--max-requests", type=int, default=8)
    chain.add_argument(
        "--attempt-timeout",
        type=float,
        default=DEFAULT_ATTEMPT_TIMEOUT_S,
        metavar="SECONDS",
        help=(
            "bound on one reasoning wire attempt. A local timeout is not a "
            "provider cancellation and makes no claim about billing"
        ),
    )
    chain.add_argument(
        "--call-deadline",
        type=float,
        default=DEFAULT_DEADLINE_S,
        metavar="SECONDS",
        help=(
            "overall bound on the reasoning call, covering every attempt and "
            "backoff. This is a feasibility-probe diagnostic bound, NOT the "
            "app's <=3s voice-turn target"
        ),
    )
    chain.set_defaults(func=cmd_chain)

    matrix = sub.add_parser("matrix", help="ten catalog languages plus Hinglish")
    matrix.add_argument("--allow-live", action="store_true")
    matrix.add_argument("--max-requests", type=int, default=40)
    matrix.add_argument("--fixture", default="clear-utterance")
    matrix.add_argument(
        "--languages",
        nargs="+",
        default=None,
        metavar="ID",
        help=(
            "restrict to catalog ids (for example: --languages telugu hinglish). "
            "The full eleven-row matrix needs ~55 operations, which exceeds the "
            "40-operation probe limit, so covering every language takes two "
            "invocations."
        ),
    )
    matrix.set_defaults(func=cmd_matrix)

    analysis = sub.add_parser("analysis", help="offline audio measurement")
    analysis.add_argument("--offline", action="store_true", default=True)
    analysis.add_argument("--allow-live", action="store_true")
    analysis.add_argument("--prepare-models", action="store_true",
                          help="download the Silero VAD ONNX asset into the ignored cache")
    analysis.add_argument("--force", action="store_true", help="re-download even if present")
    analysis.set_defaults(func=cmd_analysis)

    filler = sub.add_parser(
        "filler",
        help="the bounded filler experiment: three routes on one clip (Phase 02 FIX-2)",
    )
    filler.add_argument("--allow-live", action="store_true",
                        help="required for the STT and Gemini routes; the offline "
                             "acoustic route runs without it")
    filler.add_argument("--max-requests", type=int, default=16,
                        help="the whole-step ceiling on wire attempts (default 16)")
    filler.add_argument("--language", default="english",
                        help="catalog language selector for the STT route")
    filler.set_defaults(func=cmd_filler, evidence_root="fix-2")

    return parser


def _result_payload(args: argparse.Namespace) -> dict | None:
    """The machine-readable result a command may attach to its evidence."""
    payload = getattr(args, "_result_payload", None)
    return payload if isinstance(payload, dict) else None


def _attempt_accounting(args: argparse.Namespace) -> dict | None:
    """The measured wire-attempt accounting a command may attach."""
    payload = getattr(args, "_attempt_accounting", None)
    return payload if isinstance(payload, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    reporter = Reporter(args.command)

    # Every invocation — success, failure or cancellation — writes to a
    # fresh, immutable run directory. A previous run is never overwritten.
    from tools.probes.evidence import FIX2_EVIDENCE_ROOT, FIX_EVIDENCE_ROOT, RunEvidence

    raw_argv = list(argv if argv is not None else sys.argv[1:])
    evidence_root = (
        FIX2_EVIDENCE_ROOT
        if getattr(args, "evidence_root", "fix-1") == "fix-2"
        else FIX_EVIDENCE_ROOT
    )
    evidence = RunEvidence(
        args.command, raw_argv, cwd=str(Path.cwd()), root=evidence_root
    )

    captured_err = io.StringIO()
    exit_code = EXIT_FAILED
    state = FAILED
    try:
        with evidence:
            reporter.section("probe run")
            reporter.say(f"  run_id       : {evidence.record.run_id}")
            reporter.say(f"  started_utc  : {utcnow()}")
            reporter.say(f"  python       : {platform.python_version()}")
            reporter.say(f"  cwd          : {Path.cwd()}")
            reporter.say(f"  command      : run.py {args.command}")
            reporter.say(f"  exact argv   : {raw_argv}")
            reporter.say("  inference calls are made only by an explicit --allow-live command")

            try:
                exit_code = args.func(args, reporter)
            except LiveRefused as exc:
                reporter.status("live-consent", BLOCKED, str(exc))
                exit_code = EXIT_BLOCKED
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                reporter.status(
                    "unexpected-error", FAILED, f"{type(exc).__name__}: {exc}"
                )
                raise

            state = reporter.result_state()
            elapsed = round(time.time() - reporter.started, 3)
            reporter.section("summary")
            reporter.say(f"  overall     : {state}")
            reporter.say(f"  exit_code   : {exit_code}")
            reporter.say(f"  elapsed_s   : {elapsed}")
            reporter.say(f"  run id      : {evidence.record.run_id}")
            reporter.say(f"  evidence    : {evidence.relative()}")
            reporter.say(f"  run index   : {count_run_index() + 1} invocations recorded")
            reporter.say(f"  index file  : {RUN_INDEX.relative_to(REPO_ROOT)}")

            # The evidence is finished **last**, so the captured stdout is
            # the complete report rather than a snapshot taken before its
            # own final lines were printed.
            evidence.finish(
                exit_code=exit_code,
                overall=state,
                stdout="\n".join(reporter.lines),
                stderr=captured_err.getvalue(),
                result=_result_payload(args),
                attempt_accounting=_attempt_accounting(args),
                notes=[f"command: {args.command}"],
            )
    finally:
        captured_err.close()

    append_run_index(
        {
            "command": args.command,
            "runId": evidence.record.run_id,
            "allow_live": bool(getattr(args, "allow_live", False)),
            "overall": state,
            "exit_code": exit_code,
            "elapsed_s": round(time.time() - reporter.started, 3),
            "checks": [
                {"check": row["check"], "status": row["status"]} for row in reporter.rows
            ],
            "python": platform.python_version(),
            "cwd": str(Path.cwd()),
        }
    )

    if args.json:
        print(
            json.dumps(
                {
                    "command": args.command,
                    "runId": evidence.record.run_id,
                    "overall": state,
                    "exit_code": exit_code,
                    "checks": reporter.rows,
                },
                indent=2,
            )
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
