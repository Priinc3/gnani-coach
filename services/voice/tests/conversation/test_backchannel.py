"""Phase 19: the immediate acknowledgement, speculation and streaming.

These tests use the real runtime and router over fakes. They assert the
rules, not the taste of a filler: a backchannel has its own turn id, it can
be switched off, a speculative reply is adopted once, and the first
sentence reaches TTS before the stream has finished.
"""

from __future__ import annotations

from phase05_support import (
    FakeAnalysis,
    FakeIdentity,
    FakeReasoning,
    FakeRecognitionStream,
    FakeSttPort,
    FakeTtsPort,
    build_options,
    control_event,
)
from gnani_coach.ports.speech_to_text import TranscriptSegment


def _segment(text: str) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id="seg-1",
        segment_index=0,
        text=text,
        latency_ms=10,
        server_timestamp=None,
        learner_clock_samples=0,
    )


def _options(*, stt=None, tts=None, reasoning=None, **kwargs):
    return build_options(
        identity=FakeIdentity(),
        analysis=FakeAnalysis(),
        stt=stt or FakeSttPort(),
        tts=tts or FakeTtsPort(),
        reasoning=reasoning or FakeReasoning(),
        **kwargs,
    )


def _descriptors(events):
    return [
        event
        for event in events
        if event.get("type") == "audio.frame.descriptor"
    ]


def _read_until_reply_audio(call, *, count: int = 1, limit: int = 160):
    """Read events until ``count`` real-reply descriptors have arrived."""
    events = []
    seen = 0
    for _ in range(limit):
        event = call.next_event(timeout=5.0)
        events.append(event)
        if (
            event.get("type") == "audio.frame.descriptor"
            and event.get("payload", {}).get("kind", "reply") == "reply"
        ):
            seen += 1
            if seen >= count:
                return events
    raise AssertionError("the real reply's descriptor never arrived")


def test_backchannel_off_switch_sends_no_reaction(harness) -> None:
    """With the switch off, a turn has no backchannel descriptor."""
    options = _options(backchannel_enabled=False)
    call = harness(options)
    try:
        call.start()
        call.speech(5)
        call.silence(45)
        events = _read_until_reply_audio(call)
        descriptors = _descriptors(events)
        assert descriptors, "the real reply still has an audio descriptor"
        assert all(
            descriptor["payload"].get("kind") != "backchannel"
            for descriptor in descriptors
        )
    finally:
        call.close()


def test_filler_has_its_own_turn_and_precedes_the_reply(harness) -> None:
    """The acknowledgement is a separate turn, never the real reply's id."""
    options = _options()
    call = harness(options)
    try:
        call.start()
        call.speech(5)
        call.silence(45)
        events = _read_until_reply_audio(call)
        backchannels = [
            descriptor
            for descriptor in _descriptors(events)
            if descriptor["payload"].get("kind") == "backchannel"
        ]
        assert len(backchannels) == 1
        coach = next(event for event in events if event.get("type") == "coach_text")
        assert backchannels[0]["turnId"] != coach["turnId"]
    finally:
        call.close()


def test_speculative_reply_is_adopted_once(harness) -> None:
    """A closed segment lets the model start early; it is called once."""
    stream = FakeRecognitionStream(batches=[[_segment("one two three")]])
    stream.closed = True
    reasoning = FakeReasoning(replies=["Speculative answer."])
    options = _options(reasoning=reasoning, stream_factory=lambda providers: stream)
    call = harness(options)
    try:
        call.start()
        call.speech(5)
        call.silence(30)
        events = call.events_until({"coach_text"}, limit=120)
        assert len(reasoning.requests) == 1, "the reply was not re-requested"
        coach = next(event for event in events if event.get("type") == "coach_text")
        assert coach["payload"]["text"] == "Speculative answer."
    finally:
        call.close()


def test_speculation_is_discarded_when_the_learner_resumes(harness) -> None:
    """New speech cancels the speculative call and its output is never used."""
    stream = FakeRecognitionStream(batches=[[_segment("one two three")]])
    stream.closed = True
    reasoning = FakeReasoning(replies=["Stale answer.", "Fresh answer."], delay=0.05)
    options = _options(reasoning=reasoning, stream_factory=lambda providers: stream)
    call = harness(options)
    try:
        call.start()
        call.speech(5)
        call.silence(16)  # 512 ms: speculation has started, hold not expired
        # Let the speculative call finish, so this exercises the stored
        # reply being discarded, not only an in-flight cancellation.
        import time

        time.sleep(0.1)
        call.speech(5)
        call.silence(45)
        events = call.events_until({"coach_text"}, limit=160)
        coach = next(event for event in events if event.get("type") == "coach_text")
        assert coach["payload"]["text"] == "Fresh answer."
        assert len(reasoning.requests) == 2
    finally:
        call.close()


def test_first_sentence_goes_to_tts_before_the_stream_ends(harness) -> None:
    """The first sentence is synthesised on its own, then the rest."""
    reasoning = FakeReasoning(
        stream_deltas=["Hello there. ", "This is the rest."]
    )
    tts = FakeTtsPort()
    options = _options(reasoning=reasoning, tts=tts)
    call = harness(options)
    try:
        call.start()
        call.speech(5)
        call.silence(45)
        events = _read_until_reply_audio(call, count=2)
        spoken = [request.text for request in tts.requests]
        assert "Hello there." in spoken, "the first sentence was synthesised alone"
        assert "This is the rest." in spoken, "the remainder followed it"
        coach = next(event for event in events if event.get("type") == "coach_text")
        assert coach["payload"]["text"] == "Hello there. This is the rest."
    finally:
        call.close()
