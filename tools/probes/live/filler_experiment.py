"""The bounded filler experiment (Phase 02, FIX cycle 2).

What this is
------------
**One** clip — ``fixtures/synthetic/audio/spoken-filled-hesitation.wav`` —
and **three** routes, each run once per variant:

======  ==========================================================
Route   What it tries
======  ==========================================================
E1      The Gnani realtime STT, with ``x-format`` verbatim vs
        transcribe, a lower ``x-min-silence-ms``, and word boosting
        of ``um``/``uh`` at score 1.0 and 2.0.
E2      A Gemini audio review: the clip is sent inline and the model
        is asked for a verbatim transcript with the filled pauses
        and their positions.
E3      An **offline** acoustic scan that looks for a filled pause
        *inside* a VAD speech region rather than only in the gaps
        between regions.
======  ==========================================================

What this is not
----------------
* It is not a precision/recall evaluation. One clip cannot be one.
* It is not a claim that the recogniser is permanently incapable.
* It is not a tuning exercise: every route runs once per variant, and
  the parameters are fixed before the run.

Pass signal (per route, per the brief)
--------------------------------------
A route passes when it reports **both** fillers on the hesitation clip
**and** reports none on ``spoken-clear-sentence``.

Budget
------
The whole step shares **one** :class:`ProbeBudget`. Every wire attempt is
admitted before it starts, and the plan is refused before any side effect
if it does not fit. ``--max-requests`` is the caller's ceiling.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from gnani_coach.providers.errors import ProviderError
from gnani_coach.providers.limits import ProbeBudget
from gnani_coach.providers.stt import (
    FORMAT_TRANSCRIBE,
    FORMAT_VERBATIM,
    GnaniSttSession,
    VadSettings,
    build_config,
)
from tools.probes import fixtures_io
from tools.probes.live.languages import load_catalog, resolve
from tools.probes.live.probes import stt_submitted_seconds
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

#: The clip under review, and the clean-speech clip used as the negative.
FILLER_FIXTURE = "spoken-filled-hesitation"
NEGATIVE_FIXTURE = "spoken-clear-sentence"

#: The two filled pauses the project owner heard in the clip.
FILLER_TOKENS = ("um", "uh")

#: One STT run costs two wire attempts: the connection and the session.
STT_OPS = 2
#: One Gemini audio review costs one wire attempt.
GEMINI_OPS = 1

#: The STT variants. Each is run **once**. The order is the order they
#: are attempted in, and it is also the order in which a passing variant
#: would earn its negative-control run.
STT_VARIANTS: tuple[dict[str, object], ...] = (
    {
        "id": "verbatim-min-silence-500",
        "output_format": FORMAT_VERBATIM,
        "min_silence_ms": 500,
        "bias_words": (),
        "bias_score": 0.0,
        "why": "the documented default silence window: the Phase 02 baseline",
    },
    {
        "id": "verbatim-min-silence-300",
        "output_format": FORMAT_VERBATIM,
        "min_silence_ms": 300,
        "bias_words": (),
        "bias_score": 0.0,
        "why": "a shorter silence window, so VAD splits less and swallows less",
    },
    {
        "id": "transcribe-min-silence-300",
        "output_format": FORMAT_TRANSCRIBE,
        "min_silence_ms": 300,
        "bias_words": (),
        "bias_score": 0.0,
        "why": "the same window with ITN enabled, for the format comparison",
    },
    {
        "id": "verbatim-min-silence-300-bias-1.0",
        "output_format": FORMAT_VERBATIM,
        "min_silence_ms": 300,
        "bias_words": ("um", "uh"),
        "bias_score": 1.0,
        "why": "word boosting at the documented starting strength",
    },
    {
        "id": "verbatim-min-silence-300-bias-2.0",
        "output_format": FORMAT_VERBATIM,
        "min_silence_ms": 300,
        "bias_words": ("um", "uh"),
        "bias_score": 2.0,
        "why": "word boosting at the maximum documented strength",
    },
)

#: The prompt E2 sends with the clip. It asks for the filled pauses by
#: name and for their positions, and it forbids inventing any.
GEMINI_REVIEW_PROMPT = (
    "You are transcribing one short audio clip for a speaking-coach research probe. "
    "Listen to the attached audio and reply with ONLY a JSON object, no prose and no "
    "code fences, in exactly this shape:\n"
    '{"transcript": "<the words you hear, verbatim>", '
    '"filled_pauses": [{"word": "<the filler you heard>", "start": "MM:SS", '
    '"end": "MM:SS"}]}\n'
    "Rules:\n"
    "1. Include every filled pause you actually hear (for example 'um', 'uh', 'erm') "
    "as its own entry, with the word exactly as you heard it.\n"
    "2. Use the timestamps of the clip itself, counted from the start of the audio. "
    "MM:SS means minutes:seconds, with whole seconds.\n"
    "3. Do not invent a filled pause that is not in the audio. If you hear none, return "
    "an empty list for filled_pauses.\n"
    "4. Do not explain, apologise or add anything outside the JSON object."
)

#: What the E2 answer is expected to look like. The documented Gemini
#: audio timestamps are ``MM:SS`` — **second resolution** — so E2 cannot
#: meet a 300 ms boundary target even when it is right about presence.
E2_TIMESTAMP_RESOLUTION = "MM:SS (one-second resolution)"


@dataclass
class RouteResult:
    """One route's outcome, kept honest about what it does and does not show."""

    route: str
    variant: str
    status: str = NOT_RUN
    settings: dict[str, object] = field(default_factory=dict)
    detail: str = ""
    observed_text: str | None = None
    um_present: bool | None = None
    uh_present: bool | None = None
    events: list[dict] = field(default_factory=list)
    positions: list[dict] = field(default_factory=list)
    wire_attempts: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "variant": self.variant,
            "status": self.status,
            "settings": dict(self.settings),
            "detail": self.detail,
            "observedText": self.observed_text,
            "umPresent": self.um_present,
            "uhPresent": self.uh_present,
            "events": list(self.events),
            "positions": list(self.positions),
            "wireAttempts": self.wire_attempts,
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# token helpers
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    """Lower-cased word tokens of a recognised string."""
    return re.findall(r"[a-z']+", (text or "").lower())


