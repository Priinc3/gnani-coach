"""One bounded, audio-aware filler-localization candidate.

What this is
------------
A candidate detector that works on the **learner's own audio**, not on a
cleaned transcript. It localises short, low-energy, voiced bursts that sit
*between* estimated speech regions, and reports each one as a **candidate
event with boundary estimates on the learner sample clock**.

Why this and not a transcript count
-----------------------------------
Counting occurrences of "um"/"uh"/"like" in a cleaned transcript is not
audio analysis: the moment recognition drops a hesitation, the count is
wrong and the localisation is impossible. The build prompt forbids
presenting transcript-only output as audio analysis, so that baseline is
implemented here only as a *comparison*, clearly labelled, never as the
candidate.

Why this is still only a candidate
----------------------------------
Energy and voicing cannot tell a filled pause from a breath, a lip click, a
short word, or a syllable. So every event this module emits carries
status ``candidate`` — never ``confirmed_filler``. Nothing here publishes
a calibrated confidence percentage, a pronunciation grade or a promise of
improvement.

Forced alignment is deliberately *not* used
-------------------------------------------
A forced aligner maps supplied text onto audio. If recognition omitted the
hesitation, the word is not in the supplied text, so there is nothing to
align and no way to infer where the omission happened. Aligning the
cleaned transcript would produce confident-looking timestamps for words
that exist and silence for the one thing we care about. Any alignment
component is proposed in the HANDOFF with its language/model/licence
requirements, not installed here.

What a confirmation would require
---------------------------------
A named human reviewer who listened and labelled the same clips. Until
``fixtures/synthetic/manifest.json`` carries such labels
(``labelProvenance.verified_by`` set), precision/recall are reported as
**NOT EVALUABLE**, not as a pass or a fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from gnani_coach.providers.pcm import SampleClock
from tools.probes.analysis.vad import SpeechRegion, VadResult

#: A filled pause is short. Bounds are the detector's stated parameters and
#: are reported with every result so a reader can reproduce them.
MIN_BURST_MS = 60
MAX_BURST_MS = 420
MIN_RMS_RATIO = 0.06
MAX_RMS_RATIO = 0.55
MIN_PEAK_DBFS = -46.0
VOICING_RATIO = 0.30

EVENT_STATUS_CANDIDATE = "candidate"
EVENT_STATUS_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# inside-region scan parameters
# ---------------------------------------------------------------------------
#
# The gap scan above can only see a hesitation that the VAD turned into a
# *silence*. A hesitation the VAD absorbed into the surrounding speech
# region is invisible to it. The parameters below describe the second case:
# a short voiced event *inside* a speech region.
#
# They are chosen a priori from the acoustics of a short hesitation (voiced,
# steady, 150-800 ms) and from this module's existing conventions. They are
# **not fitted to any particular clip**, and they are reported with every
# result so a reader can reproduce them.

#: Duration band of an inside-region candidate. Given by the brief.
INSIDE_MIN_MS = 150
INSIDE_MAX_MS = 800
#: Analysis frame and hop.
INSIDE_FRAME_MS = 25
INSIDE_HOP_MS = 10
#: Frame RMS relative to the clip's median speech-frame RMS. A hesitation
#: is audible (well above the noise floor) and is not louder than the
#: surrounding words.
INSIDE_MIN_RMS_RATIO = 0.15
INSIDE_MAX_RMS_RATIO = 1.20
#: Fraction of a frame's energy below this frequency that counts as voiced.
#: Same convention as :func:`_voicing_ratio` ("low > 0.5" is voiced).
INSIDE_VOICING_RATIO = 0.50
INSIDE_LOW_BAND_HZ = 500.0
#: Mean cosine distance between consecutive frame spectra. Continuous
#: speech changes its spectrum from frame to frame; a hesitation does not.
INSIDE_MAX_SPECTRAL_CHANGE = 0.30
#: The dominant low-frequency peak is reported as a pitch-steadiness
#: diagnostic. It is not a gate.
INSIDE_PITCH_CEILING_HZ = 1000.0

#: Where a candidate came from. Recorded on every event.
SOURCE_GAP = "gap between VAD speech regions"
SOURCE_INSIDE = "inside a VAD speech region"


@dataclass
class FillerCandidate:
    """One localised short burst, with boundaries on the learner clock."""

    start_sample: int
    end_sample: int
    sample_rate: int
    rms_ratio: float
    voicing_ratio: float
    peak_dbfs: float
    status: str = EVENT_STATUS_CANDIDATE
    #: Never populated with a probability. Present so the field is
    #: explicitly rejected rather than silently absent.
    confidence: None = None
    #: Which scan produced this event.
    window_source: str = SOURCE_GAP
    #: Mean cosine distance between consecutive frame spectra over the
    #: event. Lower is steadier. ``None`` for gap events.
    mean_spectral_change: float | None = None
    #: Range of the dominant low-frequency peak over the event, in Hz.
    #: A diagnostic for pitch steadiness, not a gate.
    dominant_hz_min: float | None = None
    dominant_hz_max: float | None = None

    @property
    def start_ms(self) -> int:
        return int(round(self.start_sample * 1000.0 / self.sample_rate))

    @property
    def end_ms(self) -> int:
        return int(round(self.end_sample * 1000.0 / self.sample_rate))

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "rms_ratio": round(self.rms_ratio, 4),
            "voicing_ratio": round(self.voicing_ratio, 4),
            "peak_dbfs": round(self.peak_dbfs, 2),
            "window_source": self.window_source,
            "mean_spectral_change": (
                None if self.mean_spectral_change is None else round(self.mean_spectral_change, 4)
            ),
            "dominant_hz_min": (
                None if self.dominant_hz_min is None else round(self.dominant_hz_min, 1)
            ),
            "dominant_hz_max": (
                None if self.dominant_hz_max is None else round(self.dominant_hz_max, 1)
            ),
            "confidence": None,
            "confidence_note": "no calibrated confidence is published",
        }


@dataclass
class FillerResult:
    candidates: list[FillerCandidate] = field(default_factory=list)
    detector_params: dict[str, object] = field(default_factory=dict)
    evidence_basis: str = "learner audio (Silero VAD regions + burst acoustics)"
    #: Descriptive observations about the analysed signal. They are **not**
    #: events: a low-energy stretch is not a filled pause, and nothing here
    #: is ever counted as a candidate.
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "detector_params": dict(self.detector_params),
            "evidence_basis": self.evidence_basis,
            "diagnostics": dict(self.diagnostics),
            "status_note": (
                "Every event is a candidate. None is a confirmed filled pause: no "
                "human-reviewed filler labels exist for these fixtures."
            ),
        }


def _rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block.astype(np.float64)))))


def _peak_dbfs(block: np.ndarray) -> float:
    if block.size == 0:
        return -120.0
    peak = float(np.max(np.abs(block.astype(np.float64))))
    if peak <= 0:
        return -120.0
    return 20.0 * np.log10(peak / 32768.0)


def _zero_crossing_ratio(block: np.ndarray) -> float:
    if block.size < 2:
        return 0.0
    signs = np.sign(block.astype(np.float64))
    return float(np.mean(signs[1:] != signs[:-1]))


def detect(
    pcm: bytes,
    sample_rate: int,
    vad: VadResult,
    *,
    min_burst_ms: int = MIN_BURST_MS,
    max_burst_ms: int = MAX_BURST_MS,
    min_rms_ratio: float = MIN_RMS_RATIO,
    max_rms_ratio: float = MAX_RMS_RATIO,
    include_inside_regions: bool = False,
) -> FillerResult:
    """Localise candidate filled-pause bursts inside the learner's clip.

    Candidate windows are the silences *between* estimated speech regions:
    leading and trailing silence is excluded, because a clip boundary is
    not a filled pause. Windows longer than ``max_burst_ms`` are skipped —
    a long silence is a pause, not a hesitation, and this detector does
    not claim otherwise.

    ``include_inside_regions`` additionally runs the **inside-region
    scan** (:func:`detect_inside_regions`), which looks for a short
    voiced, steady event *within* a speech region. It is off by default so
    the gap scan keeps its published meaning and its published numbers.
    """
    samples = np.frombuffer(pcm, dtype="<i2")
    total = len(samples)
    speech_rms = [
        _rms(samples[region.start_sample : min(region.end_sample, total)])
        for region in vad.regions
    ]
    reference_rms = float(np.median(speech_rms)) if speech_rms else 0.0
    if reference_rms <= 0.0:
        return FillerResult(
            candidates=[],
            detector_params=_params(
                min_burst_ms, max_burst_ms, min_rms_ratio, max_rms_ratio, include_inside_regions
            ),
        )

    min_burst = int(round(min_burst_ms * sample_rate / 1000.0))
    max_burst = int(round(max_burst_ms * sample_rate / 1000.0))
    regions: list[SpeechRegion] = vad.regions
    candidates: list[FillerCandidate] = []

    windows: list[tuple[int, int]] = []
    if len(regions) >= 2:
        for previous, following in zip(regions, regions[1:]):
            windows.append((previous.end_sample, following.start_sample))
    elif len(regions) == 1:
        # A single region can still contain an internal burst, but the VAD
        # merge policy already folded short gaps in. Report none rather
        # than inventing a window.
        windows = []

    for start, end in windows:
        if end <= start:
            continue
        width = end - start
        if width < min_burst or width > max_burst:
            continue
        block = samples[start:end]
        rms = _rms(block)
        ratio = rms / reference_rms
        if not (min_rms_ratio <= ratio <= max_rms_ratio):
            continue
        peak = _peak_dbfs(block)
        if peak < MIN_PEAK_DBFS:
            continue
        voicing = _voicing_ratio(block)
        if voicing < VOICING_RATIO:
            continue
        candidates.append(
            FillerCandidate(
                start_sample=start,
                end_sample=end,
                sample_rate=sample_rate,
                rms_ratio=ratio,
                voicing_ratio=voicing,
                peak_dbfs=peak,
                status=EVENT_STATUS_CANDIDATE,
                window_source=SOURCE_GAP,
            )
        )

    if include_inside_regions:
        candidates.extend(detect_inside_regions(pcm, sample_rate, vad).candidates)

    return FillerResult(
        candidates=candidates,
        detector_params=_params(
            min_burst_ms, max_burst_ms, min_rms_ratio, max_rms_ratio, include_inside_regions
        ),
    )


# ---------------------------------------------------------------------------
# inside-region scan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameFeature:
    """One analysis frame of a speech region."""

    start_sample: int
    rms: float
    voicing: float
    change: float
    dominant_hz: float


def _frame_features(
    block: np.ndarray, sample_rate: int, frame: int, hop: int
) -> list[FrameFeature]:
    """Per-frame RMS, voicing, spectral change and dominant low peak."""
    features: list[FrameFeature] = []
    previous: np.ndarray | None = None
    window = np.hanning(frame)
    for start in range(0, max(0, block.size - frame + 1), hop):
        segment = block[start : start + frame].astype(np.float64)
        spectrum = np.abs(np.fft.rfft(segment * window))
        power = spectrum**2
        total = float(np.sum(power))
        if total <= 0.0:
            continue
        freqs = np.fft.rfftfreq(frame, 1.0 / sample_rate)
        low_bins = int(np.searchsorted(freqs, INSIDE_LOW_BAND_HZ))
        low_bins = max(1, min(low_bins, spectrum.size))
        voicing = float(np.sum(power[:low_bins])) / total

        pitch_bins = int(np.searchsorted(freqs, INSIDE_PITCH_CEILING_HZ))
        pitch_bins = max(1, min(pitch_bins, spectrum.size))
        dominant_hz = float(freqs[int(np.argmax(spectrum[:pitch_bins]))])

        if previous is None:
            change = 0.0
        else:
            numerator = float(np.dot(spectrum, previous))
            denominator = float(np.linalg.norm(spectrum) * np.linalg.norm(previous))
            similarity = numerator / denominator if denominator > 0 else 0.0
            change = 1.0 - similarity
        previous = spectrum

        features.append(
            FrameFeature(
                start_sample=start,
                rms=float(np.sqrt(np.mean(np.square(segment)))),
                voicing=voicing,
                change=change,
                dominant_hz=dominant_hz,
            )
        )
    return features


def detect_inside_regions(
    pcm: bytes,
    sample_rate: int,
    vad: VadResult,
    *,
    min_ms: int = INSIDE_MIN_MS,
    max_ms: int = INSIDE_MAX_MS,
    min_rms_ratio: float = INSIDE_MIN_RMS_RATIO,
    max_rms_ratio: float = INSIDE_MAX_RMS_RATIO,
    max_spectral_change: float = INSIDE_MAX_SPECTRAL_CHANGE,
) -> FillerResult:
    """Look for a short voiced, steady event *inside* a speech region.

    A hesitation the VAD absorbed into the surrounding speech is invisible
    to the gap scan. This scan looks for it where it actually is: inside
    the region.

    The event is still a **candidate**. Voicing, steadiness and duration
    cannot separate a filled pause from a breath, a lip click or a short
    word, and nothing here is a confirmed filled pause.

    Parameters are the module constants, stated with every result.
    """
    samples = np.frombuffer(pcm, dtype="<i2")
    frame = int(round(INSIDE_FRAME_MS * sample_rate / 1000.0))
    hop = int(round(INSIDE_HOP_MS * sample_rate / 1000.0))
    if frame <= 0 or hop <= 0:
        return FillerResult(candidates=[], detector_params=_inside_params())

    all_features: list[FrameFeature] = []
    per_region: list[tuple[SpeechRegion, list[FrameFeature]]] = []
    for region in vad.regions:
        block = samples[region.start_sample : region.end_sample]
        if block.size < frame:
            continue
        features = _frame_features(block, sample_rate, frame, hop)
        per_region.append((region, features))
        all_features.extend(features)

    levels = [feature.rms for feature in all_features if feature.rms > 0.0]
    reference = float(np.median(levels)) if levels else 0.0
    if reference <= 0.0:
        return FillerResult(candidates=[], detector_params=_inside_params())

    candidates: list[FillerCandidate] = []
    for region, features in per_region:
        if not features:
            continue
        run: list[FrameFeature] = []

        def _flush(run: list[FrameFeature]) -> None:
            if not run:
                return
            span_samples = (run[-1].start_sample + frame) - run[0].start_sample
            span_ms = span_samples * 1000.0 / sample_rate
            if not (min_ms <= span_ms <= max_ms):
                run.clear()
                return
            mean_change = float(np.mean([feature.change for feature in run]))
            if mean_change > max_spectral_change:
                run.clear()
                return
            rms_values = [feature.rms for feature in run]
            voicings = [feature.voicing for feature in run]
            pitches = [
                feature.dominant_hz for feature in run if feature.dominant_hz > 0.0
            ]
            block = samples[
                region.start_sample + run[0].start_sample : region.start_sample + run[-1].start_sample + frame
            ]
            candidates.append(
                FillerCandidate(
                    start_sample=region.start_sample + run[0].start_sample,
                    end_sample=region.start_sample + run[-1].start_sample + frame,
                    sample_rate=sample_rate,
                    rms_ratio=float(np.mean(rms_values)) / reference,
                    voicing_ratio=float(np.mean(voicings)),
                    peak_dbfs=_peak_dbfs(block),
                    status=EVENT_STATUS_CANDIDATE,
                    window_source=SOURCE_INSIDE,
                    mean_spectral_change=mean_change,
                    dominant_hz_min=min(pitches) if pitches else None,
                    dominant_hz_max=max(pitches) if pitches else None,
                )
            )
            run.clear()

        for feature in features:
            ratio = feature.rms / reference
            voiced = feature.voicing >= INSIDE_VOICING_RATIO
            loud_enough = min_rms_ratio <= ratio <= max_rms_ratio
            if voiced and loud_enough:
                run.append(feature)
            else:
                _flush(run)
        _flush(run)

    candidates.sort(key=lambda candidate: candidate.start_sample)
    return FillerResult(
        candidates=candidates,
        detector_params=_inside_params(),
        evidence_basis="learner audio (Silero VAD regions + inside-region frame acoustics)",
        diagnostics=_structure_diagnostics(per_region, sample_rate=sample_rate),
    )


def _structure_diagnostics(
    per_region: list[tuple[SpeechRegion, list[FrameFeature]]],
    *,
    sample_rate: int,
) -> dict[str, object]:
    """Describe the clip's internal low-energy stretches.

    This is a **description of the signal**, not a detection: a stretch of
    low energy is not a filled pause, and it is never counted as a
    candidate. It is reported so a reader can see what the inside-region
    scan covered and what it did not.
    """
    stretches: list[dict[str, object]] = []
    frame = int(round(INSIDE_FRAME_MS * sample_rate / 1000.0))
    for (region, features) in per_region:
        levels = [feature.rms for feature in features if feature.rms > 0.0]
        reference = float(np.median(levels)) if levels else 0.0
        if reference <= 0.0:
            continue
        run_start: int | None = None
        for feature in features:
            ratio = feature.rms / reference
            if ratio < INSIDE_MIN_RMS_RATIO:
                if run_start is None:
                    run_start = feature.start_sample
            elif run_start is not None:
                stretches.append(
                    {
                        "start_ms": int(
                            round((region.start_sample + run_start) * 1000.0 / sample_rate)
                        ),
                        "end_ms": int(
                            round(
                                (region.start_sample + feature.start_sample)
                                * 1000.0
                                / sample_rate
                            )
                        ),
                    }
                )
                run_start = None
        if run_start is not None and features:
            last = features[-1]
            stretches.append(
                {
                    "start_ms": int(
                        round((region.start_sample + run_start) * 1000.0 / sample_rate)
                    ),
                    "end_ms": int(
                        round(
                            (region.start_sample + last.start_sample + frame)
                            * 1000.0
                            / sample_rate
                        )
                    ),
                }
            )
    return {
        "note": (
            "descriptive only: a low-energy stretch is not a filled pause and is "
            "never counted as a candidate"
        ),
        "threshold": f"frame RMS below {INSIDE_MIN_RMS_RATIO} of the region's median frame RMS",
        "lowEnergyStretches": stretches,
        "lowEnergyStretchCount": len(stretches),
    }


def _inside_params() -> dict[str, object]:
    return {
        "scan": "inside VAD speech regions",
        "min_event_ms": INSIDE_MIN_MS,
        "max_event_ms": INSIDE_MAX_MS,
        "frame_ms": INSIDE_FRAME_MS,
        "hop_ms": INSIDE_HOP_MS,
        "min_rms_ratio": INSIDE_MIN_RMS_RATIO,
        "max_rms_ratio": INSIDE_MAX_RMS_RATIO,
        "voicing_ratio_min": INSIDE_VOICING_RATIO,
        "low_band_hz": INSIDE_LOW_BAND_HZ,
        "max_mean_spectral_change": INSIDE_MAX_SPECTRAL_CHANGE,
        "window_source": SOURCE_INSIDE,
        "note": (
            "parameters are stated a priori and reported with every result; "
            "an event is a candidate, never a confirmed filled pause"
        ),
    }


def _voicing_ratio(block: np.ndarray) -> float:
    """Fraction of windows whose low-frequency energy dominates.

    A crude voiced/unvoiced split. It separates a voiced hesitation from
    pure hiss; it does not distinguish a filled pause from a short word,
    which is exactly why the output stays a candidate.
    """
    if block.size < 64:
        return 0.0
    frame = 256
    voiced = 0
    frames = 0
    for start in range(0, block.size - frame + 1, frame):
        window = block[start : start + frame].astype(np.float64)
        spectrum = np.abs(np.fft.rfft(window * np.hanning(frame)))
        if spectrum.size < 8:
            continue
        energy = float(np.sum(spectrum**2))
        if energy <= 0:
            continue
        low = float(np.sum(spectrum[:8] ** 2)) / energy
        frames += 1
        if low > 0.5:
            voiced += 1
    return voiced / frames if frames else 0.0


def _params(
    min_burst_ms, max_burst_ms, min_rms_ratio, max_rms_ratio, include_inside_regions: bool = False
) -> dict[str, object]:
    params: dict[str, object] = {
        "min_burst_ms": min_burst_ms,
        "max_burst_ms": max_burst_ms,
        "min_rms_ratio": min_rms_ratio,
        "max_rms_ratio": max_rms_ratio,
        "min_peak_dbfs": MIN_PEAK_DBFS,
        "voicing_ratio_min": VOICING_RATIO,
        "window_source": "silences between VAD speech regions only",
    }
    if include_inside_regions:
        params["window_source"] = (
            "silences between VAD speech regions + inside-region scan"
        )
        params["inside_region_scan"] = _inside_params()
    return params


# ---------------------------------------------------------------------------
# transcript-only baseline (explicitly NOT the deliverable candidate)
# ---------------------------------------------------------------------------


def transcript_baseline(transcript: str, markers: tuple[str, ...] = ("um", "uh", "like")) -> dict:
    """Count filler *markers* in a transcript.

    This is the thing the build prompt forbids passing off as audio
    analysis, so it exists only as a labelled comparison row. It has no
    timing information and cannot see an omission.
    """
    lowered = transcript.lower()
    counts = {marker: lowered.count(marker) for marker in markers}
    return {
        "method": "transcript_marker_count",
        "is_audio_analysis": False,
        "limitation": (
            "Counts marker strings in recognised text. Cannot locate an event, "
            "cannot detect a hesitation the recogniser dropped, and cannot "
            "distinguish a lexical 'like' from a filler 'like'."
        ),
        "marker_counts": counts,
        "total": sum(counts.values()),
    }


# ---------------------------------------------------------------------------
# evaluation against verified labels
# ---------------------------------------------------------------------------


@dataclass
class EvaluationReport:
    """Precision/recall against verified labels — or an honest refusal."""

    evaluable: bool
    reason: str
    positives_available: int = 0
    negatives_available: int = 0
    precision: float | None = None
    recall: float | None = None
    matched_boundary_errors_ms: list[int] = field(default_factory=list)
    matching_rule: str = "one-to-one, both boundaries within tolerance_ms"

    def to_dict(self) -> dict[str, object]:
        return {
            "evaluable": self.evaluable,
            "reason": self.reason,
            "positives_available": self.positives_available,
            "negatives_available": self.negatives_available,
            "precision": self.precision,
            "recall": self.recall,
            "matching_rule": self.matching_rule,
            "matched_boundary_errors_ms": list(self.matched_boundary_errors_ms),
            "target": {
                "precision": 0.90,
                "recall": 0.80,
                "p95_boundary_error_ms": 300,
                "min_positives_per_mode": 20,
                "min_negatives_per_mode": 20,
            },
            "target_met": False if not self.evaluable else None,
        }


def evaluate_against_labels(
    labelled_events: list[dict] | None,
    candidates: list[FillerCandidate],
    *,
    tolerance_ms: int = 300,
    verified: bool = False,
) -> EvaluationReport:
    """Evaluate, or decline to.

    ``labelled_events`` must be events a **named human reviewer** labelled
    after listening. ``verified=False`` — which is the current state for
    every synthetic fixture — produces ``evaluable: false`` with the
    reason, rather than a number computed against the detector's own
    predictions.
    """
    if not verified or not labelled_events:
        return EvaluationReport(
            evaluable=False,
            reason=(
                "No human-reviewed filler labels exist for the synthetic fixtures. "
                "A forced aligner or the candidate detector's own output cannot "
                "substitute for a reviewer who listened. Precision/recall are "
                "NOT EVALUABLE, and the >=90% precision / >=80% recall / "
                "p95<=300ms target is neither met nor failed."
            ),
            positives_available=0,
            negatives_available=0,
        )

    matched: list[int] = []
    true_positives = 0
    used: set[int] = set()
    for label in sorted(labelled_events, key=lambda item: item["start_ms"]):
        for index, candidate in enumerate(candidates):
            if index in used:
                continue
            if (
                abs(candidate.start_ms - label["start_ms"]) <= tolerance_ms
                and abs(candidate.end_ms - label["end_ms"]) <= tolerance_ms
            ):
                used.add(index)
                true_positives += 1
                matched.append(
                    max(
                        abs(candidate.start_ms - label["start_ms"]),
                        abs(candidate.end_ms - label["end_ms"]),
                    )
                )
                break
    positives = len(labelled_events)
    detected = len(candidates)
    precision = round(true_positives / detected, 4) if detected else None
    recall = round(true_positives / positives, 4) if positives else None
    return EvaluationReport(
        evaluable=True,
        reason="evaluated against human-reviewed labels",
        positives_available=positives,
        negatives_available=0,
        precision=precision,
        recall=recall,
        matched_boundary_errors_ms=matched,
    )


def clock_span(clock: SampleClock, vad: VadResult) -> dict[str, int]:
    """Convenience view of the sample clock used for every anchor."""
    return {
        "clock_span_ms": clock.to_ms(clock.genuine_samples),
        "speech_active_ms": vad.speech_active_ms,
        "padding_ms": clock.to_ms(clock.padding_samples),
    }
