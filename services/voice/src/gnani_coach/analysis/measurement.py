"""Delivery measurements, with the denominators and the sources kept straight.

**Ported into the service tree from** ``tools/probes/analysis/metrics.py``
(Phase 02). The probe code is *read* for the semantics and *copied* here;
nothing in this package imports from ``tools/``.

This is the module that the Phase 03 VERIFY handoff item 2 is about.

The draft v0.1 schema gives ``speech.rate_wpm`` and
``speech.active_rate_wpm`` the *same* method description, which conflates
two different quantities. They are computed here with four explicitly
distinct denominators, and the four values are reported side by side
every time:

==========================  ==========================  ==================
Quantity                    Numerator                   Denominator
==========================  ==========================  ==================
``span_ms``                 elapsed learner audio       the learner clip's
                             (samples actually played)  own elapsed span
``speech_active_ms``        time VAD marked speech      same sample clock
``rate_wpm``                recognised words            ``span_ms``
``active_rate_wpm``         recognised words            ``speech_active_ms``
==========================  ==========================  ==================

Never used as a denominator: total connection time, total session time,
network round trips, provider emission timestamps, or any assistant
audio.

Two repairs from Phase 02 FIX-1 live here as well
--------------------------------------------------

**Trusted source (P02-07).** :func:`assert_trusted_learner_source`
requires an *explicitly trusted* learner or synthetic-learner source
declaration, and rejects an empty source set, an assistant-only set, a
mixed set and any unknown classification. A source label is a
**declaration**, not a proof: nothing here establishes diarization or
echo cancellation, and the module says so rather than implying it.

**Recognition status (P02-07).** A missing transcription and a
transcript with no analyzable speech are *not* a measured zero rate.
:func:`compute` accepts ``recognized_text=None`` (no transcript at all)
and ``recognized_text=""`` (the recogniser returned no analyzable
speech), and in both cases the rate properties return ``None`` with the
reason recorded in ``recognition_status``. Only a transcript that was
actually produced can produce a rate, and a transcript with no word
tokens produces a genuine measured ``0.0``.

Denominator notes that must survive into any final DTO
---------------------------------------------------------
* ``clip_span_ms`` **includes** the source's leading and trailing
  silence — that is the elapsed span the learner actually produced.
* ``clip_span_ms`` **excludes** the end padding (the zero pad added to
  reach a frame boundary), which is not elapsed audio.
* ``speech_active_ms`` is a Silero VAD *estimate*, not ground truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gnani_coach.providers.errors import InvalidRequestError

WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)

#: Source roles. A measurement only accepts the learner role.
ROLE_LEARNER = "learner"
ROLE_ASSISTANT = "assistant"
ROLE_UNKNOWN = "unknown"

#: Roles that may appear in a learner-only measurement.
ALLOWED_ROLES = frozenset({ROLE_LEARNER})

#: Recognition outcomes, kept distinct on purpose.
RECOGNITION_MEASURED = "measured"
RECOGNITION_NO_SPEECH = "no-analyzable-speech"
RECOGNITION_MISSING = "missing-transcription"


def count_words(text: str) -> int:
    """Word count from recognised text.

    Counts Unicode word tokens. Punctuation-only spans are not words.
    """
    if not text:
        return 0
    return len(WORD_RE.findall(text))


@dataclass(frozen=True)
class ClipSource:
    """One declared audio source of a measurement clip.

    ``label`` names the source; ``role`` classifies it; ``trusted`` says
    whether the classification is *explicitly* trusted for this service.
    A label alone proves nothing about speaker identity.
    """

    label: str
    role: str = ROLE_UNKNOWN
    synthetic: bool = False
    trusted: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "role": self.role,
            "synthetic": self.synthetic,
            "trusted": self.trusted,
        }


#: The canonical trusted source for a synthetic learner fixture.
SYNTHETIC_LEARNER = ClipSource(
    label="synthetic-learner", role=ROLE_LEARNER, synthetic=True, trusted=True
)

#: The canonical trusted source for a live learner stream.
LIVE_LEARNER = ClipSource(
    label="learner", role=ROLE_LEARNER, synthetic=False, trusted=True
)


def assert_trusted_learner_source(sources: list[ClipSource] | None) -> None:
    """Require an explicitly trusted learner source for a measurement.

    Rejected, each for its own stated reason:

    * **empty** — no source was declared at all;
    * **unknown** — a source's role could not be classified;
    * **assistant-only** — the clip is the assistant's audio;
    * **mixed** — learner and assistant audio in one clip;
    * **untrusted** — the learner source is declared but not trusted.

    A label is a declaration. This check does **not** establish
    diarization and does **not** establish echo cancellation; full
    stream ownership and echo exclusion remain runtime work.
    """
    if not sources:
        raise InvalidRequestError(
            "measurement clip declares no audio source; learner-only cannot be "
            "established from an unlabelled clip"
        )
    for source in sources:
        if source.role not in ALLOWED_ROLES and source.role != ROLE_ASSISTANT:
            raise InvalidRequestError(
                f"audio source {source.label!r} has an unknown role "
                f"({source.role!r}); refusing to measure it as learner audio"
            )
    if any(source.role == ROLE_ASSISTANT for source in sources):
        raise InvalidRequestError(
            "measurement clip contains assistant audio; learner-only "
            "measurements require learner audio only"
        )
    if len({source.role for source in sources}) > 1:
        raise InvalidRequestError(
            "measurement clip mixes multiple audio roles; learner audio only"
        )
    untrusted = [source.label for source in sources if not source.trusted]
    if untrusted:
        raise InvalidRequestError(
            "audio source(s) "
            + ", ".join(repr(label) for label in untrusted)
            + " are not explicitly trusted learner sources"
        )


def assert_no_assistant_audio(audio_sources: list[str]) -> None:
    """Refuse a measurement whose clip mixes learner and assistant audio.

    Kept for callers that only carry source *labels*. An empty list is
    refused too: an unlabelled clip cannot be asserted to be learner
    only. For the full check, including role classification and trust,
    use :func:`assert_trusted_learner_source`.
    """
    if not audio_sources:
        raise InvalidRequestError(
            "measurement clip declares no audio source; learner-only cannot be "
            "established from an unlabelled clip"
        )
    if len(set(audio_sources)) > 1:
        raise InvalidRequestError(
            "measurement clip mixes multiple audio sources; learner audio only"
        )


@dataclass
class DeliveryMetrics:
    """One learner clip's measurements, denominators explicit."""

    clip_span_ms: int
    speech_active_ms: int
    #: ``None`` only when the recognition status is ``missing``; a
    #: transcript that exists but holds no words is a measured ``0``.
    recognized_word_count: int | None
    recognition_status: str = RECOGNITION_MEASURED
    trailing_pad_ms: int = 0
    leading_silence_ms: int = 0
    trailing_silence_ms: int = 0
    #: Whether the source's leading/trailing silence is inside the span.
    source_silence_included_in_span: bool = True
    #: Declared sources of the measured clip.
    source_labels: list[str] = field(default_factory=list)
    #: Estimated internal pauses, in order.
    internal_pause_ms: list[int] = field(default_factory=list)
    method_notes: dict[str, str] = field(default_factory=dict)

    @property
    def rate_wpm(self) -> float | None:
        """Words per minute over the **elapsed learner span**.

        ``None`` when there is no transcript to count: a missing
        transcription and a transcript with no analyzable speech are not
        a measured zero rate.
        """
        if self.clip_span_ms <= 0:
            return None
        if not self.has_measured_rate:
            return None
        return round(self.recognized_word_count * 60000.0 / self.clip_span_ms, 2)

    @property
    def active_rate_wpm(self) -> float | None:
        """Words per minute over the **speech-active duration**.

        ``None`` under the same conditions as :attr:`rate_wpm`, and also
        when the VAD found no speech-active time at all.
        """
        if self.speech_active_ms <= 0:
            return None
        if not self.has_measured_rate:
            return None
        return round(self.recognized_word_count * 60000.0 / self.speech_active_ms, 2)

    @property
    def longest_pause_ms(self) -> int:
        return max(self.internal_pause_ms, default=0)

    @property
    def pause_count(self) -> int:
        return len(self.internal_pause_ms)

    @property
    def has_measured_rate(self) -> bool:
        """True only when a rate was actually measured."""
        return self.recognition_status == RECOGNITION_MEASURED

    def to_dict(self) -> dict[str, object]:
        return {
            "clip_span_ms": self.clip_span_ms,
            "speech_active_ms": self.speech_active_ms,
            "recognized_word_count": self.recognized_word_count,
            "recognition_status": self.recognition_status,
            "rate_wpm": self.rate_wpm,
            "active_rate_wpm": self.active_rate_wpm,
            "denominators": {
                "rate_wpm": "clip_span_ms (elapsed learner audio)",
                "active_rate_wpm": "speech_active_ms (VAD speech-active)",
                "excluded": [
                    "total connection time",
                    "total session time",
                    "assistant audio",
                    "network round trips",
                    "provider emission timestamps",
                ],
            },
            "span_includes": {
                "source_leading_silence": self.source_silence_included_in_span,
                "source_trailing_silence": self.source_silence_included_in_span,
                "end_padding": False,
            },
            "leading_silence_ms": self.leading_silence_ms,
            "trailing_silence_ms": self.trailing_silence_ms,
            "trailing_pad_ms": self.trailing_pad_ms,
            "internal_pause_ms": list(self.internal_pause_ms),
            "pause_count": self.pause_count,
            "longest_pause_ms": self.longest_pause_ms,
            "source_labels": list(self.source_labels),
            "source_caveat": (
                "source identity is a declared label; diarization and echo "
                "cancellation are NOT established by this check"
            ),
            "method_notes": dict(self.method_notes),
        }


