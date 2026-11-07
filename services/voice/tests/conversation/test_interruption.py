"""Interruption: the learner speaks over the coach.

What the contract asks for:

* the coach's playback stops and the coach turn is **fenced**;
* the wait for the model stops;
* the round state is preserved, and an acknowledgement is not a new
  round;
* a late reply or late audio of a fenced turn is **never** sent;
* the interface never says the provider cancelled anything.
"""

from __future__ import annotations

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


def _wait_for_speaking(call) -> None:
    """Read events until the coach starts speaking."""
    for _ in range(40):
        event = call.next_event(timeout=5.0)
        if (
            event.get("type") == "status"
            and event.get("payload", {}).get("state") == "speaking"
        ):
            return
    raise AssertionError("the coach never started speaking")


def test_an_interrupt_stops_the_coach_audio(harness) -> None:
    """The synthesis is fenced when the learner interrupts."""
    tts = FakeTtsPort(chunks=[b"\x01\x02" * 64] * 20, slow=True)
    options = _options(tts=tts)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        _wait_for_speaking(call)
        call.send(control_event("interrupt", {"reason": "learner_speech"}))
        call.drain(limit=40, timeout=2.0)
        assert tts.sessions, "the coach did speak"
        assert tts.sessions[0].cancelled, "the playback must be fenced"
    finally:
        call.close()


def test_an_interrupt_stops_the_wait_for_the_model(harness) -> None:
    """The model reply of a fenced turn is never adopted."""
    reasoning = FakeReasoning(delay=1.0)
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        # The model is thinking; the learner interrupts.
        for _ in range(10):
            event = call.next_event(timeout=5.0)
            if (
                event.get("type") == "status"
                and event.get("payload", {}).get("state") == "thinking"
            ):
                break
        call.send(control_event("interrupt", {"reason": "learner_speech"}))
        events = call.drain(limit=40, timeout=2.0)
        assert not any(event["type"] == "coach_text" for event in events), (
            "a late reply of a fenced turn must never be sent"
        )
    finally:
        call.close()


def test_late_audio_of_a_fenced_turn_is_never_sent(harness) -> None:
    """A provider that keeps sending after the fence is dropped."""
    tts = FakeTtsPort(
        chunks=[b"\x01\x02" * 64] * 20, slow=True, ignore_cancel=True
    )
    options = _options(tts=tts)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        # Wait until the coach's audio has actually started.
        for _ in range(40):
            event = call.next_event(timeout=5.0)
            if event["type"] == "__binary__":
                break
        else:  # pragma: no cover - the coach always speaks here
            raise AssertionError("the coach sent no audio")
        call.send(control_event("interrupt", {"reason": "learner_speech"}))
        events = call.drain(limit=60, timeout=2.0)
        # No audio may arrive after the interrupt.
        assert not any(event["type"] == "__binary__" for event in events), (
            "late audio of a fenced turn was sent"
        )
        assert tts.sessions[0].cancelled
    finally:
        call.close()


def test_an_acknowledgement_is_not_a_new_round(harness) -> None:
    """A short acknowledgement does not complete a turn."""
    stt = FakeSttPort(texts=["one two three four five", "ok"])
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        call.events_until({"coach_text"}, limit=60)
        # The learner acknowledges while the coach is speaking.
        call.send(control_event("interrupt", {"reason": "learner_speech"}))
        call.speech(6)
        call.silence(45)
        events = call.drain(limit=60, timeout=2.0)
        assert not any(event["type"] == "round_feedback" for event in events)
    finally:
        call.close()


def test_the_interrupt_keeps_the_round_state(harness) -> None:
    """The completed turns of the round survive an interruption."""
    stt = FakeSttPort(texts=["one two three four five"])
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        for index in range(3):
            call.speech(8)
            call.silence(45)
            if index == 0:
                call.events_until({"coach_text"}, limit=60)
                call.send(control_event("interrupt", {"reason": "learner_speech"}))
                call.drain(limit=30, timeout=1.0)
        # The fourth turn completes the round.
        call.speech(8)
        call.silence(45)
        events = call.events_until({"round_feedback"}, limit=120)
        feedback = next(
            event for event in events if event["type"] == "round_feedback"
        )
        assert feedback["payload"]["evidence"], "the round kept its evidence"
    finally:
        call.close()


