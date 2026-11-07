"""The turn controller: segments, the hold, and the word count.

A turn is a **conversational turn**, not a recognised segment. These
tests cover:

* several segments are joined into one turn;
* a turn waits for the silence hold before it ends;
* a turn with too few words stays open, and the learner may keep talking;
* the learner may ask for more time, and the hold is extended.
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


def _flush(call) -> None:
    """Let the server process every queued frame, then end the call."""
    call.send(control_event("end", {"reason": "learner_ended"}))
    call.wait_for_state("ended", limit=30, timeout=5.0)


def test_several_segments_are_joined_into_one_turn(harness) -> None:
    """Two recognised segments make one conversational turn."""
    stt = FakeSttPort(texts=["first part of the answer", "second part of it"])
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(5)
        call.silence(5)
        call.speech(5)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=60)
        transcripts = [
            event for event in events if event["type"] == "transcript_final"
        ]
        assert len(transcripts) == 2, "both segments must be reported"
        coach = [event for event in events if event["type"] == "coach_text"]
        assert len(coach) == 1, "one turn means one coach reply"
    finally:
        call.close()


def test_a_turn_waits_for_the_silence_hold(harness) -> None:
    """The turn does not end before the hold has elapsed."""
    stt = FakeSttPort()
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        # 20 frames of silence is 640 ms: shorter than the 1.2 s hold.
        call.silence(20)
        _flush(call)
        assert stt.submissions == 0, "the recogniser must not be asked yet"
        assert reasoning.requests == [], "the coach must not answer yet"
    finally:
        call.close()


def test_a_turn_completes_once_the_hold_elapses(harness) -> None:
    """The turn ends when the silence is long enough."""
    stt = FakeSttPort()
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=60)
        assert stt.submissions == 1
        assert len(reasoning.requests) == 1
        assert any(event["type"] == "coach_text" for event in events)
    finally:
        call.close()


def test_a_turn_with_too_few_words_stays_open(harness) -> None:
    """A turn that carries too few words is not completed."""
    stt = FakeSttPort(texts=["yes"])
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        _flush(call)
        assert stt.submissions >= 1, "the recogniser was asked"
        assert reasoning.requests == [], "one word is not a turn"
    finally:
        call.close()


def test_the_learner_may_keep_talking_after_a_short_answer(harness) -> None:
    """More speech after a short answer completes the turn."""
    stt = FakeSttPort(texts=["yes", "and then I explained the whole plan"])
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        call.speech(8)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=80)
        assert any(event["type"] == "coach_text" for event in events)
    finally:
        call.close()


def test_give_me_a_moment_extends_the_hold(harness) -> None:
    """The learner may ask for more time, and the hold is extended.

    The frozen client vocabulary has no "give me a moment" event, so the
    control is carried by the ``mute`` event: a muted learner is not
    ending a turn, and the hold grows while the learner is muted.
    """
    stt = FakeSttPort()
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.send(control_event("mute", {"muted": True}))
        call.silence(60)
        _flush(call)
        assert stt.submissions == 0, "a muted learner is not ending a turn"
        assert reasoning.requests == []
    finally:
        call.close()


def test_the_hold_is_configurable(harness) -> None:
    """A shorter hold ends the turn sooner."""
    stt = FakeSttPort()
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning, hold_ms=200)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(10)  # 320 ms of silence
        _flush(call)
        assert stt.submissions == 1, "the shorter hold must have expired"
    finally:
        call.close()


def test_the_minimum_word_count_is_configurable(harness) -> None:
    """A single word can be enough when the product says so."""
    stt = FakeSttPort(texts=["yes"])
    reasoning = FakeReasoning()
    options = _options(stt=stt, reasoning=reasoning, min_words=1)
    call = harness(options)
    try:
        call.start()
        call.speech(8)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=60)
        assert any(event["type"] == "coach_text" for event in events)
    finally:
        call.close()
