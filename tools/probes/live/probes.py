"""Bounded live probes: speech, chain, language matrix.

Truth rules this module exists to enforce [FIX-1 P02-04]
-------------------------------------------------------
* A **requested stage** is a stage the caller asked for. A stage that was
  not requested is ``NOT RUN`` and can never contribute coverage; a stage
  that was requested and failed makes the aggregate **FAILED**, with a
  nonzero exit.
* **Parameter acceptance is not language coverage.** Sending English audio
  with ``ta-IN`` proves the endpoint accepted the parameter. It is
  recorded as ``PARAMETER ACCEPTED`` and never as Tamil speech evidence.
* A language with no matching-language fixture stays ``NOT RUN`` with the
  missing fixture named. English audio is never substituted.
* Every language id, display name and STT/TTS code comes from the shared
  catalog via :mod:`tools.probes.live.languages`.

Timing honesty, restated because it is easy to get wrong
--------------------------------------------------------
``first_nonempty_chunk_ms`` and the stage durations below are **backend**
timings measured inside this process. They are not end-of-turn-to-first-
audible latency for a browser: no browser, no AudioWorklet, no playback
buffer and no network path from the learner device is involved. A chained
fixture turn is a feasibility datapoint, not a working hands-free app.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from gnani_coach.providers.errors import ProviderError
from gnani_coach.providers.gemini import (
    CANDIDATE_MODELS,
    CoachRequest,
    GeminiCoach,
    GeminiConfig,
)
from gnani_coach.providers.limits import ProbeBudget
from gnani_coach.providers.pcm import pad_to_frame, pcm_seconds
from gnani_coach.providers.stt import GnaniSttSession, build_config
from gnani_coach.providers.tts import (
    AudioConfig,
    GnaniTtsSession,
    TtsConfig,
)

from tools.probes import fixtures_io
from tools.probes.evidence import RunEvidence, summarise_attempts
from tools.probes.live.languages import (
    CatalogLanguage,
    load_catalog,
    reply_language_name,
    resolve,
    resolve_many,
)
from tools.probes.run import (
    BLOCKED,
    EXIT_BLOCKED,
    EXIT_FAILED,
    EXIT_OK,
    FAILED,
    INCONCLUSIVE,
    NOT_RUN,
    PASSED,
    Reporter,
    plan_budget,
)

#: Extra status for a cell that proves only that a parameter was accepted.
PARAMETER_ACCEPTED = "PARAMETER ACCEPTED"
#: Extra status for a cell whose provider returned nothing analyzable.
NO_SPEECH = "NO SPEECH DETECTED"
#: Extra status for a cell that ran but produced no model text.
NO_MODEL_TEXT = "NO MODEL TEXT"

#: Stages a matrix row requests when a row runs at all. Parameter
#: acceptance columns are reported alongside but are **never** part of
#: coverage: they prove the endpoint took the value, not that the value
#: described the audio.
REQUIRED_STAGES = ("sttNativeFixture", "ttsNativeText", "geminiLanguage")

#: Columns that record a parameter-acceptance smoke check only.
PARAMETER_COLUMNS = ("sttParameterAccepted", "ttsParameterAccepted")

#: Wire operations one full language row costs, counted honestly:
#: STT connect + STT session + TTS connect + TTS synthesise + reasoning.
OPS_PER_LANGUAGE = 5

#: The same five operations, for one chained turn. The previous revision
#: planned four while its own success evidence recorded five.
CHAIN_OPS_MINIMUM = 5
#: STT only: connect + one session.
SPEECH_OPS_MINIMUM = 2

#: Silence appended after learner audio so the server's VAD can close the
#: final segment. It is padding, not learner speech, but it IS submitted
#: audio and must be charged to the budget like any other.
TRAILING_SILENCE_MS = 800


@dataclass
class ProbeOutcome:
    ok: bool
    exit_code: int
    detail: dict = field(default_factory=dict)
    run: "RunEvidence | None" = None


def stt_submitted_seconds(pcm: bytes, sample_rate: int) -> float:
    """Seconds this clip will actually submit, including trailing silence.

    Budget planning must use this, not the clip's own duration: a plan
    sized on the audio alone is under-counted and fails mid-run, after
    credit has already been spent.
    """
    tail = int(round(TRAILING_SILENCE_MS * sample_rate / 1000.0)) * 2
    padded, _ = pad_to_frame(pcm + b"\x00" * tail)
    return pcm_seconds(padded, sample_rate)


def _settings(args):
    from tools.probes.run import load_settings_for_probe

    return load_settings_for_probe(getattr(args, "env_file", None))


def _write_evidence(name: str, payload: dict) -> Path:
    """Legacy fixed-name writer.

    Retained only for the Phase 02 BUILD-era filenames. New runs use
    :class:`~tools.probes.evidence.RunEvidence`, which never overwrites.
    """
    from tools.probes.evidence import EVIDENCE_ROOT

    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_ROOT / name
    if target.exists():
        target = target.with_name(f"{target.stem}-{int(time.time())}{target.suffix}")
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


# ---------------------------------------------------------------------------
# speech
# ---------------------------------------------------------------------------


def run_speech_probe(fixture, args, reporter: Reporter) -> ProbeOutcome:
    """One bounded realtime STT run over a prepared synthetic fixture."""
    settings = _settings(args)
    api_key = settings.voice.api_key.get_secret_value()  # never printed
    catalog = load_catalog()

    pcm = fixtures_io.raw_pcm_of(fixture)
    # Plan on what will actually be submitted, not on the clip's duration.
    seconds = stt_submitted_seconds(pcm, fixture.sample_rate)
    budget = plan_budget(
        args, operations=SPEECH_OPS_MINIMUM, audio_seconds=seconds
    )

    reporter.section("plan")
    reporter.say(f"  fixture_id={fixture.fixture_id} sha256={fixture.sha256[:16]}…")
    reporter.say(
        f"  submitted_audio_seconds={seconds:.2f} "
        f"(includes {TRAILING_SILENCE_MS}ms trailing silence)"
    )
    reporter.say(f"  operations_planned={SPEECH_OPS_MINIMUM}")
    reporter.say(f"  pacing={'burst' if getattr(args, 'burst', False) else 'real-time'}")
    reporter.say("  substitution=off bias_words=0 (never biased from the known script)")

    # The requested language must resolve through the shared catalog
    # before any request is issued.
    try:
        entry = resolve(args.language, catalog)
    except ProviderError as exc:
        reporter.status("config", FAILED, str(exc.detail))
        return ProbeOutcome(False, EXIT_FAILED, {"stage": "config"})
    config = build_config(entry.stt_code, sample_rate=fixture.sample_rate)
    reporter.say(
        f"  language={entry.id} stt_code={entry.stt_code} "
        f"tts_code={entry.tts_code} (resolved from the shared catalog)"
    )
    reporter.say(json.dumps(config.safe_summary(api_key), indent=2))

    if fixture.language_code not in ("en-IN", entry.stt_code):
        reporter.status(
            "fixture-language-match",
            INCONCLUSIVE,
            (
                f"fixture {fixture.fixture_id} is {fixture.language_code} audio but the "
                f"row requests {entry.stt_code}; this proves parameter acceptance only, "
                "not that-language recognition"
            ),
        )

    realtime = not getattr(args, "burst", False)
    result = asyncio.run(_speech_session(config, api_key, pcm, budget, realtime))

    reporter.section("observed provider events (content-free except recognised text)")
    for event in result.transcripts:
        reporter.say(
            f"  segment_index={event.segment_index} segment_id={event.segment_id} "
            f"status={event.status} audio_duration_ms={event.audio_duration_ms} "
            f"latency_ms={event.latency_ms} learner_clock_samples={event.learner_clock_samples}"
        )
        reporter.say(f"    text: {event.text!r}")
    reporter.section("clock and counts")
    reporter.say(f"  segments={result.segment_count} processing_acks={result.processing_count}")
    reporter.say(f"  sample_clock={json.dumps(result.sample_clock.summary())}")
    reporter.say(f"  submitted_audio_seconds={result.submitted_audio_seconds:.2f}")
    reporter.say(f"  end_padding_ms={result.end_padding_ms}")
    reporter.say(f"  duplicate_segment_ids={result.duplicate_segment_ids}")
    reporter.say(f"  out_of_order_indexes={result.out_of_order_indexes}")
    for frame in result.unrecognized_frames:
        reporter.say(
            f"  UNDOCUMENTED FRAME: type={frame.message_type!r} keys={frame.keys} "
            f"({frame.note})"
        )
    if result.unrecognized_frames:
        reporter.status(
            "undocumented-frames",
            INCONCLUSIVE,
            f"{len(result.unrecognized_frames)} frame(s) observed that are absent "
            "from the published message list; recorded, not ignored",
        )
    reporter.say(f"  server_config={json.dumps(result.server_config)}")
    for err in result.errors:
        reporter.say(f"  provider_error: {err.message}")
    reporter.section("budget (measured wire attempts)")
    reporter.say(f"  {json.dumps(summarise_attempts(budget))}")
    reporter.say(
        "  NOTE: audio_duration_ms and latency are server-reported metadata. "
        "No word-level timing exists in this API and none was derived."
    )

    if result.errors:
        reporter.status("stt-run", FAILED, "provider returned an error frame")
        return ProbeOutcome(False, EXIT_FAILED, {"transcripts": result.segment_count})
    if result.segment_count == 0:
        reporter.status(
            "stt-run",
            FAILED,
            "no transcript segment returned (possibly VAD suppression or a non-speech fixture)",
        )
        return ProbeOutcome(False, EXIT_FAILED, {"transcripts": 0})
    reporter.status(
        "stt-run",
        PASSED,
        f"{result.segment_count} segment(s); recogniser output is NOT a turn boundary",
    )
    return ProbeOutcome(True, EXIT_OK, {"transcripts": result.segment_count})


async def _speech_session(config, api_key, pcm, budget: ProbeBudget, realtime: bool):
    session = GnaniSttSession(config, api_key, budget=budget)
    async with session:
        return await session.stream_pcm(pcm, real_time=realtime)


async def _tts_synthesize(config, api_key, budget: ProbeBudget):
    """Run one synthesis inside the session's own lifecycle."""
    session = GnaniTtsSession(config, api_key, budget=budget)
    async with session:
        return await session.synthesize()