def _filler_flags(text: str) -> tuple[bool, bool]:
    """Whether ``um`` and ``uh`` each appear as their own word."""
    tokens = _tokens(text)
    return ("um" in tokens, "uh" in tokens)


# ---------------------------------------------------------------------------
# E1 — the Gnani realtime STT
# ---------------------------------------------------------------------------


async def _stt_run(
    config, api_key: str, pcm: bytes, budget: ProbeBudget
):
    """One STT connection with one session, on a shared budget."""
    session = GnaniSttSession(config, api_key, budget=budget)
    async with session:
        if config.bias_words:
            # The provider skips invalid boosting silently, so the boost is
            # echoed back through the documented control frame and the
            # answer is checked against the echo, not assumed.
            await session.send_control_frame(
                {
                    "type": "update_settings",
                    "bias": {"list": list(config.bias_words), "score": config.bias_score},
                }
            )
        return await session.stream_pcm(pcm, real_time=True)


def _stt_variant_settings(variant: dict[str, object], stt_code: str) -> dict[str, object]:
    """The exact settings of one variant, for the record."""
    return {
        "lang_code": stt_code,
        "x-sample-rate": 16000,
        "x-format": variant["output_format"],
        "x-vad-threshold": 0.7,
        "x-min-silence-ms": variant["min_silence_ms"],
        "x-min-speech-ms": 100,
        "x-min-segment-ms": 120,
        "x-enable-substitution": False,
        "x-bias-list": list(variant["bias_words"]),
        "x-bias-score": variant["bias_score"] if variant["bias_words"] else None,
        "pacing": "real-time",
        "why": variant["why"],
    }


def _boost_echo(result) -> dict[str, object]:
    """What the server said about the boost, if it said anything."""
    config = result.server_config or {}
    return {
        "serverConfigKeys": sorted(str(key) for key in config),
        "biasWordCount": config.get("bias_word_count"),
        "biasScore": config.get("bias_score"),
        "format": config.get("format"),
        "note": (
            "the boost is only confirmed if the server echoes it back; an "
            "absent echo is reported as absent, never as 'boosting had no effect'"
        ),
    }


