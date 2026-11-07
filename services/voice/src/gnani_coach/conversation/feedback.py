"""The round feedback: measured facts, one model call, and a safe fallback.

The coaching break is built from two things:

* the **measured facts** of the round — numbers and controlled
  identifiers only, never content;
* **one** call to the reasoning model, whose answer is validated before
  it is used.

If the model's answer fails validation, the runtime **degrades** to a
facts-only message: it says what was measured and nothing else. A
feedback message that cannot be checked is never spoken.

The rules the validator enforces:

* at most one strength, at most two improvements, at most one language
  note, and each line within the frozen length bound;
* every number in the model's text must be one of the measured numbers
  (or the round's turn count). A number that was not measured is a
  reason to reject the whole answer;
* the shape is checked against the frozen ``round_feedback`` payload.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from gnani_coach.conversation.config import MAX_FEEDBACK_CHARS
from gnani_coach.ports.analysis import AnalysisObservation

#: The metric keys the feedback may carry evidence for.
EVIDENCE_METRIC_KEYS = (
    "pause.longest_ms",
    "pause.count",
    "filler.count",
    "speech.rate_wpm",
    "speech.active_rate_wpm",
    "turn.duration_ms",
)

#: The digit runs of a text.
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

#: The frozen maximum number of evidence entries.
MAX_EVIDENCE_ENTRIES = 8


@dataclass
class FeedbackDraft:
    """A parsed, not-yet-validated model answer."""

    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    language_notes: list[str] = field(default_factory=list)


@dataclass
class RoundFacts:
    """The measured facts of one round.

    Numbers and controlled identifiers only: no transcript, no quoted
    mistake, no model text.
    """

    turn_count: int
    observations: tuple[AnalysisObservation, ...] = ()

    def value_for(self, metric_key: str) -> float | None:
        """The measured value of a metric, or ``None``."""
        for observation in self.observations:
            if observation.metric_key == metric_key and observation.status == "available":
                return observation.value
        return None

    def allowed_numbers(self) -> set[str]:
        """Every number the model is allowed to mention.

        The measured values and the round's turn count. A number that is
        not in this set was not measured, so a line that contains one is
        rejected.
        """
        allowed: set[str] = {str(self.turn_count)}
        for observation in self.observations:
            if observation.status != "available" or observation.value is None:
                continue
            allowed.add(_number_spelling(observation.value))
            allowed.add(str(int(observation.value)))
        return allowed

    def evidence(self) -> list[dict[str, Any]]:
        """The evidence array of the round-feedback payload."""
        entries: list[dict[str, Any]] = []
        for metric_key in EVIDENCE_METRIC_KEYS:
            observation = next(
                (
                    item
                    for item in self.observations
                    if item.metric_key == metric_key
                ),
                None,
            )
            if observation is None:
                continue
            if observation.status == "available":
                value: float | None = observation.value
                unit: str | None = observation.unit
            else:
                value = None
                unit = None
            entries.append(
                {
                    "metricKey": metric_key,
                    "status": observation.status,
                    "value": value,
                    "unit": unit,
                }
            )
            if len(entries) >= MAX_EVIDENCE_ENTRIES:
                break
        return entries

    def facts_document(self) -> str:
        """The facts as a JSON document, for the prompt.

        It carries the numbers, the units, the statuses and the reason
        codes — and no content at all.
        """
        document = {
            "turns": self.turn_count,
            "measurements": [
                {
                    "metricKey": entry["metricKey"],
                    "status": entry["status"],
                    "value": entry["value"],
                    "unit": entry["unit"],
                }
                for entry in self.evidence()
            ],
        }
        return json.dumps(document, ensure_ascii=False, indent=2)


def parse_feedback(text: str) -> FeedbackDraft | None:
    """Parse the model's answer as the frozen feedback shape.

    ``None`` when the answer is not a JSON object with the three frozen
    keys. A fenced code block around the JSON is accepted, because a
    model that wraps its answer in one has still answered.
    """
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        document = json.loads(candidate[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    if set(document) - {"strengths", "improvements", "languageNotes"}:
        return None
    try:
        return FeedbackDraft(
            strengths=_string_list(document.get("strengths", [])),
            improvements=_string_list(document.get("improvements", [])),
            language_notes=_string_list(document.get("languageNotes", [])),
        )
    except (TypeError, ValueError):
        return None


def validate_feedback(draft: FeedbackDraft, facts: RoundFacts) -> str | None:
    """Check a parsed answer against the frozen shape and the facts.

    Returns ``None`` when the answer may be used, and a short reason when
    it may not.
    """
    if len(draft.strengths) > 1:
        return "more than one strength"
    if len(draft.improvements) > 2:
        return "more than two improvements"
    if len(draft.language_notes) > 1:
        return "more than one language note"
    for group in (draft.strengths, draft.improvements, draft.language_notes):
        for line in group:
            if not line.strip():
                return "an empty line"
            if len(line) > MAX_FEEDBACK_CHARS:
                return "a line is longer than the frozen bound"
    allowed = facts.allowed_numbers()
    for group in (draft.strengths, draft.improvements, draft.language_notes):
        for line in group:
            for number in _NUMBER_RE.findall(line):
                if number not in allowed and number.replace(",", "") not in allowed:
                    return "a number that was not measured"
    return None


def facts_only_message(facts: RoundFacts, *, coaching_language: str) -> str:
    """The message spoken when the model's answer was rejected.

    It says what was measured, in plain words, and nothing else. When
    there was too little speech to measure, it says so.
    """
    rate = facts.value_for("speech.rate_wpm")
    active_rate = facts.value_for("speech.active_rate_wpm")
    longest_pause = facts.value_for("pause.longest_ms")
    pause_count = facts.value_for("pause.count")
    duration = facts.value_for("turn.duration_ms")

    if rate is None and duration is None:
        return (
            "There was not enough speech in this round to measure, so there "
            "is no feedback to give yet. Please say a little more and we "
            "will continue."
        )

    parts: list[str] = []
    if duration is not None:
        # The elapsed learner-audio span, which contains the silences
        # too. It is called what it is, so nothing claims the learner
        # spoke for that long.
        parts.append(
            f"Your answers ran for {round(duration / 1000.0, 1)} seconds across "
            f"{facts.turn_count} turns."
        )
    if rate is not None:
        parts.append(f"Your speaking rate was {round(rate, 1)} words per minute.")
    if active_rate is not None:
        parts.append(
            f"Over the time you were actually speaking, that was "
            f"{round(active_rate, 1)} words per minute."
        )
    if pause_count is not None and longest_pause is not None:
        parts.append(
            f"There {'was' if pause_count == 1 else 'were'} "
            f"{int(pause_count)} pause{'s' if pause_count != 1 else ''} inside "
            f"your answer, the longest {int(longest_pause)} milliseconds."
        )
    if not parts:
        return (
            "There was not enough speech in this round to measure, so there "
            "is no feedback to give yet."
        )
    return " ".join(parts)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("a feedback list must be a list")
    lines: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("a feedback entry must be a string")
        lines.append(item.strip())
    return lines


def _number_spelling(value: float) -> str:
    """The number as the model would write it (one or two decimals)."""
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"