# ---------------------------------------------------------------------------
# chain
# ---------------------------------------------------------------------------


def run_chain_probe(fixture, args, reporter: Reporter) -> ProbeOutcome:
    """Real STT text -> real Gemini reply -> real TTS chunks."""
    settings = _settings(args)
    gnani_key = settings.voice.api_key.get_secret_value()
    gemini_key = settings.gemini.api_key.get_secret_value()
    model = settings.gemini.model
    catalog = load_catalog()

    pcm = fixtures_io.raw_pcm_of(fixture)
    submitted_seconds = stt_submitted_seconds(pcm, fixture.sample_rate)
    # Five wire operations, planned before anything is spent.
    budget = plan_budget(
        args, operations=CHAIN_OPS_MINIMUM, audio_seconds=submitted_seconds
    )

    reporter.section("plan")
    reporter.say(
        f"  stages: stt -> gemini({model}) -> tts({args.tts_model}/{args.voice})"
    )
    reporter.say(f"  fixture_id={fixture.fixture_id} sha256={fixture.sha256[:16]}…")
    reporter.say(
        f"  submitted_audio_seconds={submitted_seconds:.2f} "
        f"(includes {TRAILING_SILENCE_MS}ms trailing silence)"
    )
    reporter.say(
        f"  wire_operations_planned={CHAIN_OPS_MINIMUM} "
        "(stt connect + stt session + reasoning + tts connect + tts synthesise)"
    )
    reporter.say("  the known fixture script is NEVER substituted for recognition")
    reporter.say("  no pre-recorded response is played back in place of the TTS call")

    timings: dict[str, float] = {}
    stage_records: list[dict] = []

    # The reply language must resolve through the catalog, and the TTS
    # language is the catalog's TTS code for that same entry — never a
    # hand-written mapping from a display string.
    try:
        reply_entry = resolve(args.reply_language, catalog)
    except ProviderError as exc:
        reporter.status("stage:config", FAILED, str(exc.detail))
        return ProbeOutcome(False, EXIT_FAILED, {"failed_stage": "config"})
    reporter.say(
        f"  reply_language={reply_entry.id} "
        f"reply_language_name={reply_language_name(reply_entry)!r} "
        f"tts_code={reply_entry.tts_code}"
    )

    # Stage 1 — real recognition
    reporter.section("stage 1/3: Gnani realtime STT")
    try:
        stt_entry = resolve(args.language, catalog)
    except ProviderError as exc:
        reporter.status("stage:config", FAILED, str(exc.detail))
        return ProbeOutcome(False, EXIT_FAILED, {"failed_stage": "config"})
    stt_config = build_config(stt_entry.stt_code, sample_rate=fixture.sample_rate)
    started = time.time()
    try:
        stt_result = asyncio.run(
            _speech_session(stt_config, gnani_key, pcm, budget, True)
        )
    except ProviderError as exc:
        reporter.status("stage:stt", FAILED, f"{exc.category}: {exc.detail}")
        return ProbeOutcome(False, EXIT_FAILED, {"failed_stage": "stt"})
    timings["stt_ms"] = round((time.time() - started) * 1000.0, 1)
    stage_records.append(
        {
            "stage": "stt",
            "status": FAILED if not stt_result.text else PASSED,
            "segments": stt_result.segment_count,
            "recognizedChars": len(stt_result.text),
            "fixtureSha256": fixture.sha256,
            "fixtureLanguageCode": fixture.language_code,
            "requestedSttCode": stt_entry.stt_code,
        }
    )
    for event in stt_result.transcripts:
        reporter.say(f"  segment {event.segment_index}: {event.text!r}")
    if not stt_result.text:
        reporter.status(
            "stage:stt", NO_SPEECH, "no recognized text; the chain cannot continue"
        )
        return ProbeOutcome(False, EXIT_FAILED, {"failed_stage": "stt"})
    recognized = stt_result.text
    reporter.status("stage:stt", PASSED, f"{len(recognized)} chars recognised")

    # Stage 2 — real Gemini reply
    reporter.section("stage 2/3: Gemini reasoning")
    gemini = GeminiCoach(
        GeminiConfig(model=model, store=False),
        gemini_key,
        budget=budget,
        attempt_timeout=float(getattr(args, "attempt_timeout", 15.0)),
        deadline=float(getattr(args, "call_deadline", 45.0)),
    )
    reporter.say(f"  {json.dumps(gemini.safe_summary(), indent=2)}")
    request = CoachRequest(
        recognized_text=recognized,
        system_instruction="You are a spoken-language conversation coach.",
        scenario=args.scenario,
        level=args.level,
        reply_language=reply_language_name(reply_entry),
    )
    started = time.time()
    try:
        reply = asyncio.run(gemini.reply(request))
    except ProviderError as exc:
        reporter.status("stage:gemini", FAILED, f"{exc.category}: {exc.detail}")
        stage_records.append({"stage": "gemini", "status": FAILED, "error": exc.category})
        return ProbeOutcome(
            False,
            EXIT_FAILED,
            {"failed_stage": "gemini", "recognized_chars": len(recognized)},
        )
    timings["gemini_ms"] = round((time.time() - started) * 1000.0, 1)
    reporter.say(f"  model={reply.model} store={reply.store} tools={reply.tools_enabled}")
    reporter.say(f"  wire attempts made: {json.dumps(gemini.attempts_made)}")
    reporter.say(f"  reply: {reply.text!r}")
    stage_records.append(
        {
            "stage": "gemini",
            "status": PASSED if reply.text else NO_MODEL_TEXT,
            "model": reply.model,
            "replyChars": len(reply.text),
            "wireAttempts": gemini.attempts_made,
            "interactionId": reply.interaction_id,
        }
    )
    if not reply.text:
        # An empty model response is not a successful reasoning turn.
        reporter.status("stage:gemini", NO_MODEL_TEXT, "empty reply")
        return ProbeOutcome(False, EXIT_FAILED, {"failed_stage": "gemini"})
    reporter.status("stage:gemini", PASSED, "bounded reply received")

    # Stage 3 — real TTS
    reporter.section("stage 3/3: Gnani realtime TTS")
    tts_config = TtsConfig(
        text=reply.text,
        voice=args.voice,
        model=args.tts_model,
        # The catalog's TTS code for the resolved entry. Hinglish keeps
        # its own `hi-en` code; it is never silently replaced.
        language=reply_entry.tts_code,
        audio=AudioConfig(sample_rate=16000, container="raw"),
    )
    started = time.time()
    try:
        tts_result = asyncio.run(_tts_synthesize(tts_config, gnani_key, budget))
    except ProviderError as exc:
        reporter.status("stage:tts", FAILED, f"{exc.category}: {exc.detail}")
        stage_records.append({"stage": "tts", "status": FAILED, "error": exc.category})
        return ProbeOutcome(
            False,
            EXIT_FAILED,
            {"failed_stage": "tts", "reply_chars": len(reply.text)},
        )
    timings["tts_total_ms"] = round((time.time() - started) * 1000.0, 1)

    reporter.say(f"  request_id={tts_result.request_id}")
    reporter.say(
        f"  first_nonempty_chunk_ms={tts_result.first_nonempty_chunk_ms} "
        f"(BACKEND timing, not browser first-audible latency)"
    )
    reporter.say(
        f"  total_bytes={tts_result.total_bytes} total_duration_ms={tts_result.total_duration_ms} "
        f"chunks={len(tts_result.chunks)}"
    )
    reporter.say(f"  container_observation={json.dumps(tts_result.container_observation)}")
    stage_records.append(
        {
            "stage": "tts",
            "status": PASSED if tts_result.total_bytes > 0 else NO_SPEECH,
            "bytes": tts_result.total_bytes,
            "chunks": len(tts_result.chunks),
            "requestId": tts_result.request_id,
            "firstNonemptyChunkMsBackend": tts_result.first_nonempty_chunk_ms,
        }
    )
    if tts_result.total_bytes <= 0:
        reporter.status("stage:tts", NO_SPEECH, "no audio bytes returned")
        return ProbeOutcome(False, EXIT_FAILED, {"failed_stage": "tts"})

    reporter.section("timings (backend only)")
    for key, value in timings.items():
        reporter.say(f"  {key}={value}")
    reporter.say("  A chained fixture turn is NOT a working hands-free call.")
    reporter.section("budget (measured wire attempts)")
    reporter.say(f"  {json.dumps(summarise_attempts(budget))}")

    payload = {
        "fixture": {
            "fixtureId": fixture.fixture_id,
            "sha256": fixture.sha256,
            "languageId": fixture.language_id,
            "languageCode": fixture.language_code,
            "sampleRate": fixture.sample_rate,
            "durationMs": fixture.duration_ms,
        },
        "language": {
            "requestedSttSelector": args.language,
            "requestedSttCode": stt_entry.stt_code,
            "replyLanguageId": reply_entry.id,
            "replyLanguageName": reply_language_name(reply_entry),
            "ttsCode": reply_entry.tts_code,
        },
        "geminiModel": reply.model,
        "ttsModel": args.tts_model,
        "ttsVoice": args.voice,
        # What the recogniser actually returned, not the intended script.
        "recognizedText": recognized,
        "recognizedChars": len(recognized),
        "sttSegments": [
            {
                "segmentId": e.segment_id,
                "segmentIndex": e.segment_index,
                "text": e.text,
                "status": e.status,
                "learnerClockSamples": e.learner_clock_samples,
            }
            for e in stt_result.transcripts
        ],
        "modelReplyText": reply.text,
        "replyChars": len(reply.text),
        "ttsTotalBytes": tts_result.total_bytes,
        "ttsChunkCount": len(tts_result.chunks),
        "ttsChunkSizes": [len(c.bytes) for c in tts_result.chunks if c.bytes],
        "firstNonemptyChunkMsBackend": tts_result.first_nonempty_chunk_ms,
        "submittedAudioSeconds": stt_result.submitted_audio_seconds,
        "sampleClock": stt_result.sample_clock.summary(),
        "timingsMs": timings,
        "stages": stage_records,
        "attemptAccounting": summarise_attempts(budget),
        "provenanceNote": (
            "the intended fixture script is recorded separately and is never "
            "used in place of the recognised text"
        ),
    }
    evidence = RunEvidence("chain", cwd=str(Path.cwd()))
    with evidence:
        path = evidence.finish(
            exit_code=EXIT_OK,
            overall=PASSED,
            stdout="\n".join(reporter.lines),
            stderr="",
            attempt_accounting=summarise_attempts(budget),
            result=payload,
            notes=[
                "one complete STT -> Gemini -> TTS turn; backend timings only",
            ],
        )
    reporter.say(f"  evidence: {evidence.relative()}")
    reporter.status("chain", PASSED, "one complete STT -> Gemini -> TTS turn evidenced")
    return ProbeOutcome(True, EXIT_OK, payload)


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------