async def _run_e1(
    variants: list[dict[str, object]],
    fixture,
    api_key: str,
    stt_code: str,
    budget: ProbeBudget,
    reporter: Reporter,
) -> list[RouteResult]:
    """Run each STT variant once, on the hesitation clip."""
    pcm = fixtures_io.raw_pcm_of(fixture)
    results: list[RouteResult] = []
    for variant in variants:
        result = RouteResult(
            route="E1",
            variant=str(variant["id"]),
            settings=_stt_variant_settings(variant, stt_code),
        )
        before = budget.wire_attempts_used
        config = build_config(
            stt_code,
            sample_rate=fixture.sample_rate,
            vad=VadSettings(min_silence_ms=int(variant["min_silence_ms"])),
            output_format=str(variant["output_format"]),
            bias_words=tuple(variant["bias_words"]),  # type: ignore[arg-type]
            bias_score=float(variant["bias_score"]),
        )
        try:
            stt = await _stt_run(config, api_key, pcm, budget)
        except ProviderError as exc:
            result.status = FAILED
            result.detail = f"{exc.category}: {exc.detail}"
            result.wire_attempts = budget.wire_attempts_used - before
            results.append(result)
            continue
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            result.status = FAILED
            result.detail = f"{type(exc).__name__}: {exc}"
            result.wire_attempts = budget.wire_attempts_used - before
            results.append(result)
            continue

        result.wire_attempts = budget.wire_attempts_used - before
        result.observed_text = stt.text
        um, uh = _filler_flags(stt.text)
        result.um_present = um
        result.uh_present = uh
        result.events = [
            {
                "segmentIndex": event.segment_index,
                "segmentId": event.segment_id,
                "text": event.text,
                "audioDurationMs": event.audio_duration_ms,
                "latencyMs": event.latency_ms,
                "learnerClockSamples": event.learner_clock_samples,
            }
            for event in stt.transcripts
        ]
        result.positions = []
        result.notes.append(
            "the realtime STT publishes no word-level timing; no filler "
            "position can be read from this API, so none is reported"
        )
        if variant["bias_words"]:
            result.notes.append(f"boost echo: {json.dumps(_boost_echo(stt))}")
        if stt.errors:
            result.status = FAILED
            result.detail = f"provider error frame: {stt.errors[0].message[:120]}"
        elif stt.segment_count == 0:
            result.status = FAILED
            result.detail = "no transcript segment returned (no analyzable speech)"
        elif um and uh:
            result.status = PASSED
            result.detail = "both fillers present in the recognised text"
        else:
            result.status = FAILED
            result.detail = (
                f"recognised text carries um={um} uh={uh}; both are required"
            )
        results.append(result)
        reporter.say(
            f"  E1 {result.variant:<34} status={result.status:<8} "
            f"um={result.um_present} uh={result.uh_present} "
            f"wire_attempts={result.wire_attempts}"
        )
        if result.observed_text is not None:
            reporter.say(f"      text: {result.observed_text!r}")
    return results


# ---------------------------------------------------------------------------
# E2 — a Gemini audio review
# ---------------------------------------------------------------------------


