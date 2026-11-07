"""The life of a call: concurrency, bursts, and provider failures.

What is under test:

* two concurrent calls do not see each other;
* a burst of frames stays bounded in memory;
* a recogniser that dies mid-call does not kill the call;
* a model that times out does not kill the call.
"""

from __future__ import annotations

import tracemalloc

from gnani_coach.conversation.config import MAX_TURN_AUDIO_BYTES
from gnani_coach.conversation.recognition import MAX_PENDING_AUDIO_BYTES
from phase05_support import (
    FakeAnalysis,
    FakeIdentity,
    FakeReasoning,
    FakeSttPort,
    FakeTtsPort,
    build_options,
    control_event,
)


def _options(
    *,
    identity: FakeIdentity | None = None,
    analysis: FakeAnalysis | None = None,
    stt: FakeSttPort | None = None,
    tts: FakeTtsPort | None = None,
    reasoning: FakeReasoning | None = None,
    **kwargs,
):
    return build_options(
        identity=identity or FakeIdentity(),
        analysis=analysis or FakeAnalysis(),
        stt=stt or FakeSttPort(),
        tts=tts or FakeTtsPort(),
        reasoning=reasoning or FakeReasoning(),
        **kwargs,
    )


def test_two_concurrent_calls_are_isolated(harness) -> None:
    """One call never sees the other one's events."""
    first_reasoning = FakeReasoning(replies=["the first call's answer"])
    second_reasoning = FakeReasoning(replies=["the second call's answer"])
    first = harness(_options(reasoning=first_reasoning))
    second = harness(_options(reasoning=second_reasoning))
    try:
        first.start()
        second.start()
        first.speech(8)
        first.silence(45)
        second.speech(8)
        second.silence(45)

        first_events = first.events_until({"coach_text"}, limit=60)
        second_events = second.events_until({"coach_text"}, limit=60)

        first_texts = [
            event["payload"]["text"]
            for event in first_events
            if event["type"] == "coach_text"
        ]
        second_texts = [
            event["payload"]["text"]
            for event in second_events
            if event["type"] == "coach_text"
        ]
        assert first_texts == ["the first call's answer"]
        assert second_texts == ["the second call's answer"]
        first_session = first_events[0]["sessionId"]
        second_session = second_events[0]["sessionId"]
        assert first_session != second_session
    finally:
        first.close()
        second.close()


def test_a_burst_of_frames_stays_bounded(harness) -> None:
    """Ten times the real-time frame rate does not grow the memory."""
    stt = FakeSttPort()
    analysis = FakeAnalysis()
    options = _options(stt=stt, analysis=analysis)
    call = harness(options)
    tracemalloc.start()
    try:
        baseline = tracemalloc.get_traced_memory()[0]
        call.start()
        # 2,000 frames is about 64 seconds of audio at the real-time
        # rate: ten times the burst the browser may produce.
        call.frames(2000, loud=True)
        call.silence(45)
        call.events_until({"coach_text"}, limit=200, timeout=10.0)
        peak = tracemalloc.get_traced_memory()[1]
        growth = max(0, peak - baseline)
        assert growth < 32 * 1024 * 1024, "the burst grew the memory too much"
        # The buffers themselves are bounded by their own ceilings.
        for request in analysis.requests:
            assert len(request.audio) <= MAX_TURN_AUDIO_BYTES
    finally:
        tracemalloc.stop()
        call.close()


def test_the_submitted_audio_is_bounded(harness) -> None:
    """The recogniser is never handed an unbounded clip."""
    stt = FakeSttPort()
    options = _options(stt=stt)
    call = harness(options)
    try:
        call.start()
        call.frames(2000, loud=True)
        call.silence(45)
        call.events_until({"coach_text"}, limit=200, timeout=10.0)
        assert stt.submissions >= 1
        assert stt.max_clip_bytes <= MAX_PENDING_AUDIO_BYTES
    finally:
        call.close()


def test_a_recogniser_that_dies_does_not_kill_the_call(harness) -> None:
    """A mid-call recogniser failure is reported and the call continues."""
    stt = FakeSttPort()
    stt.fail = True
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        events = call.events_until({"error"}, limit=60)
        failure = next(event for event in events if event["type"] == "error")
        assert failure["payload"]["category"] in (
            "provider_unavailable",
            "internal",
        )
        # The call is still open: the learner may end it.
        call.send(control_event("end", {"reason": "learner_ended"}))
        call.wait_for_state("ended", limit=30, timeout=5.0)
    finally:
        call.close()


def test_a_model_timeout_does_not_kill_the_call(harness) -> None:
    """A model that times out costs the reply, not the call."""
    from gnani_coach.providers.errors import UpstreamTimeoutError

    reasoning = FakeReasoning(error=UpstreamTimeoutError("the model did not answer"))
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        events = call.events_until({"error"}, limit=60)
        failure = next(event for event in events if event["type"] == "error")
        assert failure["payload"]["category"] == "timeout"
        assert failure["payload"]["retryable"] is True
        call.send(control_event("end", {"reason": "learner_ended"}))
        call.wait_for_state("ended", limit=30, timeout=5.0)
    finally:
        call.close()


def test_a_provider_that_throttles_is_reported_as_retryable(harness) -> None:
    """A throttled provider is a retryable failure."""
    from gnani_coach.providers.errors import RateLimitError

    reasoning = FakeReasoning(error=RateLimitError("the provider is busy"))
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        events = call.events_until({"error"}, limit=60)
        failure = next(event for event in events if event["type"] == "error")
        assert failure["payload"]["category"] == "rate_limited"
        assert failure["payload"]["retryable"] is True
    finally:
        call.close()