def _matching_fixture(entry: CatalogLanguage, manifest: dict, args, fx):
    """The fixture whose language matches the row, or ``None``.

    A row with no matching-language fixture is reported ``NOT RUN`` with
    the missing fixture named. Substituting another language's audio would
    turn a parameter-acceptance check into a false language result.
    """
    if args.fixture:
        try:
            candidate = fx.resolve_fixture(args.fixture, manifest)
        except Exception:  # noqa: BLE001
            candidate = None
        if candidate is not None and candidate.language_code in (
            entry.stt_code,
            entry.tts_code,
        ):
            return candidate
        return None
    for item in manifest.get("fixtures", []):
        if item.get("audio") is None:
            continue
        if item.get("languageCode") in (entry.stt_code, entry.tts_code):
            try:
                return fx.resolve_fixture(item["fixtureId"], manifest)
            except Exception:  # noqa: BLE001
                continue
    return None


def run_matrix_probe(manifest: dict, args, reporter: Reporter) -> int:
    """Every catalog language plus Hinglish, honestly incomplete if needed."""
    catalog = load_catalog()
    selector = list(getattr(args, "languages", None) or [])
    try:
        rows_meta = resolve_many(selector, catalog)
    except ProviderError as exc:
        reporter.status("languages", FAILED, str(exc.detail))
        return EXIT_FAILED

    rows: list[dict] = []
    for entry in rows_meta:
        rows.append(
            {
                "id": entry.id,
                "displayName": entry.display_name,
                "nativeName": entry.native_name,
                "sttCode": entry.stt_code,
                "ttsCode": entry.tts_code,
                "kind": entry.kind,
                "documented": entry.documented,
                # coverage columns
                "sttNativeFixture": NOT_RUN,
                "ttsNativeText": NOT_RUN,
                "geminiLanguage": NOT_RUN,
                # parameter-acceptance smoke checks; never coverage
                "sttParameterAccepted": NOT_RUN,
                "ttsParameterAccepted": NOT_RUN,
                "coverage": NOT_RUN,
                "note": "",
            }
        )

    # Honest planning. A full row costs five operations and about three
    # connections, so the eleven-row matrix does NOT fit inside the
    # 40-operation limit in one invocation. That is reported, not hidden.
    fixture = None
    audio_per_row = 0.0
    try:
        fixture = fixtures_io.resolve_fixture(args.fixture, manifest)
        audio_per_row = stt_submitted_seconds(
            fixtures_io.raw_pcm_of(fixture), fixture.sample_rate
        )
    except Exception:  # noqa: BLE001
        audio_per_row = 0.0

    total_ops = len(rows) * OPS_PER_LANGUAGE
    audio = audio_per_row * len(rows)

    reporter.section("plan (checked against the limits before any call)")
    reporter.say(f"  languages={len(rows)}")
    reporter.say(f"  operations_needed_full_matrix={total_ops}")
    reporter.say(f"  planned_stt_audio_seconds={audio:.1f}")
    reporter.say(f"  connections_needed_full_matrix={len(rows) * 3}")
    reporter.say(
        f"  connections_limit={ProbeBudget().max_connections} "
        f"operations_limit={ProbeBudget().max_operations}"
    )
    if total_ops > ProbeBudget().max_operations:
        affordable = ProbeBudget().max_operations // OPS_PER_LANGUAGE
        reporter.status(
            "plan-fits",
            INCONCLUSIVE,
            f"the full {len(rows)}-language matrix needs {total_ops} operations but the "
            f"limit is {ProbeBudget().max_operations}; at most {affordable} rows can "
            f"complete per invocation. Unrun rows stay NOT RUN.",
        )
    try:
        budget = plan_budget(args, operations=total_ops, audio_seconds=audio)
    except SystemExit as exc:
        reporter.status("plan", BLOCKED, str(exc))
        return EXIT_BLOCKED

    ran_ok = 0
    for index, row in enumerate(rows):
        if budget.operations_left < OPS_PER_LANGUAGE:
            row["note"] = _append_note(
                row["note"], "NOT RUN - operation budget exhausted before this language"
            )
            reporter.status(f"language:{row['id']}", NOT_RUN, row["note"])
            continue
        rows[index] = _probe_one_language(row, args, budget, manifest, catalog)
        if rows[index]["coverage"] == PASSED:
            ran_ok += 1

    aggregate = aggregate_rows(rows, REQUIRED_STAGES)

    reporter.section("matrix results")
    for row in rows:
        reporter.say(
            f"  {row['id']:<12} coverage={row['coverage']:<18} "
            f"stt_native={row['sttNativeFixture']:<20} "
            f"tts_native={row['ttsNativeText']:<20} "
            f"gemini={row['geminiLanguage']:<14} "
            f"stt_param={row['sttParameterAccepted']:<10} "
            f"tts_param={row['ttsParameterAccepted']:<10} {row['note']}"
        )
    reporter.say("")
    reporter.say(
        "  *_param columns are PARAMETER ACCEPTANCE SMOKE CHECKS only: they show the "
        "endpoint accepted a value, never that the value described the audio."
    )

    reporter.section("summary")
    reporter.say(f"  rows_with_all_requested_stages_passed={ran_ok}/{len(rows)}")
    reporter.say(
        f"  rows_failed={len(aggregate['failed_rows'])}: "
        f"{', '.join(aggregate['failed_rows']) or '(none)'}"
    )
    reporter.say(
        f"  rows_not_run={len(aggregate['not_run_rows'])}: "
        f"{', '.join(aggregate['not_run_rows']) or '(none)'}"
    )
    reporter.say(f"  aggregate={aggregate['state']}")
    reporter.say(f"  budget={json.dumps(summarise_attempts(budget))}")
    reporter.say(
        "  API access and a synthetic roundtrip do NOT prove human intelligibility "
        "or coaching quality; no cell here is a quality verdict."
    )
    reporter.status(
        "matrix",
        aggregate["state"],
        f"{ran_ok}/{len(rows)} rows completed every requested stage "
        f"({', '.join(REQUIRED_STAGES)}); "
        f"{len(aggregate['failed_rows'])} failed and "
        f"{len(aggregate['not_run_rows'])} were not run",
    )

    payload = {
        "rows": rows,
        "requiredStages": list(REQUIRED_STAGES),
        "aggregate": aggregate,
        "attemptAccounting": summarise_attempts(budget),
    }
    evidence = RunEvidence("matrix", cwd=str(Path.cwd()))
    with evidence:
        evidence.finish(
            exit_code=aggregate["exit_code"],
            overall=aggregate["state"],
            stdout="\n".join(reporter.lines),
            stderr="",
            attempt_accounting=summarise_attempts(budget),
            result=payload,
        )
    reporter.say(f"  evidence: {evidence.relative()}")
    return int(aggregate["exit_code"])


