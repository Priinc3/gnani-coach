"""The coaching round: the break, the choices and the retry.

Four completed learner turns (the settings' ``coachingRoundTurns``)
trigger one coaching break, announced at a natural boundary. The
feedback is built from the measured facts plus **one** model call, and it
degrades to a facts-only message when the model's answer fails
validation.
"""

from __future__ import annotations

import json

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


def _one_turn(call) -> None:
    """One completed learner turn."""
    call.speech(8)
    call.silence(45)


def test_four_turns_trigger_one_coaching_break(harness) -> None:
    """The break arrives after the round's turns, not before."""
    reasoning = FakeReasoning(
        replies=[
            "first reply",
            "second reply",
            "third reply",
            "fourth reply",
            '{"strengths": ["You kept the story moving."], '
            '"improvements": ["Try one concrete example."], '
            '"languageNotes": []}',
        ]
    )
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        for _ in range(4):
            _one_turn(call)
        events = call.events_until({"round_feedback"}, limit=120)
        feedback = next(
            event for event in events if event["type"] == "round_feedback"
        )
        payload = feedback["payload"]
        assert len(payload["strengths"]) <= 1
        assert len(payload["improvements"]) <= 2
        assert len(payload["languageNotes"]) <= 1
        assert payload["strengths"] == ["You kept the story moving."]
        assert payload["improvements"] == ["Try one concrete example."]
        assert payload["evidence"], "the feedback carries the measured evidence"
        metric_keys = {entry["metricKey"] for entry in payload["evidence"]}
        assert "speech.rate_wpm" in metric_keys
        assert "filler.count" in metric_keys
    finally:
        call.close()


def test_the_feedback_evidence_carries_the_real_metrics(harness) -> None:
    """The evidence is the measured facts, not a summary of them."""
    reasoning = FakeReasoning(
        replies=[
            "one",
            "two",
            "three",
            "four",
            '{"strengths": [], "improvements": [], "languageNotes": []}',
        ]
    )
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        for _ in range(4):
            _one_turn(call)
        events = call.events_until({"round_feedback"}, limit=120)
        feedback = next(
            event for event in events if event["type"] == "round_feedback"
        )
        evidence = {entry["metricKey"]: entry for entry in feedback["payload"]["evidence"]}
        assert evidence["speech.rate_wpm"]["status"] == "available"
        assert evidence["speech.rate_wpm"]["value"] == 120.0
        assert evidence["speech.rate_wpm"]["unit"] == "words_per_minute"
        # The filler capability is unvalidated: never a number.
        assert evidence["filler.count"]["status"] == "insufficient_evidence"
        assert evidence["filler.count"]["value"] is None
    finally:
        call.close()


def test_an_unusable_model_answer_degrades_to_the_facts(harness) -> None:
    """A model answer that fails validation is never spoken as feedback."""
    reasoning = FakeReasoning(
        replies=[
            "one",
            "two",
            "three",
            "four",
            '{"strengths": ["You spoke at 300 words per minute."], '
            '"improvements": [], "languageNotes": []}',
        ]
    )
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        for _ in range(4):
            _one_turn(call)
        events = call.events_until({"round_feedback"}, limit=120)
        feedback = next(
            event for event in events if event["type"] == "round_feedback"
        )
        assert feedback["payload"]["strengths"] == []
        spoken = [
            event["payload"]["text"]
            for event in events
            if event["type"] == "coach_text"
        ]
        spoken += [
            event["payload"]["text"]
            for event in call.drain(limit=20, timeout=1.0)
            if event["type"] == "coach_text"
        ]
        assert any("words per minute" in text for text in spoken), (
            "the facts-only message states what was measured"
        )
        assert not any("300" in text for text in spoken)
    finally:
        call.close()


def test_an_unparsable_model_answer_degrades_to_the_facts(harness) -> None:
    """A model answer that is not the frozen shape is rejected."""
    reasoning = FakeReasoning(
        replies=["one", "two", "three", "four", "Here is some prose instead."]
    )
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        for _ in range(4):
            _one_turn(call)
        events = call.events_until({"round_feedback"}, limit=120)
        feedback = next(
            event for event in events if event["type"] == "round_feedback"
        )
        assert feedback["payload"]["strengths"] == []
        assert feedback["payload"]["improvements"] == []
        assert feedback["payload"]["evidence"]
    finally:
        call.close()