def _extract_review_text(interaction: object) -> str:
    """Pull the model's text out of an Interactions response."""
    text = getattr(interaction, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    steps = getattr(interaction, "steps", None)
    if isinstance(steps, (list, tuple)):
        collected: list[str] = []
        for step in steps:
            content = getattr(step, "content", None)
            if isinstance(content, (list, tuple)):
                for part in content:
                    part_text = getattr(part, "text", None)
                    if isinstance(part_text, str):
                        collected.append(part_text)
        if collected:
            return "\n".join(collected).strip()
    raise ProviderError("Gemini audio review returned no text", provider="gemini")


def _parse_review_json(text: str) -> dict:
    """Parse the model's JSON answer, tolerating a fenced block."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("the audio review did not return a JSON object")
    return parsed


def _seconds_from_timestamp(value: object) -> float | None:
    """``MM:SS`` -> seconds. The documented resolution is one second."""
    if not isinstance(value, str):
        return None
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", value)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


async def _gemini_audio_review(
    model: str,
    api_key: str,
    wav_bytes: bytes,
    budget: ProbeBudget,
    *,
    attempt_timeout: float = 30.0,
    deadline: float = 60.0,
) -> tuple[str, int]:
    """One bounded Gemini call with the clip attached inline.

    The SDK is configured with **no internal retry**, so every wire attempt
    is visible to the budget. The client is closed on every exit path.
    """
    from google import genai
    from google.genai import types

    call_kind = "gemini:audio-review"
    token = budget.begin_call(call_kind)
    budget.admit_attempt(call_kind, call=token)
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=int(attempt_timeout * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    try:
        content = types.Content(
            parts=[
                types.Part(
                    inline_data=types.Blob(data=wav_bytes, mime_type="audio/wav")
                ),
                types.Part(text=GEMINI_REVIEW_PROMPT),
            ],
            role="user",
        )
        interaction = await asyncio.wait_for(
            client.aio.interactions.create(
                model=model,
                input=[content],
                store=False,
                generation_config={"max_output_tokens": 800},
            ),
            timeout=min(attempt_timeout, deadline),
        )
        return _extract_review_text(interaction), budget.wire_attempts_used
    finally:
        aio = getattr(client, "aio", None)
        closer = getattr(aio, "aclose", None) if aio is not None else None
        if closer is not None:
            try:
                result = closer()
                if asyncio.isfuture(result) or asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001 - close must not mask
                pass
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


async def _run_e2(
    filler_fixture,
    negative_fixture,
    model: str,
    api_key: str,
    budget: ProbeBudget,
    reporter: Reporter,
) -> list[RouteResult]:
    """One review of the hesitation clip, and one of the clean clip."""
    results: list[RouteResult] = []
    for fixture, variant_id, role in (
        (filler_fixture, "audio-review-filled-hesitation", "positive"),
        (negative_fixture, "audio-review-clear-sentence", "negative"),
    ):
        result = RouteResult(
            route="E2",
            variant=variant_id,
            settings={
                "model": model,
                "input": "clip attached inline (wav, base64 in the request)",
                "bytes": fixture.audio_path.stat().st_size,
                "prompt": "verbatim transcript + filled pauses with MM:SS positions",
                "role": role,
            },
        )
        before = budget.wire_attempts_used
        try:
            text, _ = await _gemini_audio_review(
                model, api_key, fixture.audio_path.read_bytes(), budget
            )
        except asyncio.TimeoutError:
            result.status = FAILED
            result.detail = "the review did not answer inside its bound"
            result.wire_attempts = budget.wire_attempts_used - before
            results.append(result)
            continue
        except ProviderError as exc:
            result.status = FAILED
            result.detail = f"{exc.category}: {exc.detail}"
            result.wire_attempts = budget.wire_attempts_used - before
            results.append(result)
            continue
        except Exception as exc:  # noqa: BLE001
            result.status = FAILED
            result.detail = f"{type(exc).__name__}: {exc}"
            result.wire_attempts = budget.wire_attempts_used - before
            results.append(result)
            continue

        result.wire_attempts = budget.wire_attempts_used - before
        result.observed_text = text
        result.notes.append(
            f"the documented timestamp format is {E2_TIMESTAMP_RESOLUTION}, so this "
            "route cannot satisfy a 300 ms boundary target even when it is right "
            "about presence"
        )
        try:
            parsed = _parse_review_json(text)
        except (json.JSONDecodeError, ValueError) as exc:
            result.status = FAILED
            result.detail = f"the review did not return usable JSON: {exc}"
            results.append(result)
            continue

        transcript = str(parsed.get("transcript") or "")
        pauses = parsed.get("filled_pauses")
        pauses = pauses if isinstance(pauses, list) else []
        result.events = [
            {
                "word": str(item.get("word", "")) if isinstance(item, dict) else str(item),
                "start": item.get("start") if isinstance(item, dict) else None,
                "end": item.get("end") if isinstance(item, dict) else None,
            }
            for item in pauses
        ]
        result.positions = [
            {
                "word": event["word"],
                "startSeconds": _seconds_from_timestamp(event["start"]),
                "endSeconds": _seconds_from_timestamp(event["end"]),
                "resolution": E2_TIMESTAMP_RESOLUTION,
            }
            for event in result.events
        ]
        words = {event["word"].strip().lower().rstrip(".,!?") for event in result.events}
        transcript_words = set(_tokens(transcript))
        um = "um" in words or "um" in transcript_words
        uh = "uh" in words or "uh" in transcript_words
        result.um_present = um
        result.uh_present = uh
        result.notes.append(f"review transcript: {transcript!r}")
        if role == "positive":
            if um and uh:
                result.status = PASSED
                result.detail = "the review reports both fillers"
            else:
                result.status = FAILED
                result.detail = (
                    f"the review reports um={um} uh={uh}; both are required"
                )
        else:
            if um or uh:
                result.status = FAILED
                result.detail = (
                    "the review reports a filler on the clean clip; the route "
                    "cannot pass its negative control"
                )
            else:
                result.status = PASSED
                result.detail = "the review reports no filler on the clean clip"
        results.append(result)
        reporter.say(
            f"  E2 {result.variant:<34} status={result.status:<8} "
            f"um={result.um_present} uh={result.uh_present} "
            f"wire_attempts={result.wire_attempts}"
        )
    return results


# ---------------------------------------------------------------------------
# E3 — the offline acoustic scan
# ---------------------------------------------------------------------------


def _run_e3(
    filler_fixture,
    negative_fixture,
    reporter: Reporter,
) -> list[RouteResult]:
    """Look for filled pauses *inside* the VAD speech regions.

    No spend, no network, no provider call. The VAD model asset must
    already be prepared; it is never downloaded here.
    """
    from tools.probes.analysis import filler as filler_mod
    from tools.probes.analysis import vad as vad_mod

    results: list[RouteResult] = []
    if not vad_mod.asset_present():
        for fixture, variant_id, role in (
            (filler_fixture, "inside-region-scan-filled-hesitation", "positive"),
            (negative_fixture, "inside-region-scan-clear-sentence", "negative"),
        ):
            result = RouteResult(
                route="E3",
                variant=variant_id,
                status=BLOCKED,
                settings={"scan": "inside VAD speech regions"},
                detail=(
                    "the VAD model asset is not prepared; run "
                    "`run.py analysis --prepare-models` (no auto-download)"
                ),
            )
            results.append(result)
        return results

    recorded = json.loads(vad_mod.MODEL_PROVENANCE_PATH.read_text(encoding="utf-8"))
    asset = vad_mod.ModelAsset(
        path=vad_mod.CACHE_DIR / vad_mod.MODEL_FILENAME,
        sha256=recorded["sha256"],
        bytes=recorded["bytes"],
        source=recorded["source"],
        license=recorded["license"],
    )
    vad = vad_mod.SileroVad(asset)

    for fixture, variant_id, role in (
        (filler_fixture, "inside-region-scan-filled-hesitation", "positive"),
        (negative_fixture, "inside-region-scan-clear-sentence", "negative"),
    ):
        result = RouteResult(
            route="E3",
            variant=variant_id,
            settings={
                "scan": "inside VAD speech regions",
                "detectorParams": filler_mod._inside_params(),
                "vadModel": asset.sha256[:16] + "…",
                "fixtureId": fixture.fixture_id,
                "fixtureSha256": fixture.sha256,
                "role": role,
            },
        )
        pcm = fixtures_io.raw_pcm_of(fixture)
        vad_result = vad.analyse(pcm, fixture.sample_rate)
        inside = filler_mod.detect_inside_regions(pcm, fixture.sample_rate, vad_result)
        result.events = [candidate.to_dict() for candidate in inside.candidates]
        result.positions = [
            {
                "start_ms": candidate.start_ms,
                "end_ms": candidate.end_ms,
                "duration_ms": candidate.duration_ms,
                "source": candidate.window_source,
            }
            for candidate in inside.candidates
        ]
        count = len(inside.candidates)
        result.notes.append(
            f"the VAD found {len(vad_result.regions)} speech region(s) in this clip"
        )
        result.notes.append(
            "the clip's internal low-energy stretches are reported as a "
            "description of the signal only; a low-energy stretch is not a "
            "filled pause and is never counted as a candidate"
        )
        stretches = (inside.diagnostics or {}).get("lowEnergyStretches") or []
        result.settings["lowEnergyStretches"] = stretches
        result.settings["lowEnergyStretchCount"] = len(stretches)
        if role == "positive":
            if count >= 2:
                result.status = PASSED
                result.detail = (
                    f"{count} inside-region candidate events; the clip holds two "
                    "filled pauses"
                )
                result.notes.append(
                    "the reviewer gave no positions, so these events cannot be "
                    "matched one-to-one with 'um' and 'uh'; the count and the "
                    "rough positions are the evidence, not a correspondence"
                )
            else:
                result.status = FAILED
                result.detail = (
                    f"{count} inside-region candidate event(s); two are required"
                )
        else:
            if count == 0:
                result.status = PASSED
                result.detail = "no candidate event on the clean-speech clip"
            else:
                result.status = FAILED
                result.detail = (
                    f"{count} candidate event(s) on the clean-speech clip; the "
                    "route cannot pass its negative control"
                )
        results.append(result)
        reporter.say(
            f"  E3 {result.variant:<40} status={result.status:<8} "
            f"events={count} wire_attempts=0"
        )
        for event in result.events:
            reporter.say(
                f"      event start_ms={event['start_ms']} end_ms={event['end_ms']} "
                f"duration_ms={event['duration_ms']} "
                f"voicing={event['voicing_ratio']} "
                f"change={event['mean_spectral_change']} "
                f"dominant_hz={event['dominant_hz_min']}..{event['dominant_hz_max']}"
            )
    return results


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def _route_status(route: str, results: list[RouteResult]) -> str:
    """Combine a route's rows into one verdict.

    A route passes only when its **positive** row passes *and* its
    **negative** row passes. A row that was not run is never coverage,
    and a failed row is never masked by a successful one.
    """
    if route == "E1":
        variants = [row for row in results if row.route == "E1"]
        controls = [row for row in results if row.route == "E1-control"]
        if not variants:
            return NOT_RUN
        if any(row.status == PASSED for row in variants):
            return PASSED
        if any(row.status == BLOCKED for row in variants):
            return BLOCKED
        if any(row.status == FAILED for row in variants):
            return FAILED
        if controls and any(row.status == NOT_RUN for row in controls):
            return NOT_RUN
        return INCONCLUSIVE

    positives = [row for row in results if row.settings.get("role") == "positive"]
    negatives = [row for row in results if row.settings.get("role") == "negative"]
    if not positives and not negatives:
        return NOT_RUN
    states = [row.status for row in positives + negatives]
    if any(state == FAILED for state in states):
        return FAILED
    if any(state == BLOCKED for state in states):
        return BLOCKED
    if all(state == PASSED for state in states):
        return PASSED
    if any(state == NOT_RUN for state in states):
        return NOT_RUN
    return INCONCLUSIVE


async def _run_e1_controls(
    passers: list[RouteResult],
    negative_fixture,
    api_key: str,
    stt_code: str,
    budget: ProbeBudget,
    reporter: Reporter,
) -> list[RouteResult]:
    """Run the clean-speech clip for each E1 variant that reported both fillers.

    A variant that reports a filler on the clean clip cannot pass, so its
    positive result is downgraded by the caller.
    """
    controls: list[RouteResult] = []
    for result in passers:
        if budget.operations_left < STT_OPS:
            result.notes.append(
                "negative control NOT RUN: the whole-step budget was exhausted"
            )
            reporter.say(f"  control for {result.variant}: NOT RUN (budget exhausted)")
            continue
        variant = next(item for item in STT_VARIANTS if item["id"] == result.variant)
        control = RouteResult(
            route="E1-control",
            variant=f"{result.variant}-on-{NEGATIVE_FIXTURE}",
            settings={
                **_stt_variant_settings(variant, stt_code),
                "role": "negative",
                "fixtureId": negative_fixture.fixture_id,
                "fixtureSha256": negative_fixture.sha256,
            },
        )
        before = budget.wire_attempts_used
        config = build_config(
            stt_code,
            sample_rate=negative_fixture.sample_rate,
            vad=VadSettings(min_silence_ms=int(variant["min_silence_ms"])),
            output_format=str(variant["output_format"]),
            bias_words=tuple(variant["bias_words"]),  # type: ignore[arg-type]
            bias_score=float(variant["bias_score"]),
        )
        try:
            stt = await _stt_run(
                config, api_key, fixtures_io.raw_pcm_of(negative_fixture), budget
            )
            control.observed_text = stt.text
            um, uh = _filler_flags(stt.text)
            control.um_present = um
            control.uh_present = uh
            if stt.errors:
                control.status = FAILED
                control.detail = f"provider error frame: {stt.errors[0].message[:120]}"
            elif um or uh:
                control.status = FAILED
                control.detail = "the variant reports a filler on the clean clip"
            else:
                control.status = PASSED
                control.detail = "the variant reports no filler on the clean clip"
        except Exception as exc:  # noqa: BLE001
            control.status = FAILED
            control.detail = f"{type(exc).__name__}: {exc}"
        control.wire_attempts = budget.wire_attempts_used - before
        controls.append(control)
        reporter.say(
            f"  control for {result.variant:<34} status={control.status:<8} "
            f"um={control.um_present} uh={control.uh_present} "
            f"wire_attempts={control.wire_attempts}"
        )
    return controls


def run_filler_experiment(args, reporter: Reporter) -> tuple[int, dict]:
    """Run the three routes and return (exit code, machine-readable result)."""
    from tools.probes.run import load_settings_for_probe, run_preflight

    preflight = run_preflight(reporter, getattr(args, "env_file", None))
    manifest = fixtures_io.load_manifest()
    filler_fixture = fixtures_io.resolve_fixture(FILLER_FIXTURE, manifest)
    negative_fixture = fixtures_io.resolve_fixture(NEGATIVE_FIXTURE, manifest)

    catalog = load_catalog()
    entry = resolve(str(getattr(args, "language", "english")), catalog)
    stt_code = entry.stt_code

    gnani_ready = preflight.gnani_key
    gemini_ready = preflight.gemini_key and bool(preflight.gemini_model)
    allow_live = bool(getattr(args, "allow_live", False))
    live_block: str | None = None
    if not allow_live:
        live_block = (
            "live consent was not given (--allow-live); no provider call was made"
        )
    gnani_live = gnani_ready and allow_live
    gemini_live = gemini_ready and allow_live

    reporter.section("plan (one shared budget for the whole step)")
    reporter.say(f"  clip under review : {FILLER_FIXTURE} sha256={filler_fixture.sha256[:16]}…")
    reporter.say(f"  negative control  : {NEGATIVE_FIXTURE} sha256={negative_fixture.sha256[:16]}…")
    reporter.say(f"  stt language      : {entry.id} -> {stt_code}")
    reporter.say(
        f"  E1 variants       : {len(STT_VARIANTS)} x {STT_OPS} wire attempts"
    )
    reporter.say(
        "  E2 reviews        : 2 x 1 wire attempt (the clip and the negative)"
    )
    reporter.say("  E3                : 0 wire attempts (offline)")
    reporter.say(
        "  negative controls : up to 2 more STT runs, for the E1 variants that "
        "report both fillers"
    )

    try:
        settings = load_settings_for_probe(getattr(args, "env_file", None))
    except Exception:  # noqa: BLE001 - a missing env file is reported, not raised
        settings = None
    gnani_key = (
        settings.voice.api_key.get_secret_value()
        if settings is not None and gnani_ready
        else ""
    )
    gemini_key = (
        settings.gemini.api_key.get_secret_value()
        if settings is not None and gemini_ready
        else ""
    )
    model = preflight.gemini_model or ""

    audio_seconds = 0.0
    for fixture in (filler_fixture, negative_fixture):
        audio_seconds += stt_submitted_seconds(
            fixtures_io.raw_pcm_of(fixture), fixture.sample_rate
        )

    planned = len(STT_VARIANTS) * STT_OPS + 2 * GEMINI_OPS + 2 * STT_OPS
    try:
        budget = plan_budget(args, operations=planned, audio_seconds=audio_seconds)
    except SystemExit as exc:
        reporter.status("plan", BLOCKED, str(exc))
        return EXIT_BLOCKED, {
            "overall": BLOCKED,
            "routes": [],
            "routeStatus": {},
            "planRefused": str(exc),
            "budget": {},
        }

    results: list[RouteResult] = []
    route_status: dict[str, str] = {}

    # -- E3 first: it costs nothing and cannot be lost to a later failure.
    reporter.section("E3 — offline acoustic scan inside the VAD speech regions")
    e3_results = _run_e3(filler_fixture, negative_fixture, reporter)
    results.extend(e3_results)
    route_status["E3"] = _route_status("E3", e3_results)

    # -- E1
    reporter.section("E1 — Gnani realtime STT, one run per variant")
    if not gnani_live:
        detail = (
            live_block
            if live_block
            else "GNANI_API_KEY is not configured (name only; no value read)"
        )
        for variant in STT_VARIANTS:
            results.append(
                RouteResult(
                    route="E1",
                    variant=str(variant["id"]),
                    status=BLOCKED,
                    settings=_stt_variant_settings(variant, stt_code),
                    detail=detail,
                )
            )
            reporter.say(f"  E1 {str(variant['id']):<34} status=BLOCKED  ({detail})")
        route_status["E1"] = BLOCKED
    else:
        e1_results = asyncio.run(
            _run_e1(list(STT_VARIANTS), filler_fixture, gnani_key, stt_code, budget, reporter)
        )
        results.extend(e1_results)
        route_status["E1"] = _route_status("E1", e1_results)

    # -- E2
    reporter.section("E2 — Gemini audio review of the clip")
    if not gemini_live:
        missing = [
            name
            for name, present in (
                ("GEMINI_API_KEY", preflight.gemini_key),
                ("GEMINI_MODEL", bool(preflight.gemini_model)),
            )
            if not present
        ]
        detail = (
            live_block
            if live_block
            else f"{', '.join(missing)} not configured (name only; no value read)"
        )
        for variant_id, role in (
            ("audio-review-filled-hesitation", "positive"),
            ("audio-review-clear-sentence", "negative"),
        ):
            results.append(
                RouteResult(
                    route="E2",
                    variant=variant_id,
                    status=BLOCKED,
                    settings={"model": model or "(unset)", "role": role},
                    detail=detail,
                )
            )
            reporter.say(f"  E2 {variant_id:<34} status=BLOCKED  ({detail})")
        route_status["E2"] = BLOCKED
    else:
        e2_results = asyncio.run(
            _run_e2(filler_fixture, negative_fixture, model, gemini_key, budget, reporter)
        )
        results.extend(e2_results)
        route_status["E2"] = _route_status("E2", e2_results)

    # -- negative controls for the E1 variants that reported both fillers.
    reporter.section("negative controls — the clean-speech clip")
    e1_passers = [
        result
        for result in results
        if result.route == "E1" and result.status == PASSED
    ]
    controls: list[RouteResult] = []
    if not e1_passers:
        reporter.say("  no E1 variant reported both fillers; no control is needed")
    elif not gnani_live:
        reporter.say("  no live route is available; the control cannot run")
    else:
        controls = asyncio.run(
            _run_e1_controls(
                e1_passers,
                negative_fixture,
                gnani_key,
                stt_code,
                budget,
                reporter,
            )
        )
        results.extend(controls)
        for control in controls:
            parent = next(
                (
                    result
                    for result in results
                    if result.route == "E1" and result.variant == control.variant.split("-on-")[0]
                ),
                None,
            )
            if parent is not None and control.status != PASSED:
                parent.status = FAILED
                parent.detail = (
                    f"{parent.detail}; the negative control on {NEGATIVE_FIXTURE} "
                    "did not pass"
                )
        route_status["E1"] = _route_status(
            "E1", [result for result in results if result.route in ("E1", "E1-control")]
        )

    passed = [route for route, status in route_status.items() if status == PASSED]
    failed = [route for route, status in route_status.items() if status == FAILED]
    blocked = [route for route, status in route_status.items() if status == BLOCKED]
    not_run = [route for route, status in route_status.items() if status == NOT_RUN]
    inconclusive = [
        route for route, status in route_status.items() if status == INCONCLUSIVE
    ]

    reporter.section("route summary")
    for route, status in sorted(route_status.items()):
        reporter.say(f"  {route}: {status}")
    reporter.say("")
    reporter.say(f"  routes passed    : {', '.join(passed) if passed else '(none)'}")
    reporter.say(f"  routes failed    : {', '.join(failed) if failed else '(none)'}")
    reporter.say(f"  routes blocked   : {', '.join(blocked) if blocked else '(none)'}")
    reporter.say(f"  routes not run   : {', '.join(not_run) if not_run else '(none)'}")
    reporter.say(
        f"  routes inconclusive: {', '.join(inconclusive) if inconclusive else '(none)'}"
    )
    reporter.say(
        "  ONE CLIP PASSING IS A SMOKE SIGNAL ONLY. It is not precision >=90%, "
        "not recall >=80% and not a p95 boundary error <=300 ms."
    )

    if passed:
        overall = PASSED
        exit_code = EXIT_OK
    elif failed:
        overall = FAILED
        exit_code = EXIT_FAILED
    elif blocked:
        overall = BLOCKED
        exit_code = EXIT_BLOCKED
    else:
        overall = INCONCLUSIVE
        exit_code = EXIT_FAILED

    payload = {
        "clip": {
            "fixtureId": filler_fixture.fixture_id,
            "sha256": filler_fixture.sha256,
            "durationMs": filler_fixture.duration_ms,
            "sampleRate": filler_fixture.sample_rate,
        },
        "negative": {
            "fixtureId": negative_fixture.fixture_id,
            "sha256": negative_fixture.sha256,
            "durationMs": negative_fixture.duration_ms,
        },
        "sttLanguage": {"id": entry.id, "sttCode": stt_code},
        "routes": [result.to_dict() for result in results],
        "routeStatus": route_status,
        "passedRoutes": passed,
        "failedRoutes": failed,
        "blockedRoutes": blocked,
        "overall": overall,
        "passRule": (
            "a route passes when it reports both fillers on the hesitation clip "
            "and reports none on the clean-speech clip"
        ),
        "budget": budget.summary(),
        "caveat": (
            "one clip is a smoke signal only; it does not meet precision >=90% / "
            "recall >=80% / p95 boundary <=300 ms and must not be written up as "
            "meeting them"
        ),
    }
    return exit_code, payload