def aggregate_rows(rows: list[dict], required_stages: tuple[str, ...]) -> dict:
    """Combine per-stage results into one honest verdict.

    A row counts as covered only when **every requested stage** passed.
    A stage that was not run is not a pass, and a stage that failed makes
    the row failed even if the other stages succeeded.
    """
    passed: list[str] = []
    failed: list[str] = []
    not_run: list[str] = []
    for row in rows:
        statuses = [row.get(stage) for stage in required_stages]
        row["coverage"] = _coverage_for(statuses)
        if row["coverage"] == PASSED:
            passed.append(row["id"])
        elif row["coverage"] == NOT_RUN:
            not_run.append(row["id"])
        else:
            failed.append(row["id"])

    if not_run or failed:
        state = INCONCLUSIVE if not failed else FAILED
    else:
        state = PASSED
    return {
        "state": state,
        "passed_rows": passed,
        "failed_rows": failed,
        "not_run_rows": not_run,
        "requiredStages": list(required_stages),
        "exit_code": EXIT_FAILED if (failed or not_run) else EXIT_OK,
        "rule": (
            "every requested stage must PASS; NOT RUN is never coverage and a "
            "failed stage is never masked by a successful one"
        ),
    }


def _coverage_for(statuses: list[object]) -> str:
    if all(status == PASSED for status in statuses):
        return PASSED
    if any(status == FAILED for status in statuses):
        return FAILED
    if any(status == NO_SPEECH for status in statuses):
        return NO_SPEECH
    if any(status == NO_MODEL_TEXT for status in statuses):
        return NO_MODEL_TEXT
    return NOT_RUN


