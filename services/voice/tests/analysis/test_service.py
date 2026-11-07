"""The analysis service: the real :class:`AnalysisPort` implementation.

What is proved here:

* the service answers on the frozen port;
* the six frozen metric keys are the ones it reports;
* the two rates carry **different** methods and **different**
  denominators;
* a missing transcription is **absent**, never a measured zero;
* the filler count is always ``insufficient_evidence`` with the reason
  ``filler_detection_unvalidated`` — no detector is shipped;
* a source that is not an explicitly trusted learner source is refused
  before a measurement is produced;
* an absent VAD asset is an honest ``unavailable``, not a crash and not a
  guess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from gnani_coach.analysis.service import (
    REPORTED_METRIC_KEYS,
    LearnerAudioAnalysis,
)
from gnani_coach.conversation.metrics import (
    DurableMetrics,
    TurnMetrics,
    validate_durable_metrics,
)
from gnani_coach.ports.analysis import AnalysisPort, AnalysisRequest
from phase05_analysis_support import MissingEngine, StubEngine, silence, tone


def _request(
    *,
    audio: bytes | None = None,
    recognized_text: str | None = "one two three four five",
    audio_source: str = "learner-audio",
) -> AnalysisRequest:
    return AnalysisRequest(
        audio=audio if audio is not None else tone(3.0),
        sample_rate=16000,
        turn_id="trn_a1b2c3d4",
        round_id="rnd_e5f6a7b8",
        recognized_text=recognized_text,
        audio_source=audio_source,  # type: ignore[arg-type]
        synthetic=False,
    )


async def _measure(service: LearnerAudioAnalysis, request: AnalysisRequest):
    return await service.measure(request)


def _by_key(measurement) -> dict[str, object]:
    return {observation.metric_key: observation for observation in measurement.result.observations}


@pytest.mark.anyio
async def test_the_service_answers_on_the_frozen_port(stub_engine: StubEngine) -> None:
    """The service is an AnalysisPort, with a measured result."""
    service = LearnerAudioAnalysis(engine=stub_engine)
    assert isinstance(service, AnalysisPort)
    result = await service.analyze(_request())
    assert result.recognition_status == "measured"
    assert result.audio_source == "learner-audio"
    assert result.observations


@pytest.mark.anyio
async def test_the_six_frozen_metric_keys_are_reported(
    stub_engine: StubEngine,
) -> None:
    """Only the allowlisted keys, and all of them."""
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request())
    keys = {observation.metric_key for observation in measurement.result.observations}
    assert keys == set(REPORTED_METRIC_KEYS)
    assert len(measurement.result.observations) == len(REPORTED_METRIC_KEYS)


@pytest.mark.anyio
async def test_the_two_rates_carry_their_own_method_and_denominator(
    stub_engine: StubEngine,
) -> None:
    """The two rates never share a method or a denominator."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request())
    observations = _by_key(measurement)

    overall = observations["speech.rate_wpm"]
    active = observations["speech.active_rate_wpm"]
    assert overall.method == "stt_words_over_learner_span"
    assert overall.denominator == "learner_span_ms"
    assert active.method == "stt_words_over_speech_active"
    assert active.denominator == "speech_active_ms"
    assert overall.denominator != active.denominator
    assert overall.status == "available"
    assert active.status == "available"
    # 5 words over 3 s and over 2 s of speech-active time.
    assert overall.value == pytest.approx(100.0)
    assert active.value == pytest.approx(150.0)


@pytest.mark.anyio
async def test_a_missing_transcription_is_absent_and_never_zero(
    stub_engine: StubEngine,
) -> None:
    """No transcript: the rate is absent, and it says why."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request(recognized_text=None))
    observations = _by_key(measurement)

    assert measurement.result.recognition_status == "missing-transcription"
    for key in ("speech.rate_wpm", "speech.active_rate_wpm"):
        observation = observations[key]
        assert observation.status == "unavailable"
        assert observation.value is None
        assert observation.unavailability_reason == "stt_unavailable"
        assert observation.recognition_status == "missing-transcription"


@pytest.mark.anyio
async def test_an_unanalyzable_transcript_is_insufficient_evidence(
    stub_engine: StubEngine,
) -> None:
    """The recogniser ran and returned nothing: insufficient evidence."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request(recognized_text=""))
    observations = _by_key(measurement)

    assert measurement.result.recognition_status == "no-analyzable-speech"
    for key in ("speech.rate_wpm", "speech.active_rate_wpm"):
        observation = observations[key]
        assert observation.status == "insufficient_evidence"
        assert observation.value is None
        assert observation.recognition_status == "no-analyzable-speech"


@pytest.mark.anyio
async def test_a_transcript_without_words_is_a_measured_zero(
    stub_engine: StubEngine,
) -> None:
    """A transcript exists: a rate of zero is a real measurement."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request(recognized_text="..."))
    observations = _by_key(measurement)

    assert measurement.result.recognition_status == "measured"
    assert observations["speech.rate_wpm"].status == "available"
    assert observations["speech.rate_wpm"].value == 0.0


@pytest.mark.anyio
async def test_the_filler_count_is_always_unvalidated(
    stub_engine: StubEngine,
) -> None:
    """No filler detector is shipped, so the count is never a number."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    for text in ("one two three four five", "", None, "..."):
        measurement = await _measure(service, _request(recognized_text=text))
        filler = _by_key(measurement)["filler.count"]
        assert filler.status == "insufficient_evidence"
        assert filler.value is None
        assert filler.unavailability_reason == "filler_detection_unvalidated"
        assert filler.method is None