def test_the_round_length_follows_the_settings(harness) -> None:
    """Two turns are enough when the settings say so."""
    reasoning = FakeReasoning(
        replies=["one", "two", '{"strengths": [], "improvements": [], "languageNotes": []}']
    )
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        # The round size is part of the start event.
        call.socket.send_json(_start_with_two_turns())
        _one_turn(call)
        _one_turn(call)
        events = call.events_until({"round_feedback"}, limit=120)
        assert any(event["type"] == "round_feedback" for event in events)
    finally:
        call.close()


def _start_with_two_turns() -> dict:
    from phase05_support import start_event

    return start_event(coaching_round_turns=2)


def test_keep_talking_does_not_produce_feedback(harness) -> None:
    """"Keep talking" continues the call without a break."""
    reasoning = FakeReasoning()
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.send(control_event("coaching_choice", {"choice": "keep_talking"}))
        _one_turn(call)
        events = call.drain(limit=40, timeout=1.0)
        assert not any(event["type"] == "round_feedback" for event in events)
    finally:
        call.close()


def test_coach_now_produces_the_feedback(harness) -> None:
    """"Coach me now" produces the break immediately."""
    reasoning = FakeReasoning(
        replies=["one", '{"strengths": [], "improvements": [], "languageNotes": []}']
    )
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        _one_turn(call)
        call.send(control_event("coaching_choice", {"choice": "coach_now"}))
        events = call.events_until({"round_feedback"}, limit=60)
        assert any(event["type"] == "round_feedback" for event in events)
    finally:
        call.close()


def test_skip_feedback_ends_the_round(harness) -> None:
    """"Skip feedback" ends the round without a break."""
    reasoning = FakeReasoning()
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.send(control_event("coaching_choice", {"choice": "skip_feedback"}))
        _one_turn(call)
        events = call.drain(limit=40, timeout=1.0)
        assert not any(event["type"] == "round_feedback" for event in events)
    finally:
        call.close()


def test_a_retry_repeats_the_answer(harness) -> None:
    """A retry reuses the same turn and the same metric definitions."""
    reasoning = FakeReasoning(replies=["the first answer", "a different answer"])
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        _one_turn(call)
        events = call.events_until({"coach_text"}, limit=60)
        coach = next(event for event in events if event["type"] == "coach_text")
        turn_id = coach["turnId"]
        call.send(control_event("retry", {"turnId": turn_id}))
        retried = call.events_until({"coach_text"}, limit=60)
        texts = [
            event["payload"]["text"]
            for event in retried
            if event["type"] == "coach_text"
        ]
        assert texts, "the retry must be answered"
        assert len(reasoning.requests) == 2
        # The retry uses the same turn, so the same transcript.
        assert (
            reasoning.requests[0].recognized_text
            == reasoning.requests[1].recognized_text
        )
    finally:
        call.close()


def test_a_retry_with_an_unknown_turn_is_ignored(harness) -> None:
    """A retry for a turn the runtime does not know is ignored."""
    reasoning = FakeReasoning()
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        call.send(control_event("retry", {"turnId": "trn_unknownturn"}))
        events = call.drain(limit=20, timeout=1.0)
        assert len(reasoning.requests) == 0
        assert not any(event["type"] == "error" for event in events)
    finally:
        call.close()


def test_the_feedback_call_is_one_call(harness) -> None:
    """The break costs exactly one model call."""
    reasoning = FakeReasoning(
        replies=["one", "two", "three", "four", '{"strengths": [], "improvements": [], "languageNotes": []}']
    )
    options = _options(reasoning=reasoning)
    call = harness(options)
    try:
        call.start()
        for _ in range(4):
            _one_turn(call)
        call.events_until({"round_feedback"}, limit=120)
        assert len(reasoning.requests) == 5, "four replies and one feedback call"
        last = reasoning.requests[-1]
        assert "measured facts" in last.instruction
        assert json.dumps(last.recognized_text)  # the round's transcript is quoted
    finally:
        call.close()
