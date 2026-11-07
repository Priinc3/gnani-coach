"""The recognition stream: the runtime's view of a recogniser.

The frozen speech-to-text port submits one clip per session, so the
stream treats a submission as a reconnectable step. What is proved here:

* a clip is submitted and its segments come back;
* the pending buffer is bounded, so a burst cannot grow the memory;
* the **submission ceiling** is a hard stop: past it the recogniser is
  not called again;
* a reconnect carries the **same VAD settings object**, and the
  reconnects are counted.
"""

from __future__ import annotations

import pytest

from gnani_coach.conversation.recognition import (
    MAX_PENDING_AUDIO_BYTES,
    PortRecognitionStream,
)
from gnani_coach.ports.speech_to_text import SttOpenRequest
from gnani_coach.providers.errors import BudgetExceededError
from phase05_support import FakeSttPort, loud_frame, silent_frame


def _request() -> SttOpenRequest:
    return SttOpenRequest(
        language_code="en-IN",
        sample_rate=16000,
        vad=None,
        connection_id="con_a1b2c3d4",
    )


@pytest.mark.anyio
async def test_a_submission_returns_the_segments() -> None:
    """The clip is submitted and the segments come back."""
    port = FakeSttPort()
    stream = PortRecognitionStream(port=port, request=_request())
    await stream.push_frame(loud_frame())
    await stream.push_frame(loud_frame())
    # The fake recogniser closes a segment on the first silent frame.
    await stream.push_frame(silent_frame())
    segments = await stream.collect(grace_ms=10)
    assert port.submissions == 1
    assert stream.submissions == 1
    assert segments, "the recogniser answered with a segment"
    await stream.close(reason="done")


@pytest.mark.anyio
async def test_the_pending_buffer_is_bounded() -> None:
    """A burst of frames is submitted as it goes, not buffered whole."""
    port = FakeSttPort()
    stream = PortRecognitionStream(port=port, request=_request())
    frames = (MAX_PENDING_AUDIO_BYTES // 1024) + 16
    for _ in range(frames):
        await stream.push_frame(loud_frame())
    assert port.submissions >= 1, "the burst was submitted, not buffered"
    assert port.max_clip_bytes <= MAX_PENDING_AUDIO_BYTES
    await stream.close(reason="done")


@pytest.mark.anyio
async def test_the_submission_ceiling_is_a_hard_stop() -> None:
    """Past the ceiling the recogniser is not called again."""
    port = FakeSttPort()
    stream = PortRecognitionStream(port=port, request=_request(), max_submissions=2)
    for _ in range(2):
        await stream.push_frame(loud_frame())
        await stream.collect(grace_ms=10)
    assert stream.submissions == 2
    assert port.submissions == 2

    await stream.push_frame(loud_frame())
    with pytest.raises(BudgetExceededError):
        await stream.collect(grace_ms=10)
    assert port.submissions == 2, "the recogniser was called past the ceiling"
    await stream.close(reason="done")


@pytest.mark.anyio
async def test_a_reconnect_carries_the_same_vad_object() -> None:
    """The VAD settings survive a reconnect, and the reconnect is counted."""
    port = FakeSttPort()
    request = _request()
    stream = PortRecognitionStream(port=port, request=request)
    await stream.push_frame(loud_frame())
    await stream.collect(grace_ms=10)
    assert stream.reconnects == 0
    await stream.reopen()
    assert stream.reconnects == 1
    assert stream._request.vad is request.vad
    await stream.close(reason="done")


@pytest.mark.anyio
async def test_a_closed_stream_collects_nothing() -> None:
    """A closed stream never calls the recogniser again."""
    port = FakeSttPort()
    stream = PortRecognitionStream(port=port, request=_request())
    await stream.push_frame(loud_frame())
    await stream.close(reason="done")
    assert await stream.collect(grace_ms=10) == ()
    assert port.submissions == 0
