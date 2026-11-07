"""Gnani realtime text-to-speech adapter (Timbre).

Primary documentation read 2026-10-18:
https://docs.gnani.ai/api/TTS/tts-websocket and
https://docs.gnani.ai/api/TTS/available-voices

Contract implemented here
-------------------------
* ``wss://api.vachana.ai/api/v1/tts``, authenticated with the
  ``X-API-Key-ID`` upgrade header.
* One synthesis request in flight per connection.
* ``start`` -> ``audio``(base64) -> ``complete`` lifecycle, with the
  ``error`` frame handled as a recoverable-or-fatal provider message.

The container/header question [P2]
----------------------------------
The docs say ``container: wav`` yields "WAV file (with header)" and
``container: raw`` yields "Raw 16-bit PCM". That leaves open whether a
multi-chunk WAV stream repeats a 44-byte RIFF header per chunk. This
adapter does **not** guess. It records the raw first bytes and
:func:`inspect_container` reports what was actually observed, so a browser
integration is designed against measured behaviour. ``container: raw`` is
the default for that reason.

Cancellation: what is and is not possible [P2]
----------------------------------------------
The reviewed page documents **no cancel control message**, and this adapter
does not invent one. Instead:

* :meth:`GnaniTtsSession.cancel_consumption` fences the consumer — later
  chunks are recorded with status ``fenced`` and never handed to the
  caller. This is *stopping consumption*.
* It is explicitly **not** cancelling provider computation or billing. The
  request may still be synthesised and billed server-side.
* :meth:`GnaniTtsSession.drain` safely finishes the in-flight request.
  Closing the connection is the only provider-side stop available, and it
  is recorded as such.

Timbre v2.5 is the starting model family per BUILD.md; v3.0 is an explicit
capability alternative, never an automatic upgrade. Voice/model pairing is
validated locally against the documented catalog so a mismatched pair
fails before a credential is spent.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import struct
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from types import TracebackType

from gnani_coach.providers import events as ev
from gnani_coach.providers.errors import (
    CancelledError,
    InvalidRequestError,
    ProtocolError,
    ProviderError,
)
from gnani_coach.providers.limits import MAX_MESSAGE_BYTES, ProbeBudget
from gnani_coach.providers.redaction import describe_headers
from gnani_coach.providers.transport import (
    ConnectionClosed,
    Transport,
    WebSocketTransport,
    decode_json_message,
    validate_endpoint,
)

PROVIDER = "gnani-tts"
DEFAULT_TTS_URL = "wss://api.vachana.ai/api/v1/tts"

MODEL_V25 = "timbre-v2.5"
MODEL_V30 = "timbre-v3.0"
SUPPORTED_MODELS = (MODEL_V25, MODEL_V30)

#: Documented catalog, transcribed from the voice page read 2026-10-18.
VOICE_CATALOG: dict[str, frozenset[str]] = {
    MODEL_V25: frozenset(
        {
            "Ambuja", "Asmita", "Bhavna", "Brinda", "Chitra", "Deepak",
            "Devika", "Dhruva", "Falak", "Girish", "Hemraj", "Ishaan",
            "Jalaj", "Jwala", "Kaveri", "Kavin", "Kirra", "Lavanya",
            "Lehara", "Mehuli", "Nalini", "Noopur", "Omkar", "Poorvi",
            "Pranav", "Reshma", "Riyaan", "Roopesh", "Saanvi", "Shlok",
            "Suhana", "Trisha", "Trupti", "Urmila", "Varuni", "Vedika",
            "Veera", "Vikrant", "Yashvi", "Yukti", "Zahira", "Zayan",
        }
    ),
    MODEL_V30: frozenset(
        {
            "Avinash", "Chetana", "Devansh", "Kalpana", "Lakshmi", "Prakash",
            "Riyaa", "Shivani", "Shubham", "Tarika", "Vasudha", "Yashraj",
            "Harshad",
        }
    ),
}

#: v2.5 voices have one preferred language each (voice page, 2026-10-18).
V25_PREFERRED_LANGUAGE: dict[str, str] = {
    "Ambuja": "hi-IN", "Asmita": "ta-IN", "Bhavna": "hi-IN", "Brinda": "ta-IN",
    "Chitra": "hi-IN", "Deepak": "hi-IN", "Devika": "en-IN", "Dhruva": "bn-IN",
    "Falak": "gu-IN", "Girish": "en-IN", "Hemraj": "hi-IN", "Ishaan": "mr-IN",
    "Jalaj": "hi-IN", "Jwala": "hi-IN", "Kaveri": "en-IN", "Kavin": "kn-IN",
    "Kirra": "bn-IN", "Lavanya": "te-IN", "Lehara": "te-IN", "Mehuli": "pa-IN",
    "Nalini": "hi-IN", "Noopur": "ta-IN", "Omkar": "hi-IN", "Poorvi": "hi-en",
    "Pranav": "en-IN", "Reshma": "ml-IN", "Riyaan": "ml-IN", "Roopesh": "hi-IN",
    "Saanvi": "kn-IN", "Shlok": "en-IN", "Suhana": "te-IN", "Trisha": "ta-IN",
    "Trupti": "en-IN", "Urmila": "hi-IN", "Varuni": "te-IN", "Vedika": "ta-IN",
    "Veera": "gu-IN", "Vikrant": "hi-IN", "Yashvi": "hi-IN", "Yukti": "te-IN",
    "Zahira": "mr-IN", "Zayan": "pa-IN",
}

#: v2.5 voice -> preferred language, used to validate a pairing locally.
V25_VOICE_LANGUAGE = V25_PREFERRED_LANGUAGE

SUPPORTED_TTS_LANGUAGES = frozenset(
    {
        "auto", "hi-IN", "en-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN",
        "mr-IN", "pa-IN", "bn-IN", "gu-IN", "hi-en",
    }
)

SUPPORTED_ENCODINGS = frozenset(
    {"linear_pcm", "pcm_s16le", "pcm_mulaw", "pcm_alaw", "oggopus"}
)
SUPPORTED_CONTAINERS = frozenset({"wav", "raw", "mp3", "ogg", "mulaw", "alaw"})
SUPPORTED_SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)


@dataclass(frozen=True)
class AudioConfig:
    """Streamed-audio configuration.

    ``container`` defaults to ``raw`` because the documented wav behaviour
    ("WAV file (with header)") does not state whether a header is repeated
    per chunk. A probe that needs wav sets it explicitly and the observed
    header behaviour is recorded by :func:`inspect_container`.
    """

    sample_rate: int = 16000
    num_channels: int = 1
    sample_width: int = 2
    encoding: str = "linear_pcm"
    container: str = "raw"

    def validate(self) -> None:
        if self.sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise InvalidRequestError(
                f"audio_config.sample_rate {self.sample_rate} unsupported"
            )
        if self.num_channels != 1:
            raise InvalidRequestError("this adapter is mono-only")
        if self.sample_width != 2:
            raise InvalidRequestError("only 16-bit samples are handled")
        if self.encoding not in SUPPORTED_ENCODINGS:
            raise InvalidRequestError(f"encoding {self.encoding!r} unsupported")
        if self.container not in SUPPORTED_CONTAINERS:
            raise InvalidRequestError(f"container {self.container!r} unsupported")

    def to_payload(self) -> dict[str, object]:
        return {
            "sample_rate": self.sample_rate,
            "num_channels": self.num_channels,
            "sample_width": self.sample_width,
            "encoding": self.encoding,
            "container": self.container,
        }


@dataclass(frozen=True)
class TtsConfig:
    text: str
    voice: str
    model: str = MODEL_V25
    language: str = "en-IN"
    speed: float = 1.0
    audio: AudioConfig = field(default_factory=AudioConfig)

    def validate(self, catalog_languages: Iterable[str] | None = None) -> None:
        if not self.text or not self.text.strip():
            raise InvalidRequestError("synthesis text must not be empty")
        if len(self.text) > 5000:
            raise InvalidRequestError("synthesis text exceeds the 5000-character bound")
        if self.model not in SUPPORTED_MODELS:
            raise InvalidRequestError(f"model {self.model!r} is not supported")
        if self.language not in SUPPORTED_TTS_LANGUAGES:
            raise InvalidRequestError(f"TTS language {self.language!r} is not supported")
        if catalog_languages is not None and self.language != "auto":
            tts_codes = {
                c for c in catalog_languages if isinstance(c, str) and c.endswith("-IN")
            }
            tts_codes.add("hi-en")
            if self.language not in tts_codes:
                raise InvalidRequestError(
                    f"TTS language {self.language!r} is not in the shared catalog"
                )
        known = VOICE_CATALOG.get(self.model)
        if known is not None and self.voice not in known:
            raise InvalidRequestError(
                f"voice {self.voice!r} is not a documented {self.model} voice"
            )
        if self.model == MODEL_V25 and self.voice in V25_VOICE_LANGUAGE:
            preferred = V25_VOICE_LANGUAGE[self.voice]
            if self.language not in ("auto", preferred):
                raise InvalidRequestError(
                    f"v2.5 voice {self.voice!r} prefers language {preferred!r}"
                )
        if not 0.85 <= self.speed <= 1.15:
            raise InvalidRequestError("speed must be within 0.85-1.15")
        self.audio.validate()

    def to_request(self) -> dict[str, object]:
        return {
            "text": self.text,
            "voice": self.voice,
            "model": self.model,
            "language": self.language,
            "speed": self.speed,
            "audio_config": self.audio.to_payload(),
        }

    def safe_summary(self) -> dict[str, object]:
        return {
            "model": self.model,
            "voice": self.voice,
            "language": self.language,
            "speed": self.speed,
            "audio": self.audio.to_payload(),
            "text_chars": len(self.text),
        }


@dataclass
class TtsResult:
    chunks: list[ev.TtsAudioChunk]
    lifecycle: list[ev.TtsLifecycleEvent]
    completion: ev.TtsCompletionEvent | None
    errors: list[ev.ProviderErrorEvent]
    request_id: str | None
    first_nonempty_chunk_ms: float | None
    total_bytes: int
    total_duration_ms: float | None
    chunk_indexes_seen: list[int]
    out_of_order_indexes: list[int]
    fenced_chunk_count: int
    cancelled_by_consumer: bool
    drained: bool
    connection_closed_to_stop: bool
    container_observation: dict[str, object]
    forwarded: bool

    @property
    def audio(self) -> bytes:
        return b"".join(c.bytes for c in self.chunks if c.status == "observed")


def inspect_container(chunks: list[bytes]) -> dict[str, object]:
    """Report what container/header actually arrived. Never assumes.

    Returns a content-free description: whether a RIFF/WAVE signature was
    observed, where, and whether it appeared more than once (which would
    mean a per-chunk header and would break naive concatenation).
    """
    observations: list[dict[str, object]] = []
    riff_offsets: list[int] = []
    offset = 0
    for index, chunk in enumerate(chunks):
        starts_with_riff = chunk[:4] == b"RIFF" and chunk[8:12] == b"WAVE"
        if starts_with_riff:
            riff_offsets.append(offset)
            header_bytes = 44 if len(chunk) >= 44 and chunk[36:40] == b"data" else 12
            observations.append(
                {
                    "chunk_index": index,
                    "byte_offset": offset,
                    "riff": True,
                    "header_bytes": header_bytes,
                    "payload_bytes": max(0, len(chunk) - header_bytes),
                    "declared_data_bytes": (
                        struct.unpack("<I", chunk[40:44])[0]
                        if len(chunk) >= 44 and chunk[36:40] == b"data"
                        else None
                    ),
                }
            )
        else:
            observations.append(
                {
                    "chunk_index": index,
                    "byte_offset": offset,
                    "riff": False,
                    "header_bytes": 0,
                    "payload_bytes": len(chunk),
                    "declared_data_bytes": None,
                }
            )
        offset += len(chunk)
    return {
        "chunk_count": len(chunks),
        "riff_header_count": len(riff_offsets),
        "repeated_header_per_chunk": len(riff_offsets) > 1,
        "chunks": observations[:16],
        "truncated": len(observations) > 16,
    }


class GnaniTtsSession:
    """One TTS connection, one in-flight synthesis, cancellable consumption."""

    def __init__(
        self,
        config: TtsConfig,
        api_key: str,
        *,
        budget: ProbeBudget | None = None,
        catalog_languages: Iterable[str] | None = None,
        transport: Transport | None = None,
        recv_timeout: float = 30.0,
        url: str = DEFAULT_TTS_URL,
    ) -> None:
        config.validate(catalog_languages)
        if not api_key:
            raise InvalidRequestError("a Gnani API key is required")
        self.config = config
        self.url = url or DEFAULT_TTS_URL
        validate_endpoint(self.url)
        self._api_key = api_key
        self.budget = budget
        self.recv_timeout = recv_timeout

        self.chunks: list[ev.TtsAudioChunk] = []
        self.lifecycle: list[ev.TtsLifecycleEvent] = []
        self.completion: ev.TtsCompletionEvent | None = None
        self.errors: list[ev.ProviderErrorEvent] = []
        self.request_id: str | None = None

        self._transport: Transport | None = transport
        self._owns_transport = transport is None
        self._queue: asyncio.Queue[object] = asyncio.Queue(maxsize=512)
        self._receiver: asyncio.Task[None] | None = None
        self._closed = False
        self._fenced = False
        self._in_flight = False
        self._request_sent_at: float | None = None
        self._first_nonempty_at: float | None = None
        self._indexes: list[int] = []
        self._out_of_order: list[int] = []
        self._max_index: int | None = None
        self._received_count = 0
        self._forwarded_upto = 0
        self._done = asyncio.Event()

    # -- lifecycle -----------------------------------------------------
    async def __aenter__(self) -> GnaniTtsSession:
        await self._connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose(reason="context-exit")

    async def _connect(self) -> None:
        if self.budget is not None:
            self.budget.spend_connection()
            token = self.budget.begin_call(f"{PROVIDER}:connect")
            self.budget.admit_attempt(f"{PROVIDER}:connect", call=token)
        if self._transport is None:
            self._transport = WebSocketTransport(
                self.url, {"X-API-Key-ID": self._api_key, "Content-Type": "application/json"}
            )
            await self._transport.__aenter__()
        self._receiver = asyncio.create_task(
            self._receive_loop(), name="gnani-tts-receive"
        )

    async def aclose(self, *, reason: str = "done") -> None:
        if self._closed:
            return
        self._closed = True
        if self._receiver is not None and not self._receiver.done():
            self._receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._receiver
        transport, self._transport = self._transport, None
        if transport is not None and self._owns_transport:
            with contextlib.suppress(Exception):
                await transport.close()
        self._done.set()

    # -- receive -------------------------------------------------------
    async def _receive_loop(self) -> None:
        transport = self._transport
        if transport is None:
            return
        try:
            while not self._closed:
                try:
                    raw = await transport.recv(timeout=self.recv_timeout)
                except asyncio.TimeoutError:
                    continue
                except ConnectionClosed:
                    self._done.set()
                    return
                except ProviderError as exc:
                    self._queue.put_nowait(("error", exc))
                    self._done.set()
                    return
                self._queue.put_nowait(("message", raw))
        except asyncio.CancelledError:
            raise
        finally:
            self._queue.put_nowait(None)
            self._done.set()

    def _handle(self, raw: str | bytes) -> None:
        message = decode_json_message(raw)
        kind = message["type"]
        now = time.time()

        if kind == "start":
            request_id = message.get("request_id")
            self.request_id = request_id if isinstance(request_id, str) else None
            self.lifecycle.append(
                ev.TtsLifecycleEvent(request_id=self.request_id, received_at=now)
            )
        elif kind == "audio":
            data = message.get("data")
            if not isinstance(data, dict):
                raise ProtocolError("audio message has no 'data' object")
            index = data.get("chunk_index")
            index = index if isinstance(index, int) and not isinstance(index, bool) else None
            is_final = bool(data.get("is_final"))
            try:
                payload = ev.decode_audio_payload(
                    data.get("audio", ""), max_bytes=MAX_MESSAGE_BYTES
                )
            except ValueError as exc:
                raise ProtocolError(f"audio chunk could not be decoded: {exc}") from exc

            status = "observed"
            if self._fenced:
                status = "fenced"
            if index is not None:
                if self._max_index is not None and index <= self._max_index:
                    status = "out_of_order" if status == "observed" else status
                    self._out_of_order.append(index)
                self._max_index = index if self._max_index is None else max(self._max_index, index)
                self._indexes.append(index)

            is_first = False
            if payload and status == "observed" and self._first_nonempty_at is None:
                self._first_nonempty_at = now
                is_first = True
            self.chunks.append(
                ev.TtsAudioChunk(
                    request_id=self.request_id,
                    chunk_index=index,
                    bytes=payload,
                    received_at=now,
                    is_final=is_final,
                    is_first_nonempty=is_first,
                    status=status,  # type: ignore[arg-type]
                )
            )
        elif kind == "complete":
            data = message.get("data")
            data = data if isinstance(data, dict) else {}
            index = data.get("chunk_index")
            self.completion = ev.TtsCompletionEvent(
                request_id=self.request_id,
                chunk_index=index if isinstance(index, int) and not isinstance(index, bool) else None,
                received_at=now,
                total_bytes=sum(len(c.bytes) for c in self.chunks),
            )
            self._in_flight = False
            self._done.set()
        elif kind == "error":
            from gnani_coach.providers.redaction import redact

            self.errors.append(
                ev.ProviderErrorEvent(
                    provider=PROVIDER,
                    message=redact(str(message.get("message", "")), max_length=200),
                    server_timestamp=None,
                    received_at=now,
                )
            )
            self._in_flight = False
            self._done.set()
        else:
            raise ProtocolError(f"unknown TTS message type {kind!r}")

    # -- request -------------------------------------------------------
    async def synthesize(
        self,
        *,
        forward: object = None,
        cancel_after_chunks: int | None = None,
        close_on_cancel: bool = False,
        idle_timeout_ms: int | None = None,
    ) -> TtsResult:
        """Run one synthesis and collect the chunks.

        ``forward`` is an optional ``async (chunk: bytes) -> None`` consumer.
        ``cancel_after_chunks`` fences consumption after N chunks, which is
        how the probe exercises cancellation without inventing a provider
        cancel frame. ``close_on_cancel`` additionally closes the
        connection, which is the only provider-side stop available.

        Returns a :class:`TtsResult`. A fenced chunk is recorded with its
        payload but is **not** forwarded to ``forward``.
        """
        if self._closed:
            raise CancelledError("session is closed", provider=PROVIDER)
        if self._transport is None:
            # The port wrapper opens a session and then synthesises without
            # entering the async context. Connect lazily on first use so a
            # live call does not fail with "session is closed".
            await self._connect()
        if self._in_flight:
            raise InvalidRequestError(
                "one synthesis request at a time per connection (documented)"
            )
        if self.budget is not None:
            token = self.budget.begin_call(f"{PROVIDER}:synthesize")
            self.budget.admit_attempt(f"{PROVIDER}:synthesize", call=token)

        self._in_flight = True
        self._done.clear()
        self._request_sent_at = time.time()
        await self._transport.send(json.dumps(self.config.to_request()))

        forwarded_any = False
        loop = asyncio.get_running_loop()
        wait_ms = idle_timeout_ms or max(500, int(self.recv_timeout * 1000))
        deadline = loop.time() + wait_ms / 1000.0

        while True:
            remaining = max(0.0, deadline - loop.time())
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if item is None:
                break
            kind, payload = item  # type: ignore[misc]
            if kind == "message":
                self._handle(payload)  # type: ignore[arg-type]
            elif kind == "error":
                exc = payload if isinstance(payload, BaseException) else ProtocolError("unknown")
                raise exc

            forwarded = False
            new_chunks = self.chunks[self._forwarded_upto :]
            self._forwarded_upto = len(self.chunks)
            for chunk in new_chunks:
                if chunk.status != "observed" or not chunk.bytes:
                    continue
                # A received non-empty chunk counts toward the cancellation
                # budget whether or not a consumer callback was attached:
                # "stop consuming after N chunks" must not depend on who
                # was listening.
                self._received_count += 1
                if forward is not None:
                    await forward(chunk.bytes)  # type: ignore[operator]
                    forwarded = True
            if forwarded:
                forwarded_any = True

            if (
                cancel_after_chunks is not None
                and self._received_count >= cancel_after_chunks
                and not self._fenced
            ):
                self._fenced = True
                if close_on_cancel:
                    await self.aclose(reason="cancelled-and-closed")
                    break

            if self.completion is not None or self.errors:
                break
            if self._fenced and close_on_cancel:
                break

        await self.aclose(reason="synthesize-complete")

        observed = [c for c in self.chunks if c.status == "observed" and c.bytes]
        first_ms = None
        if self._first_nonempty_at is not None and self._request_sent_at is not None:
            first_ms = round((self._first_nonempty_at - self._request_sent_at) * 1000.0, 2)

        duration_ms = None
        rate = self.config.audio.sample_rate
        channels = self.config.audio.num_channels
        width = self.config.audio.sample_width
        if observed and self.config.audio.container == "raw":
            payload_bytes = sum(len(c.bytes) for c in observed)
            duration_ms = round(
                payload_bytes / float(rate * channels * width) * 1000.0, 2
            )

        return TtsResult(
            chunks=list(self.chunks),
            lifecycle=list(self.lifecycle),
            completion=self.completion,
            errors=list(self.errors),
            request_id=self.request_id,
            first_nonempty_chunk_ms=first_ms,
            total_bytes=sum(len(c.bytes) for c in observed),
            total_duration_ms=duration_ms,
            chunk_indexes_seen=list(self._indexes),
            out_of_order_indexes=list(self._out_of_order),
            fenced_chunk_count=sum(1 for c in self.chunks if c.status == "fenced"),
            cancelled_by_consumer=self._fenced,
            drained=self._fenced and not self._closed,
            connection_closed_to_stop=self._fenced,
            container_observation=inspect_container([c.bytes for c in observed]),
            forwarded=forwarded_any,
        )

    # -- explicit cancellation API -------------------------------------
    async def cancel_consumption(self) -> None:
        """Fence the consumer. Provider work is **not** cancelled."""
        self._fenced = True

    async def drain(self) -> TtsResult:
        """Safely finish the in-flight request without forwarding audio."""
        self._fenced = True
        return await self.synthesize(forward=None)


def headers_for(api_key: str) -> dict[str, str]:
    return {"X-API-Key-ID": api_key, "Content-Type": "application/json"}


def safe_connection_summary(api_key: str) -> dict[str, object]:
    return {
        "url": DEFAULT_TTS_URL,
        "headers": describe_headers(headers_for(api_key)),
    }
