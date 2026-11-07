"""Turns: how a conversational turn is built out of recognised segments.

**A turn is not a segment.** One sentence can be split into several
recognised segments when the recogniser's VAD closes on a pause, so the
grouping is this application's own and is never taken from a provider
segment boundary (see ``docs/contracts/call-transport.md`` §2).

The end-of-turn policy
----------------------

A turn is *completed* when both hold:

* the silence since the last speech is at least the **hold** (1.2 s by
  default), and
* the turn carries at least the **minimum word count** (3 by default).

Until then the turn stays open, so a learner who says "give me a moment"
is not cut off mid-thought. A client may also extend the hold
explicitly.

The silence detector
--------------------

The runtime's end-of-turn detector is a **simple energy gate** over the
learner's own frames. It is an *endpointing heuristic*, not a
measurement:

* it decides when the learner has finished a turn;
* it is never written to the durable metrics, and it never appears as an
  observation;
* the measured speech regions come from the analysis service's VAD, not
  from here.

The learner-audio sample clock is the only clock this module uses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gnani_coach.analysis.measurement import count_words
from gnani_coach.conversation.config import (
    ENDPOINTING_GATE_DBFS,
    ENDPOINTING_HANGOVER_MS,
    MAX_TURN_AUDIO_BYTES,
    MAX_TURN_MS,
)
from gnani_coach.ports.speech_to_text import TranscriptSegment
from gnani_coach.ports.types import RoundId, TurnId

#: The duration of one 1,024-byte frame at 16 kHz mono s16le.
FRAME_DURATION_MS = 32


@dataclass
class LearnerTurn:
    """One conversational turn of the learner.

    The transcript is **transient**: it lives in memory for the duration
    of the turn and is released with it. It is never written to metrics,
    logs or caches.
    """

    turn_id: TurnId
    round_id: RoundId | None
    started_clock_ms: int
    ended_clock_ms: int = 0
    audio: bytearray = field(default_factory=bytearray)
    segments: list[TranscriptSegment] = field(default_factory=list)
    text: str = ""
    #: A fenced turn is one the learner interrupted. Its late reply and
    #: its late audio are never sent, and it never counts as a completed
    #: practice round.
    fenced: bool = False
    completed: bool = False

    @property
    def duration_ms(self) -> int:
        """The elapsed learner-audio span of this turn.

        It includes the source's leading and trailing silence and it
        excludes the end padding, because the runtime never hands padding
        to the analysis.
        """
        return max(0, self.ended_clock_ms - self.started_clock_ms)

    @property
    def word_count(self) -> int:
        return count_words(self.text)

    def add_segment(self, segment: TranscriptSegment) -> None:
        """Append one recognised segment to the turn."""
        self.segments.append(segment)
        if segment.text:
            self.text = f"{self.text} {segment.text}".strip()

    def release(self) -> None:
        """Drop the transient content of the turn."""
        self.audio = bytearray()
        self.text = ""


class Endpointing:
    """The end-of-turn detector: an energy gate over the learner's frames."""

    def __init__(
        self,
        *,
        hold_ms: int,
        min_words: int,
        hangover_ms: int = ENDPOINTING_HANGOVER_MS,
        gate_dbfs: float = ENDPOINTING_GATE_DBFS,
    ) -> None:
        self.hold_ms = int(hold_ms)
        self.min_words = int(min_words)
        self.hangover_ms = int(hangover_ms)
        self.gate_dbfs = float(gate_dbfs)
        self._last_speech_ms: int | None = None
        self._clock_ms: int = 0
        self._speech_run_ms: int = 0
        #: The clock at the start of the current run of speech.
        self._speech_onset_ms: int | None = None
        #: How much the learner asked for more time.
        self.extended_by_ms: int = 0

    # -- clock ---------------------------------------------------------
    @property
    def clock_ms(self) -> int:
        """The learner-audio sample clock, in milliseconds."""
        return self._clock_ms

    def advance(self, duration_ms: int) -> None:
        """Move the learner-audio sample clock forward."""
        self._clock_ms += max(0, int(duration_ms))

    # -- gate ----------------------------------------------------------
    def observe(self, frame: bytes) -> bool:
        """Feed one frame to the gate. True when the frame is speech."""
        speech = _is_speech(frame, self.gate_dbfs)
        if speech:
            self._last_speech_ms = self._clock_ms
            if self._speech_onset_ms is None:
                # The learner started speaking in this frame: the onset is
                # the clock at the *start* of the frame, not at its end.
                self._speech_onset_ms = max(0, self._clock_ms - FRAME_DURATION_MS)
            self._speech_run_ms += FRAME_DURATION_MS
        else:
            self._speech_run_ms = 0
            self._speech_onset_ms = None
        return speech

    @property
    def voice_onset_gap_ms(self) -> int:
        """How long the learner has been speaking, on the audio clock.

        ``0`` when the learner is not speaking. It is the elapsed
        **learner-audio** time since the current run of speech started,
        so it says nothing about the wall clock.
        """
        if self._speech_onset_ms is None:
            return 0
        return max(0, self._clock_ms - self._speech_onset_ms)

    @property
    def silence_ms(self) -> int:
        """The silence since the last speech, in milliseconds."""
        if self._last_speech_ms is None:
            return self._clock_ms
        return max(0, self._clock_ms - self._last_speech_ms)

    @property
    def speech_run_ms(self) -> int:
        """How long the current run of speech has lasted.

        A short noise is not speech: the learner has to speak for the
        hangover before the coach is interrupted.
        """
        return self._speech_run_ms

    def hold_expired(self) -> bool:
        """True when the hold has elapsed since the last speech."""
        return self.silence_ms >= self.hold_ms

    def extend_hold(self, extra_ms: int) -> None:
        """Give the learner more time ("give me a moment")."""
        self.hold_ms += max(0, int(extra_ms))
        self.extended_by_ms += max(0, int(extra_ms))

    def reset(self) -> None:
        """Start a new turn.

        The silence clock restarts from **now**: the previous turn's last
        segment ended here, so the silence since the last segment is
        zero and the hold has to elapse again.
        """
        self._last_speech_ms = self._clock_ms
        self._speech_run_ms = 0
        self._speech_onset_ms = None


def turn_is_complete(
    turn: LearnerTurn,
    endpointing: Endpointing,
    *,
    min_words: int,
    max_turn_ms: int = MAX_TURN_MS,
) -> bool:
    """Whether a turn may be completed right now.

    Both the hold and the word count must hold. A turn that has been open
    for too long is completed anyway, so a very quiet learner still moves
    the conversation on — the turn is then reported as *too little
    speech*, never as a measured zero.
    """
    if endpointing.hold_expired() and turn.word_count >= min_words:
        return True
    return turn.duration_ms >= max_turn_ms


def turn_audio_is_full(audio: bytearray) -> bool:
    """True when the turn's buffer reached its bound."""
    return len(audio) >= MAX_TURN_AUDIO_BYTES


def _is_speech(frame: bytes, gate_dbfs: float) -> bool:
    """A frame is speech when its RMS is above the gate.

    The measurement is the root-mean-square of the signed 16-bit samples,
    expressed in dBFS. It is a cheap, dependency-free estimate used only
    for endpointing.
    """
    if not frame:
        return False
    count = len(frame) // 2
    if count == 0:
        return False
    total = 0
    for index in range(0, len(frame) - 1, 2):
        sample = int.from_bytes(frame[index : index + 2], "little", signed=True)
        total += sample * sample
    rms = math.sqrt(total / count)
    if rms <= 0:
        return False
    dbfs = 20.0 * math.log10(rms / 32768.0)
    return dbfs >= gate_dbfs
