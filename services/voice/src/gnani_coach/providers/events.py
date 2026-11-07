"""Provider-internal diagnostic events.

These are **not** shared-contract objects. The draft v0.1 schemas
(``analysis-observation``, ``durable-metrics``) are owned by Phase 03 and
this phase must not invent fields or flip capability flags.

What this module provides instead is a lossless, in-process record of what
a provider actually did, from which Phase 03 can propose an explicit
mapping. Every event is content-free by construction except
:attr:`SttTranscriptEvent.text` and :attr:`TtsAudioChunk.bytes`, which are
synthetic fixture material in this phase and are only written to an
opt-in payload capture — never to the default log.

Timing rule, enforced by field names rather than convention:

* ``server_emitted_at`` / ``latency_ms`` / ``audio_duration_ms`` are
  **server-reported** values. They are metadata about the provider.
* ``learner_clock_samples`` is the **local sample clock**. It is the only
  thing permitted to anchor an evidence span.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Literal

EventStatus = Literal["observed", "rejected", "fenced", "duplicate", "out_of_order"]


@dataclass(frozen=True)
class ConnectionEvent:
    """Handshake outcome. ``config`` is the server's echoed configuration."""

    provider: str
    endpoint_path: str
    connected_at: float
    config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SttTranscriptEvent:
    """One completed VAD segment.

    ``segment_index`` and ``segment_id`` are retained for deduplication.
    ``audio_duration_ms`` is the provider's report of how much speech the
    segment contained — **not** a word timing and **not** the position of
    the segment in the learner's clip.
    """

    segment_id: str | None
    segment_index: int | None
    text: str
    audio_duration_ms: int | None
    latency_ms: int | None
    server_timestamp: str | None
    received_at: float
    #: Local sample-clock position when this transcript arrived.
    learner_clock_samples: int
    status: EventStatus = "observed"


@dataclass(frozen=True)
class SttProcessingEvent:
    """VAD closed a segment; transcription has begun. Not a turn boundary."""

    server_timestamp: str | None
    received_at: float
    learner_clock_samples: int


@dataclass(frozen=True)
class SttSettingsEvent:
    """`settings_updated` acknowledgement."""

    config: dict[str, object]
    received_at: float


@dataclass(frozen=True)
class ProviderErrorEvent:
    """A provider `error` frame. ``message`` is redacted before storage."""

    provider: str
    message: str
    server_timestamp: str | None
    received_at: float


@dataclass(frozen=True)
class UnrecognizedFrame:
    """A well-formed provider frame of a type this adapter does not model.

    Recorded rather than raised or dropped, so protocol drift between the
    published documentation and the live service stays visible in results
    instead of silently changing behaviour.
    """

    provider: str
    message_type: str
    keys: tuple[str, ...]
    received_at: float
    note: str = ""


@dataclass(frozen=True)
class TtsLifecycleEvent:
    """`start` for a synthesis request."""

    request_id: str | None
    received_at: float


@dataclass(frozen=True)
class TtsAudioChunk:
    """One base64 audio chunk, decoded.

    ``chunk_index`` is retained so ordering can be verified rather than
    assumed. ``is_first_nonempty`` marks the arrival the probe reports as
    "first audio" — this is *backend* chunk arrival, never browser
    first-audible latency.
    """

    request_id: str | None
    chunk_index: int | None
    bytes: bytes
    received_at: float
    is_final: bool = False
    is_first_nonempty: bool = False
    status: EventStatus = "observed"


@dataclass(frozen=True)
class TtsCompletionEvent:
    """`complete` for a synthesis request."""

    request_id: str | None
    chunk_index: int | None
    received_at: float
    total_bytes: int


@dataclass(frozen=True)
class GeminiReplyEvent:
    """A text reply from the reasoning model.

    ``model`` is the exact model id used. ``store`` records whether
    server-side conversation storage was requested (``False`` keeps the
    conversation stateless, per the Gemini Interactions API).
    """

    model: str
    interaction_id: str | None
    text: str
    requested_at: float
    completed_at: float
    store: bool
    tools_enabled: bool = False


def decode_audio_payload(value: str, *, max_bytes: int = 4 * 1024 * 1024) -> bytes:
    """Strictly decode a base64 TTS payload.

    Empty audio is legal (the `complete` frame carries it). Invalid base64
    or an oversized payload is a protocol failure, never a silent empty
    string that would look like "no audio yet".
    """
    if value is None:
        return b""
    if not isinstance(value, str):
        raise ValueError("audio payload must be a base64 string")
    if value == "":
        return b""
    if len(value) > max_bytes * 2:
        raise ValueError("audio payload exceeds the decoded size bound")
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"audio payload is not valid base64: {type(exc).__name__}") from exc
    if len(decoded) > max_bytes:
        raise ValueError("audio payload exceeds the decoded size bound")
    return decoded
