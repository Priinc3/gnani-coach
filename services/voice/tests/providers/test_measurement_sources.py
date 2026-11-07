"""Measurement source trust and recognition status [FIX-1 P02-07].

Negative cases are the point of this module: an empty source set, an
assistant-only clip, a mixed clip, an unknown classification and an
untrusted learner source must all be **refused**, not measured.

No shared schema is edited here. The shared contract is owned by
Phase 03; this module only tightens the probe-level validation.
"""

from __future__ import annotations

import pytest

from gnani_coach.providers.errors import InvalidRequestError
from tools.probes.analysis.metrics import (
    RECOGNITION_MEASURED,
    RECOGNITION_MISSING,
    RECOGNITION_NO_SPEECH,
    ROLE_ASSISTANT,
    ROLE_LEARNER,
    ROLE_UNKNOWN,
    SYNTHETIC_LEARNER,
    ClipSource,
    assert_no_assistant_audio,
    assert_trusted_learner_source,
    compute,
)


# ---------------------------------------------------------------------------
# trusted source
# ---------------------------------------------------------------------------


def test_a_trusted_synthetic_learner_source_is_accepted():
    assert_trusted_learner_source([SYNTHETIC_LEARNER])


def test_a_trusted_real_learner_source_is_accepted():
    source = ClipSource(label="learner-mic", role=ROLE_LEARNER, trusted=True)
    assert_trusted_learner_source([source])


def test_an_empty_source_set_is_refused():
    with pytest.raises(InvalidRequestError) as excinfo:
        assert_trusted_learner_source([])
    assert "no audio source" in str(excinfo.value)


def test_a_none_source_set_is_refused():
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source(None)


def test_an_assistant_only_clip_is_refused():
    source = ClipSource(label="assistant-tts", role=ROLE_ASSISTANT, trusted=True)
    with pytest.raises(InvalidRequestError) as excinfo:
        assert_trusted_learner_source([source])
    assert "assistant audio" in str(excinfo.value)


def test_a_mixed_clip_is_refused():
    learner = ClipSource(label="learner", role=ROLE_LEARNER, trusted=True)
    assistant = ClipSource(label="assistant", role=ROLE_ASSISTANT, trusted=True)
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source([learner, assistant])


def test_an_unknown_classification_is_refused():
    source = ClipSource(label="mystery", role=ROLE_UNKNOWN, trusted=True)
    with pytest.raises(InvalidRequestError) as excinfo:
        assert_trusted_learner_source([source])
    assert "unknown role" in str(excinfo.value)


def test_an_untrusted_learner_source_is_refused():
    source = ClipSource(label="learner", role=ROLE_LEARNER, trusted=False)
    with pytest.raises(InvalidRequestError) as excinfo:
        assert_trusted_learner_source([source])
    assert "not explicitly trusted" in str(excinfo.value)


def test_a_label_alone_does_not_establish_speaker_identity():
    """The module must not imply diarization or echo cancellation."""
    metrics = compute(
        clip_span_ms=1000,
        speech_active_ms=800,
        recognized_text="hello there",
        source_labels=["synthetic-learner"],
    )
    payload = metrics.to_dict()
    assert "diarization" in payload["source_caveat"]
    assert "echo" in payload["source_caveat"]


# ---------------------------------------------------------------------------
# the label-only guard kept for existing callers
# ---------------------------------------------------------------------------


def test_the_label_only_guard_also_refuses_an_empty_set():
    with pytest.raises(InvalidRequestError):
        assert_no_assistant_audio([])


def test_the_label_only_guard_refuses_mixed_labels():
    with pytest.raises(InvalidRequestError):
        assert_no_assistant_audio(["learner", "assistant"])


def test_the_label_only_guard_accepts_one_learner_label():
    assert_no_assistant_audio(["synthetic-learner"])


# ---------------------------------------------------------------------------
# recognition status: missing vs no-speech vs measured
# ---------------------------------------------------------------------------


def test_a_missing_transcription_is_not_a_measured_zero():
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=0,
        recognized_text=None,
    )
    assert metrics.recognition_status == RECOGNITION_MISSING
    assert metrics.recognized_word_count is None
    assert metrics.rate_wpm is None
    assert metrics.active_rate_wpm is None
    assert metrics.has_measured_rate is False


def test_no_analyzable_speech_is_not_a_measured_zero():
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=0,
        recognized_text="",
    )
    assert metrics.recognition_status == RECOGNITION_NO_SPEECH
    assert metrics.recognized_word_count == 0
    # A rate of 0.0 would read as "measured: no words per minute".
    assert metrics.rate_wpm is None
    assert metrics.active_rate_wpm is None
    assert metrics.has_measured_rate is False


def test_a_real_transcript_is_measured():
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=5_000,
        recognized_text="one two three four",
    )
    assert metrics.recognition_status == RECOGNITION_MEASURED
    assert metrics.recognized_word_count == 4
    assert metrics.rate_wpm == 24.0
    assert metrics.active_rate_wpm == 48.0
    assert metrics.has_measured_rate is True


def test_a_transcript_with_no_word_tokens_is_a_genuine_measured_zero():
    """A transcript exists and holds no words: that *is* a measured zero."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=5_000,
        recognized_text="...",
    )
    assert metrics.recognition_status == RECOGNITION_MEASURED
    assert metrics.recognized_word_count == 0
    assert metrics.rate_wpm == 0.0
    assert metrics.active_rate_wpm == 0.0
    assert metrics.has_measured_rate is True


def test_the_overall_and_active_denominators_stay_separate():
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=5_000,
        recognized_text="one two three four",
    )
    assert metrics.rate_wpm != metrics.active_rate_wpm
    payload = metrics.to_dict()
    assert payload["denominators"]["rate_wpm"] != payload["denominators"]["active_rate_wpm"]
    assert "assistant audio" in payload["denominators"]["excluded"]


def test_the_span_states_whether_source_silence_is_included():
    included = compute(
        clip_span_ms=10_000,
        speech_active_ms=5_000,
        recognized_text="one two",
        leading_silence_ms=500,
        trailing_silence_ms=700,
    )
    payload = included.to_dict()
    assert payload["span_includes"]["source_leading_silence"] is True
    assert payload["span_includes"]["source_trailing_silence"] is True
    assert payload["span_includes"]["end_padding"] is False

    excluded = compute(
        clip_span_ms=10_000,
        speech_active_ms=5_000,
        recognized_text="one two",
        source_silence_included_in_span=False,
    )
    assert excluded.to_dict()["span_includes"]["source_leading_silence"] is False


def test_the_end_padding_remains_excluded_from_the_span():
    metrics = compute(
        clip_span_ms=9_000,
        speech_active_ms=5_000,
        recognized_text="one two",
        trailing_pad_ms=320,
    )
    # The span is the elapsed audio; the pad is reported separately.
    assert metrics.clip_span_ms == 9_000
    assert metrics.trailing_pad_ms == 320
    assert metrics.to_dict()["span_includes"]["end_padding"] is False


def test_the_method_notes_explain_the_recognition_status():
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=5_000,
        recognized_text=None,
    )
    notes = metrics.to_dict()["method_notes"]
    assert "recognition_status" in notes
    assert "no-analyzable-speech" in notes["recognition_status"]
    assert "missing-transcription" in notes["recognition_status"]


def test_negative_durations_are_refused():
    with pytest.raises(InvalidRequestError):
        compute(clip_span_ms=-1, speech_active_ms=0, recognized_text="hello")
    with pytest.raises(InvalidRequestError):
        compute(clip_span_ms=10, speech_active_ms=20, recognized_text="hello")