@pytest.mark.anyio
async def test_an_untrusted_source_is_refused_before_any_measurement(
    stub_engine: StubEngine,
) -> None:
    """An assistant-only or unknown clip is never measured."""
    service = LearnerAudioAnalysis(engine=stub_engine)
    for source in ("assistant-audio", "unknown", ""):
        measurement = await _measure(
            service, _request(audio_source=source)
        )
        assert stub_engine.calls == [], "the VAD must not run on an untrusted clip"
        for observation in measurement.result.observations:
            assert observation.status == "unavailable"
            assert observation.value is None
            assert observation.unavailability_reason == "speech_analysis_unavailable"


@pytest.mark.anyio
async def test_a_synthetic_learner_source_is_accepted(
    stub_engine: StubEngine,
) -> None:
    """The synthetic learner source is a trusted one."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(
        service, _request(audio_source="synthetic-learner-audio")
    )
    assert measurement.result.observations[0].status == "available"
    assert measurement.result.audio_source == "synthetic-learner-audio"


@pytest.mark.anyio
async def test_the_absent_vad_asset_makes_the_pauses_unavailable(
    missing_engine: MissingEngine,
) -> None:
    """No VAD: the pauses are unavailable, and the rest still measures."""
    service = LearnerAudioAnalysis(engine=missing_engine)
    measurement = await _measure(service, _request())
    observations = _by_key(measurement)

    for key in ("pause.longest_ms", "pause.count"):
        observation = observations[key]
        assert observation.status == "unavailable"
        assert observation.value is None
        assert observation.unavailability_reason == "speech_analysis_unavailable"
    # The duration comes from the clip itself, so it is still measured.
    assert observations["turn.duration_ms"].status == "available"
    assert observations["turn.duration_ms"].value == 3000
    assert measurement.speech_active_ms == 0


@pytest.mark.anyio
async def test_the_turn_duration_is_measured_from_the_clip(
    stub_engine: StubEngine,
) -> None:
    """The span is the elapsed learner audio, on the sample clock."""
    service = LearnerAudioAnalysis(engine=stub_engine)
    audio = tone(2.0) + silence(1.0)
    measurement = await _measure(service, _request(audio=audio))
    duration = _by_key(measurement)["turn.duration_ms"]
    assert duration.method == "learner_audio_sample_clock"
    assert duration.unit == "milliseconds"
    assert duration.value == 3000


@pytest.mark.anyio
async def test_the_speech_active_time_is_reported_beside_the_observations(
    stub_engine: StubEngine,
) -> None:
    """The port returns observations; the runtime also needs the duration."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request())
    assert measurement.speech_active_ms == 2000


@pytest.mark.anyio
async def test_the_observations_write_a_valid_durable_document(
    stub_engine: StubEngine,
) -> None:
    """The measured facts become a document the frozen schema accepts."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request())

    document = DurableMetrics(
        session_id="ses_a1b2c3d4",
        recorded_at="2026-10-20T10:00:00Z",
        practice_language_id="english",
        scenario_id="everyday",
        turns=[
            TurnMetrics(
                turn_id="trn_a1b2c3d4",
                round_id="rnd_e5f6a7b8",
                duration_ms=3000,
                recognition_status=measurement.result.recognition_status,
                audio_source_classification="learner-audio",
                observations=measurement.result.observations,
                speech_active_ms=measurement.speech_active_ms,
            )
        ],
    ).to_document()

    assert validate_durable_metrics(document) == []
    schema = json.loads(
        (
            Path("packages/contracts/data/catalog.json").resolve().parents[1]
            / "schemas"
            / "durable-metrics.schema.json"
        ).read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = list(validator.iter_errors(document))
    assert errors == [], errors[0].message if errors else ""


@pytest.mark.anyio
async def test_the_durable_document_of_a_missing_transcription_is_valid(
    stub_engine: StubEngine,
) -> None:
    """A turn without a transcript may not carry a measured rate."""
    stub_engine.regions = [(0, 2000)]
    service = LearnerAudioAnalysis(engine=stub_engine)
    measurement = await _measure(service, _request(recognized_text=None))

    document = DurableMetrics(
        session_id="ses_a1b2c3d4",
        recorded_at="2026-10-20T10:00:00Z",
        practice_language_id="english",
        scenario_id="everyday",
        turns=[
            TurnMetrics(
                turn_id="trn_a1b2c3d4",
                round_id="rnd_e5f6a7b8",
                duration_ms=3000,
                recognition_status=measurement.result.recognition_status,
                audio_source_classification="learner-audio",
                observations=measurement.result.observations,
                speech_active_ms=measurement.speech_active_ms,
            )
        ],
    ).to_document()

    assert validate_durable_metrics(document) == []
    schema = json.loads(
        (
            Path("packages/contracts/data/catalog.json").resolve().parents[1]
            / "schemas"
            / "durable-metrics.schema.json"
        ).read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = list(validator.iter_errors(document))
    assert errors == [], errors[0].message if errors else ""