def test_the_barge_in_timing_is_measured_and_logged(harness, caplog) -> None:
    """The learner speaks over the coach: the fence is timed from the
    first interrupting frame."""
    import logging
    import re

    tts = FakeTtsPort(chunks=[b"\x01\x02" * 64] * 40, slow=True)
    options = _options(tts=tts)
    call = harness(options)
    with caplog.at_level(logging.INFO, logger="gnani_coach.conversation"):
        try:
            call.start()
            call.speech(8)
            call.silence(45)
            # The coach starts speaking; the learner then talks over it.
            _wait_for_speaking(call)
            call.speech(20)
            call.drain(limit=80, timeout=3.0)
        finally:
            call.close()
    raw = "\n".join(record.getMessage() for record in caplog.records)
    fence = re.search(r"fence_latency_ms=(-?\d+)", raw)
    assert fence is not None, "the barge-in was not timed"
    latency_ms = int(fence.group(1))
    assert latency_ms >= 0, latency_ms
    onset = re.search(r"voice_onset_gap_ms=(-?\d+)", raw)
    assert onset is not None, "the voice onset was not timed"
    onset_ms = int(onset.group(1))
    # The hang-over before the fence is 240 ms of learner audio, so the
    # coach is fenced only after the learner has really started talking.
    assert onset_ms >= 240, onset_ms
    assert onset_ms < 5_000, onset_ms


def test_the_interrupt_is_never_described_as_a_cancellation(harness) -> None:
    """Nothing the client is told claims the provider was cancelled."""
    tts = FakeTtsPort(chunks=[b"\x01\x02" * 64] * 20, slow=True)
    options = _options(tts=tts)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        _wait_for_speaking(call)
        call.send(control_event("interrupt", {"reason": "learner_speech"}))
        events = call.drain(limit=60, timeout=2.0)
        texts = [
            event["payload"].get("text", "")
            for event in events
            if event["type"] in ("coach_text", "status")
        ]
        for text in texts:
            lowered = str(text).lower()
            assert "cancel" not in lowered
            assert "billing" not in lowered
            assert "refund" not in lowered
    finally:
        call.close()


def test_the_interrupt_timing_is_measured_and_logged(harness, caplog) -> None:
    """The gap between the last coach audio byte and the interrupt is a
    number, and it is logged as a number."""
    import logging
    import re

    tts = FakeTtsPort(chunks=[b"\x01\x02" * 64] * 20, slow=True)
    options = _options(tts=tts)
    call = harness(options)
    with caplog.at_level(logging.INFO, logger="gnani_coach.conversation"):
        try:
            call.start()
            call.speech(8)
            call.silence(45)
            # Wait until the coach's audio has actually started, so the
            # measured gap is a real one.
            for _ in range(40):
                event = call.next_event(timeout=5.0)
                if event["type"] == "__binary__":
                    break
            call.send(control_event("interrupt", {"reason": "learner_speech"}))
            call.drain(limit=60, timeout=2.0)
        finally:
            call.close()
    raw = "\n".join(record.getMessage() for record in caplog.records)
    match = re.search(r"last_audio_gap_ms=(-?\d+)", raw)
    assert match is not None, "the interrupt timing was not logged"
    gap_ms = int(match.group(1))
    assert gap_ms >= 0, "the measured gap is a duration"
    fence = re.search(r"fence_latency_ms=(-?\d+)", raw)
    assert fence is not None, "the fence latency was not logged"
    assert int(fence.group(1)) >= 0, "the measured fence latency is a duration"
    # The log carries the gap, and nothing about the content.
    assert "last_audio_gap_ms=" in raw
    assert "session=" in raw
