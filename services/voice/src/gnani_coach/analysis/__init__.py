"""Analysis — **Phase 05 owns this tree**.

Phase 03 created this package as a stub so the composition root had a
real import and so G1 builders could see the shape. The stub answered
with ``insufficient_evidence`` for every metric, which was the documented
unavailable behaviour while no measurement existed.

Phase 05 replaces the stub with the real measurement: the learner-only
analysis service in :mod:`gnani_coach.analysis.service`, the Phase 02
measurement semantics in :mod:`gnani_coach.analysis.measurement` and the
Silero VAD in :mod:`gnani_coach.analysis.vad`.

Frozen contract: ``docs/contracts/seams.md``.

The exported name is ``get_analysis``. It is used as a FastAPI
dependency, so the composition root does not change.

Honesty rules that survive into the implementation:

* a missing transcription is ``missing-transcription`` and never a
  measured ``0``;
* the filler capability is unvalidated, so the filler count is always
  ``insufficient_evidence`` with the reason
  ``filler_detection_unvalidated``;
* the two speaking rates keep separate methods **and** separate
  denominators;
* the measured audio declares its source, and the declaration is not a
  proof of diarization or echo cancellation;
* the VAD model asset lives in an ignored cache inside this tree and is
  never downloaded at request time. When it is absent, every
  VAD-dependent observation is ``unavailable`` with a null value.
"""

from __future__ import annotations

from gnani_coach.analysis.measurement import (
    RECOGNITION_MEASURED,
    RECOGNITION_MISSING,
    RECOGNITION_NO_SPEECH,
    count_words,
)
from gnani_coach.analysis.service import (
    REPORTED_METRIC_KEYS,
    LearnerAudioAnalysis,
)
from gnani_coach.analysis.vad import (
    asset_present,
    describe_asset,
    model_path,
    prepare_model,
)
from gnani_coach.ports.analysis import (
    AnalysisObservation,
    AnalysisPort,
    AnalysisRequest,
    AnalysisResult,
)
from gnani_coach.ports.types import RecognitionStatus

__all__ = [
    "AnalysisObservation",
    "AnalysisPort",
    "AnalysisRequest",
    "AnalysisResult",
    "LearnerAudioAnalysis",
    "RECOGNITION_MEASURED",
    "RECOGNITION_MISSING",
    "RECOGNITION_NO_SPEECH",
    "REPORTED_METRIC_KEYS",
    "RecognitionStatus",
    "asset_present",
    "count_words",
    "describe_asset",
    "get_analysis",
    "model_path",
    "prepare_model",
]

#: One process-wide analysis service. The ONNX VAD session is expensive to
#: build and is safe to share, so the service is created once and reused.
_SERVICE: AnalysisPort | None = None


def get_analysis() -> AnalysisPort:
    """The analysis port for the current process.

    The real measurement: the learner's own audio, the frozen method
    identifiers, the frozen denominators and the frozen recognition
    status vocabulary.
    """
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = LearnerAudioAnalysis()
    return _SERVICE