def _append_note(existing: str, addition: str) -> str:
    return f"{existing} {addition}".strip()


def _probe_one_language(
    row: dict, args, budget: ProbeBudget, manifest: dict, catalog: list[CatalogLanguage]
) -> dict:
    """Run real STT, TTS and reasoning for one catalog language, or say why not.

    Two different claims are kept apart for every row:

    * ``sttNativeFixture`` / ``ttsNativeText`` — *language coverage*. Only
      a matching-language fixture, or text written in that language, can
      make these anything other than ``NOT RUN``.
    * ``sttParameterAccepted`` / ``ttsParameterAccepted`` — *parameter
      acceptance smoke checks*. A 200 response proves the endpoint took
      the value. It proves nothing about that language, and it never
      contributes to coverage.
    """
    settings = _settings(args)
    gnani_key = settings.voice.api_key.get_secret_value()
    gemini_key = settings.gemini.api_key.get_secret_value()
    entry = next(item for item in catalog if item.id == row["id"])

    # --- STT: language coverage, then a separate parameter smoke check ---
    fixture = _matching_fixture(entry, manifest, args, fixtures_io)
    if fixture is None:
        row["sttNativeFixture"] = NOT_RUN
        row["note"] = _append_note(
            row["note"],
            (
                f"NOT RUN - no {entry.id} ({entry.stt_code}) fixture is prepared; "
                "another language's audio would only prove parameter acceptance"
            ),
        )
        _stt_parameter_check(row, args, budget, catalog, settings, gnani_key, entry)
    else:
        row["fixtureId"] = fixture.fixture_id
        row["fixtureSha256"] = fixture.sha256
        row["fixtureLanguageCode"] = fixture.language_code
        raw = fixtures_io.raw_pcm_of(fixture)
        stt_seconds = stt_submitted_seconds(raw, fixture.sample_rate)
        stt_budget = budget.child(2, stt_seconds)
        try:
            config = build_config(row["sttCode"], sample_rate=fixture.sample_rate)
            stt_result = asyncio.run(
                _speech_session(config, gnani_key, raw, stt_budget, True)
            )
            budget.absorb(stt_budget)
            row["sttParameterAccepted"] = PASSED
            if stt_result.errors:
                row["sttNativeFixture"] = FAILED
                row["note"] = _append_note(
                    row["note"],
                    f"STT error frame: {stt_result.errors[0].message[:80]}",
                )
            elif stt_result.segment_count == 0:
                # Missing recognition is not a measured zero: the audio had
                # no analyzable speech for this row.
                row["sttNativeFixture"] = NO_SPEECH
                row["note"] = _append_note(
                    row["note"],
                    "STT returned no analyzable speech; this is NOT a measured "
                    "zero-filler result and NOT a language verdict",
                )
            else:
                row["sttNativeFixture"] = PASSED
                row["recognizedChars"] = len(stt_result.text)
                row["recognizedText"] = stt_result.text
        except ProviderError as exc:
            budget.absorb(stt_budget)
            row["sttNativeFixture"] = FAILED
            row["sttParameterAccepted"] = FAILED
            row["note"] = _append_note(
                row["note"], f"STT {exc.category}: {exc.detail[:80]}"
            )

    # --- TTS: native text, plus a separate parameter smoke check ---------
    voice = _voice_for(row["ttsCode"])
    if voice is None:
        row["ttsNativeText"] = NOT_RUN
        row["note"] = _append_note(
            row["note"], "TTS NOT RUN - no documented v2.5 voice for this language"
        )
    else:
        row["voice"] = voice
        native_text = NATIVE_PROBE_TEXT.get(entry.id)
        if native_text is None:
            row["ttsNativeText"] = NOT_RUN
            row["note"] = _append_note(
                row["note"],
                f"TTS NOT RUN - no native {entry.id} probe text is recorded; "
                "English text under this language's code would only prove "
                "parameter acceptance",
            )
        else:
            tts_budget = budget.child(2)
            try:
                tts_result = asyncio.run(
                    _tts_synthesize(
                        TtsConfig(
                            text=native_text,
                            voice=voice,
                            model="timbre-v2.5",
                            language=row["ttsCode"],
                            audio=AudioConfig(sample_rate=16000, container="raw"),
                        ),
                        gnani_key,
                        tts_budget,
                    )
                )
                budget.absorb(tts_budget)
                row["ttsParameterAccepted"] = PASSED
                row["ttsNativeText"] = PASSED if tts_result.total_bytes > 0 else NO_SPEECH
                row["ttsBytes"] = tts_result.total_bytes
                row["ttsTextLanguage"] = entry.id
                if row["ttsNativeText"] != PASSED:
                    row["note"] = _append_note(
                        row["note"], "TTS returned no audio for the native text"
                    )
            except ProviderError as exc:
                budget.absorb(tts_budget)
                row["ttsNativeText"] = FAILED
                row["ttsParameterAccepted"] = FAILED
                row["note"] = _append_note(
                    row["note"], f"TTS {exc.category}: {exc.detail[:60]}"
                )

    # --- reasoning reply language ---------------------------------------
    if gemini_key and settings.gemini.model:
        gem_budget = budget.child(1)
        try:
            reply = asyncio.run(
                GeminiCoach(
                    GeminiConfig(model=settings.gemini.model, store=False),
                    gemini_key,
                    budget=gem_budget,
                ).reply(
                    CoachRequest(
                        recognized_text="Say hello and ask one short follow-up question.",
                        system_instruction="You are a spoken-language conversation coach.",
                        reply_language=reply_language_name(entry),
                    )
                )
            )
            budget.absorb(gem_budget)
            if not reply.text:
                # An empty model response is a failed reasoning stage, not
                # a pass.
                row["geminiLanguage"] = NO_MODEL_TEXT
                row["note"] = _append_note(
                    row["note"], "Gemini returned no text; not a successful reply"
                )
            else:
                row["geminiLanguage"] = PASSED
                row["geminiModel"] = reply.model
                row["geminiReplyChars"] = len(reply.text)
                row["geminiReplyLanguageRequested"] = reply_language_name(entry)
                row["geminiReplyText"] = reply.text
        except ProviderError as exc:
            budget.absorb(gem_budget)
            row["geminiLanguage"] = FAILED
            row["note"] = _append_note(
                row["note"], f"Gemini {exc.category}: {exc.detail[:60]}"
            )
    else:
        row["geminiLanguage"] = NOT_RUN
        row["note"] = _append_note(
            row["note"], "reasoning NOT RUN - no model selector configured"
        )

    if row.get("sttNativeFixture") == PASSED and row.get("ttsNativeText") == PASSED:
        row["note"] = _append_note(
            row["note"],
            "API roundtrip and parameter acceptance only; intelligibility, "
            "language accuracy and coaching quality NOT verified",
        )
    return row