def compute(
    *,
    clip_span_ms: int,
    speech_active_ms: int,
    recognized_text: str | None,
    trailing_pad_ms: int = 0,
    leading_silence_ms: int = 0,
    trailing_silence_ms: int = 0,
    internal_pause_ms: list[int] | None = None,
    source_labels: list[str] | None = None,
    source_silence_included_in_span: bool = True,
) -> DeliveryMetrics:
    """Build :class:`DeliveryMetrics` with the denominators already separated.

    ``recognized_text`` distinguishes three outcomes:

    * ``None`` — **no transcription at all** (``missing-transcription``).
      The word count is unknown and both rates are ``None``.
    * ``""`` — the recogniser ran and returned **no analyzable speech**
      (``no-analyzable-speech``). The word count is ``0`` and both rates
      are ``None``: this is *not* a measured zero rate.
    * any other string — a transcript exists and was measured
      (``measured``). A transcript with no word tokens in it yields a
      genuine measured ``0.0`` rate.
    """
    if clip_span_ms < 0 or speech_active_ms < 0:
        raise InvalidRequestError("durations must be nonnegative")
    if speech_active_ms > clip_span_ms + 1:
        raise InvalidRequestError("speech-active time cannot exceed the clip span")

    if recognized_text is None:
        status = RECOGNITION_MISSING
        word_count: int | None = None
    elif recognized_text == "":
        status = RECOGNITION_NO_SPEECH
        word_count = 0
    else:
        status = RECOGNITION_MEASURED
        word_count = count_words(recognized_text)

    return DeliveryMetrics(
        clip_span_ms=clip_span_ms,
        speech_active_ms=speech_active_ms,
        recognized_word_count=word_count,
        recognition_status=status,
        trailing_pad_ms=trailing_pad_ms,
        leading_silence_ms=leading_silence_ms,
        trailing_silence_ms=trailing_silence_ms,
        source_silence_included_in_span=source_silence_included_in_span,
        source_labels=list(source_labels or []),
        internal_pause_ms=list(internal_pause_ms or []),
        method_notes={
            "clip_span_ms": (
                "learner audio sample clock; end padding excluded; source "
                + (
                    "leading and trailing silence included"
                    if source_silence_included_in_span
                    else "silence excluded"
                )
            ),
            "speech_active_ms": (
                "estimated by Silero VAD; estimate, not ground truth"
            ),
            "rate_wpm": "recognized words / clip_span_ms",
            "active_rate_wpm": "recognized words / speech_active_ms",
            "recognition_status": (
                "measured = a transcript exists; no-analyzable-speech = the "
                "recogniser returned nothing; missing-transcription = no "
                "transcript was obtained. Only 'measured' yields a rate."
            ),
        },
    )
