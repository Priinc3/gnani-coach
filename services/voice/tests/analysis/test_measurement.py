"""The measurement semantics: the four denominators, the recognition
status and the trusted-source rule.

These are the rules of the Phase 02 probe, re-homed into the service
tree. Nothing here imports from ``tools/``.
"""

from __future__ import annotations

import pytest

from gnani_coach.analysis.measurement import (
    LIVE_LEARNER,
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
    count_words,
)
from gnani_coach.providers.errors import InvalidRequestError


def test_the_word_count_ignores_punctuation() -> None:
    """Punctuation is not a word."""
    assert count_words("hello there") == 2
    assert count_words("hello, there!") == 2
    assert count_words("... --") == 0
    assert count_words("") == 0
    assert count_words("don't stop") == 2


def test_a_missing_transcription_is_not_a_measured_zero() -> None:
    """No transcript at all: the rates are absent, never 0."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=6_000,
        recognized_text=None,
    )
    assert metrics.recognition_status == RECOGNITION_MISSING
    assert metrics.recognized_word_count is None
    assert metrics.rate_wpm is None
    assert metrics.active_rate_wpm is None
    assert not metrics.has_measured_rate


def test_an_unanalyzable_transcript_is_not_a_measured_zero() -> None:
    """The recogniser ran and returned nothing: still not a 0 rate."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=6_000,
        recognized_text="",
    )
    assert metrics.recognition_status == RECOGNITION_NO_SPEECH
    assert metrics.recognized_word_count == 0
    assert metrics.rate_wpm is None
    assert metrics.active_rate_wpm is None
    assert not metrics.has_measured_rate


def test_a_transcript_without_words_is_a_measured_zero() -> None:
    """A transcript exists, so a rate of zero is a real measurement."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=6_000,
        recognized_text="... --",
    )
    assert metrics.recognition_status == RECOGNITION_MEASURED
    assert metrics.recognized_word_count == 0
    assert metrics.rate_wpm == 0.0
    assert metrics.active_rate_wpm == 0.0
    assert metrics.has_measured_rate


def test_the_two_rates_use_two_denominators() -> None:
    """The overall rate divides by the span, the active rate by the
    speech-active time. They are never the same number by accident."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=4_000,
        recognized_text="one two three four five six seven eight nine ten",
    )
    assert metrics.recognized_word_count == 10
    assert metrics.rate_wpm == 60.0  # 10 words over 10 s
    assert metrics.active_rate_wpm == 150.0  # 10 words over 4 s
    assert metrics.rate_wpm != metrics.active_rate_wpm


def test_the_denominators_are_named_in_the_report() -> None:
    """The report says which durations were used, and what was not."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=4_000,
        recognized_text="one two three",
    )
    document = metrics.to_dict()
    denominators = document["denominators"]
    assert denominators["rate_wpm"] == "clip_span_ms (elapsed learner audio)"
    assert denominators["active_rate_wpm"] == "speech_active_ms (VAD speech-active)"
    excluded = " ".join(denominators["excluded"])
    assert "total connection time" in excluded
    assert "total session time" in excluded
    assert "network round trips" in excluded
    assert "assistant audio" in excluded


def test_the_span_includes_the_silence_and_excludes_the_padding() -> None:
    """The span is the elapsed learner audio, not the padded clip."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=4_000,
        recognized_text="one two three",
        trailing_pad_ms=800,
    )
    span = metrics.to_dict()["span_includes"]
    assert span["source_leading_silence"] is True
    assert span["source_trailing_silence"] is True
    assert span["end_padding"] is False


def test_the_source_label_is_a_declaration_not_a_proof() -> None:
    """The report says the label proves nothing."""
    metrics = compute(
        clip_span_ms=10_000,
        speech_active_ms=4_000,
        recognized_text="one two three",
        source_labels=["learner"],
    )
    caveat = metrics.to_dict()["source_caveat"]
    assert "declared label" in caveat
    assert "NOT established" in caveat


def test_the_trusted_source_rule_accepts_a_learner_source() -> None:
    """A live learner clip and a synthetic learner clip are both fine."""
    assert_trusted_learner_source([LIVE_LEARNER])
    assert_trusted_learner_source([SYNTHETIC_LEARNER])


def test_the_trusted_source_rule_refuses_an_empty_source() -> None:
    """An unlabelled clip cannot be asserted to be learner only."""
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source([])
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source(None)


def test_the_trusted_source_rule_refuses_assistant_audio() -> None:
    """The coach's own audio is never measured as learner audio."""
    assistant = ClipSource(label="coach", role=ROLE_ASSISTANT, trusted=True)
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source([assistant])


def test_the_trusted_source_rule_refuses_a_mixed_clip() -> None:
    """Learner and assistant audio in one clip is refused."""
    assistant = ClipSource(label="coach", role=ROLE_ASSISTANT, trusted=True)
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source([LIVE_LEARNER, assistant])


def test_the_trusted_source_rule_refuses_an_unknown_role() -> None:
    """A source whose role could not be classified is refused."""
    unknown = ClipSource(label="mystery", role=ROLE_UNKNOWN, trusted=True)
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source([unknown])


def test_the_trusted_source_rule_refuses_an_untrusted_source() -> None:
    """A learner role that is not explicitly trusted is refused."""
    untrusted = ClipSource(label="learner", role=ROLE_LEARNER, trusted=False)
    with pytest.raises(InvalidRequestError):
        assert_trusted_learner_source([untrusted])


def test_the_label_only_rule_refuses_an_unlabelled_clip() -> None:
    """The lighter rule still refuses an empty source list."""
    with pytest.raises(InvalidRequestError):
        assert_no_assistant_audio([])
    with pytest.raises(InvalidRequestError):
        assert_no_assistant_audio(["learner", "coach"])
    assert_no_assistant_audio(["learner"])


def test_a_speech_active_time_beyond_the_span_is_refused() -> None:
    """The two durations must describe the same clip."""
    with pytest.raises(InvalidRequestError):
        compute(
            clip_span_ms=1_000,
            speech_active_ms=5_000,
            recognized_text="one two three",
        )