def _stt_parameter_check(row, args, budget, catalog, settings, gnani_key, entry) -> None:
    """Send the available fixture under this row's code, labelled as a smoke check.

    This deliberately does **not** touch the coverage columns. Its only
    answer is "did the endpoint accept the parameter".
    """
    try:
        manifest = fixtures_io.load_manifest()
        fixture = fixtures_io.resolve_fixture(args.fixture, manifest)
    except Exception:  # noqa: BLE001
        row["sttParameterAccepted"] = NOT_RUN
        return
    row["sttParameterAcceptedFixture"] = fixture.fixture_id
    row["sttParameterAcceptedFixtureLanguage"] = fixture.language_code
    try:
        stt_budget = budget.child(2)
        config = build_config(row["sttCode"], sample_rate=fixture.sample_rate)
        asyncio.run(
            _speech_session(config, gnani_key, fixtures_io.raw_pcm_of(fixture), stt_budget, True)
        )
        budget.absorb(stt_budget)
        row["sttParameterAccepted"] = PASSED
        row["note"] = _append_note(
            row["note"],
            f"parameter smoke check sent {fixture.fixture_id} "
            f"({fixture.language_code} audio) under {entry.stt_code}; this is "
            "parameter acceptance ONLY and is not {0} speech evidence".format(entry.id),
        )
    except ProviderError as exc:
        budget.absorb(stt_budget)
        row["sttParameterAccepted"] = FAILED
        row["note"] = _append_note(
            row["note"], f"STT parameter smoke check {exc.category}"
        )


#: Short neutral probe text **in the row's own language**, used only where
#: a native string is recorded. A language absent from this map is NOT RUN
#: for the TTS text stage rather than being handed English text under a
#: non-English language code.
NATIVE_PROBE_TEXT: dict[str, str] = {
    "english": "Hello. This is a short test.",
    "hinglish": "Namaste. Yeh ek chhota test hai.",
}


def _voice_for(tts_code: str) -> str | None:
    """Pick a documented v2.5 voice whose preferred language matches."""
    from gnani_coach.providers.tts import V25_PREFERRED_LANGUAGE

    for voice, language in sorted(V25_PREFERRED_LANGUAGE.items()):
        if language == tts_code:
            return voice
    return None


# ---------------------------------------------------------------------------
# helpers re-exported for clarity
# ---------------------------------------------------------------------------

CANDIDATE_MODELS = CANDIDATE_MODELS
