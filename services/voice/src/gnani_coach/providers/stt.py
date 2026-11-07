"""Gnani realtime speech-to-text adapter (Prisma).

Primary documentation read 2026-10-18:
https://docs.gnani.ai/api/STT/stt-websocket

Contract implemented here
-------------------------
* ``wss://api.vachana.ai/stt/v3/stream`` with all configuration in
  WebSocket upgrade headers (``x-api-key-id``, ``lang_code``,
  ``x-sample-rate``, ``x-format``, and the five VAD headers).
* ``x-format: verbatim`` by default so spoken form is preserved for
  baseline analysis. Substituting is **off**: ``x-enable-substitution`` is
  not sent. Word boosting is never sent from a fixture whose expected text
  is known — biasing the recogniser with the expected answer would
  invalidate the accuracy measurement.
* Exactly 1,024-byte raw mono signed 16-bit little-endian PCM frames,
  paced at the real sample rate (32 ms at 16 kHz). A WAV header is never
  sent as a frame.

Two facts from the docs that shape this adapter:

* "The Python SDK does not currently expose VAD tuning. Use a raw
  WebSocket client, as above, if you need these headers." This is why the
  adapter speaks raw WebSocket rather than using ``gnani-vachana``. The
  SDK package is deliberately **not** installed.
* Every closed VAD segment becomes exactly one ``transcript`` message, and
  a segment ending does not prove the speaker finished their thought.
  :meth:`GnaniSttSession.iter_transcripts` therefore yields *segments*, and
  :attr:`GnaniSttSession.transcript_segments` never claims to be a turn.

What this adapter deliberately does not do
------------------------------------------
* No REST fallback and no substitute recogniser. A failure is a failure.
* No word-level timing. The provider documents none, and this adapter
  never derives word positions from ``latency`` or ``audio_duration_ms``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field
from types import TracebackType

from gnani_coach.providers import events as ev
from gnani_coach.providers.errors import (
    CancelledError,
    InvalidRequestError,
    ProtocolError,
    ProviderError,
)
from gnani_coach.providers.limits import ProbeBudget
from gnani_coach.providers.pcm import (
    FRAME_BYTES,
    STT_SAMPLE_RATES,
    SampleClock,
    frame_duration_ms,
    frames as pcm_frames,
    pad_to_frame,
    pcm_seconds,
)
from gnani_coach.providers.redaction import describe_headers
from gnani_coach.providers.transport import (
    ConnectionClosed,
    Transport,
    WebSocketTransport,
    decode_json_message,
    validate_endpoint,
)

PROVIDER = "gnani-stt"
DEFAULT_STT_URL = "wss://api.vachana.ai/stt/v3/stream"
FORMAT_VERBATIM = "verbatim"
FORMAT_TRANSCRIBE = "transcribe"

#: Word boosting, as documented on the realtime STT page (read
#: 2026-10-20, https://docs.gnani.ai/api/STT/stt-websocket):
#:
#: * up to **100** words, each a **single word of letters only**;
#: * the score must be one of ``0.0``, ``0.5``, ``1.0``, ``1.5``, ``2.0``;
#: * boosting requires ``x-format: verbatim`` (boost words are spoken-form
#:   tokens);
#: * **invalid boosting input is silently skipped** — the connection is
#:   never rejected and no error is returned. A skipped boost looks
#:   exactly like a boost that had no effect, so the rules are checked
#:   here instead of being discovered later as a silent null result.
BIAS_SCORES: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0)
MAX_BIAS_WORDS = 100


@dataclass(frozen=True)
class VadSettings:
    """The five documented VAD headers.

    These are fixed for the life of a connection: changing them requires a
    reconnect with new headers. Defaults mirror the documented values; a
    probe that changes them must record that it did.
    """

    threshold: float = 0.7
    min_silence_ms: int = 500
    min_speech_ms: int = 100
    min_segment_ms: int = 120
    max_speech_s: float | None = None

    def validate(self) -> None:
        if not 0.0 <= self.threshold <= 1.0:
            raise InvalidRequestError("x-vad-threshold must be within 0.0-1.0")
        if not 100 <= self.min_silence_ms <= 2000:
            raise InvalidRequestError("x-min-silence-ms must be within 100-2000")
        if not 50 <= self.min_speech_ms <= 2000:
            raise InvalidRequestError("x-min-speech-ms must be within 50-2000")
        if not 100 <= self.min_segment_ms <= 1000:
            raise InvalidRequestError("x-min-segment-ms must be within 100-1000")
        if self.max_speech_s is not None and not 5.0 <= self.max_speech_s <= 120.0:
            raise InvalidRequestError("x-max-speech-s must be within 5.0-120.0")


@dataclass(frozen=True)
class SttConfig:
    """Connection configuration. Credential is never logged."""

    language_code: str
    sample_rate: int = 16000
    output_format: str = FORMAT_VERBATIM
    vad: VadSettings = field(default_factory=VadSettings)
    enable_substitution: bool = False
    bias_words: tuple[str, ...] = ()
    bias_score: float = 0.0
    url: str = DEFAULT_STT_URL

    def validate(self, catalog_codes: Iterable[str]) -> None:
        if self.language_code not in set(catalog_codes):
            raise InvalidRequestError(
                f"language_code {self.language_code!r} is not in the shared catalog"
            )
        if self.sample_rate not in STT_SAMPLE_RATES:
            raise InvalidRequestError(
                f"x-sample-rate {self.sample_rate} is not one of {STT_SAMPLE_RATES}"
            )
        if self.output_format not in (FORMAT_VERBATIM, FORMAT_TRANSCRIBE):
            raise InvalidRequestError("x-format must be verbatim or transcribe")
        if self.bias_words and self.bias_score <= 0:
            raise InvalidRequestError("word boosting requires a positive x-bias-score")
        if len(self.bias_words) > MAX_BIAS_WORDS:
            raise InvalidRequestError(
                f"word boosting accepts at most {MAX_BIAS_WORDS} words"
            )
        if self.bias_words:
            # The provider skips invalid boosting silently, so an invalid
            # list would be indistinguishable from "boosting did not help".
            if self.output_format != FORMAT_VERBATIM:
                raise InvalidRequestError(
                    "word boosting requires x-format: verbatim; boost words are "
                    "spoken-form tokens"
                )
            if self.bias_score not in BIAS_SCORES:
                raise InvalidRequestError(
                    f"x-bias-score must be one of {BIAS_SCORES}"
                )
            for word in self.bias_words:
                if not word or not word.isalpha() or any(ch.isspace() for ch in word):
                    raise InvalidRequestError(
                        "each word-boosting entry must be a single word of letters only"
                    )
        self.vad.validate()
        validate_endpoint(self.url)

    def headers(self, api_key: str) -> dict[str, str]:
        """Build upgrade headers. The key is attached here and nowhere else.

        The endpoint is re-validated at this point, not only in
        :meth:`validate`, so a credential can never be attached to a host
        that has been changed after construction.
        """
        validate_endpoint(self.url)
        headers = {
            "x-api-key-id": api_key,
            "lang_code": self.language_code,
            "x-sample-rate": str(self.sample_rate),
            "x-format": self.output_format,
            "x-vad-threshold": f"{self.vad.threshold:g}",
            "x-min-silence-ms": str(self.vad.min_silence_ms),
            "x-min-speech-ms": str(self.vad.min_speech_ms),
            "x-min-segment-ms": str(self.vad.min_segment_ms),
        }
        if self.vad.max_speech_s is not None:
            headers["x-max-speech-s"] = f"{self.vad.max_speech_s:g}"
        if self.enable_substitution:
            raise InvalidRequestError(
                "substitution must stay off for baseline spoken-form analysis"
            )
        if self.bias_words:
            headers["x-bias-list"] = json.dumps(list(self.bias_words))
            # The documented scores are 0.0, 0.5, 1.0, 1.5 and 2.0. The
            # value is written with one decimal so the header carries the
            # documented spelling exactly: an unrecognised score would make
            # the provider skip boosting, silently.
            headers["x-bias-score"] = f"{self.bias_score:.1f}"
        return headers

    def safe_summary(self, api_key: str) -> dict[str, object]:
        return {
            "url": self.url,
            "headers": describe_headers(self.headers(api_key)),
            "frame_bytes": FRAME_BYTES,
            "frame_duration_ms": round(frame_duration_ms(self.sample_rate), 3),
            "output_format": self.output_format,
            "vad": {
                "threshold": self.vad.threshold,
                "min_silence_ms": self.vad.min_silence_ms,
                "min_speech_ms": self.vad.min_speech_ms,
                "min_segment_ms": self.vad.min_segment_ms,
                "max_speech_s": self.vad.max_speech_s,
                "note": "VAD headers are fixed for the life of the connection",
            },
            "substitution": self.enable_substitution,
            "bias_words_count": len(self.bias_words),
            "bias_score": self.bias_score if self.bias_words else 0.0,
            "bias_words": list(self.bias_words),
        }


@dataclass
class SttResult:
    """Outcome of one STT run, with the sample clock preserved."""

    transcripts: list[ev.SttTranscriptEvent]
    processing_count: int
    sample_clock: SampleClock
    server_config: dict[str, object]
    errors: list[ev.ProviderErrorEvent]
    duplicate_segment_ids: list[str] = field(default_factory=list)
    out_of_order_indexes: list[int] = field(default_factory=list)
    #: Well-formed frames of an unmodelled type, e.g. `speech_start`.
    unrecognized_frames: list[ev.UnrecognizedFrame] = field(default_factory=list)
    submitted_audio_seconds: float = 0.0
    end_padding_ms: int = 0
    frames_sent: int = 0
    closed_cleanly: bool = False

    @property
    def text(self) -> str:
        """Concatenated recognised text, in observed segment order."""
        return " ".join(t.text for t in self.transcripts if t.text).strip()

    @property
    def segment_count(self) -> int:
        return len(self.transcripts)


class GnaniSttSession:
    """One STT connection: send and receive concurrently.

    Usage::

        async with GnaniSttSession(config, api_key, budget=budget) as session:
            async for transcript in session.iter_transcripts():
                ...
            result = await session.stream_pcm(raw_pcm)

    Concurrency is real: a receive task runs for the whole session so that
    transcripts are observed while audio is still being written. Reading
    sequentially after the socket is drained would lose nothing here (the
    server buffers), but it would misrepresent the protocol and would not
    exercise the endpointing behaviour the product depends on.
    """

    def __init__(
        self,
        config: SttConfig,
        api_key: str,
        *,
        budget: ProbeBudget | None = None,
        catalog_codes: Iterable[str] | None = None,
        transport: Transport | None = None,
        recv_timeout: float = 30.0,
        idle_grace_ms: int = 1500,
    ) -> None:
        config.validate(catalog_codes or _default_codes())
        if not api_key:
            raise InvalidRequestError("a Gnani API key is required")
        self.config = config
        self._api_key = api_key
        self.budget = budget
        self.clock = SampleClock(sample_rate=config.sample_rate)
        self.recv_timeout = recv_timeout
        self.idle_grace_ms = idle_grace_ms

        self.transcripts: list[ev.SttTranscriptEvent] = []
        self.errors: list[ev.ProviderErrorEvent] = []
        self.server_config: dict[str, object] = {}
        self.processing_count: int = 0
        self.duplicate_segment_ids: list[str] = []
        self.out_of_order_indexes: list[int] = []
        self.unrecognized_frames: list[ev.UnrecognizedFrame] = []
        self._pending_error: ProviderError | None = None

        self._transport: Transport | None = transport
        self._owns_transport = transport is None
        self._queue: asyncio.Queue[object] = asyncio.Queue(maxsize=512)
        self._receiver: asyncio.Task[None] | None = None
        self._connected_event: asyncio.Event = asyncio.Event()
        self._closed = False
        self._fenced = False
        self._seen_ids: set[str] = set()
        self._max_index: int | None = None
        self._stop_reason = "not-started"

    # -- lifecycle -----------------------------------------------------
    async def __aenter__(self) -> GnaniSttSession:
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
            # Order matters: the connection is charged first, so a refused
            # budget never leaves a half-open transport behind.
            self.budget.spend_connection()
            token = self.budget.begin_call(f"{PROVIDER}:connect")
            self.budget.admit_attempt(f"{PROVIDER}:connect", call=token)
        if self._transport is None:
            self._transport = WebSocketTransport(
                self.config.url, self.config.headers(self._api_key)
            )
            await self._transport.__aenter__()
        self._receiver = asyncio.create_task(
            self._receive_loop(), name="gnani-stt-receive"
        )
        # The server sends `connected` immediately; wait for it so a
        # handshake rejection surfaces as a category, not as silence.
        connected = asyncio.create_task(self._connected_event.wait())
        waiter = asyncio.create_task(self._queue.get())
        done, _pending = await asyncio.wait(
            {connected, waiter}, timeout=self.recv_timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            connected.cancel()
            waiter.cancel()
            await self.aclose(reason="no-connected-frame")
            raise ProtocolError(
                "provider did not send a 'connected' frame after the handshake"
            )
        connected.cancel()
        waiter.cancel()
        item = waiter.result() if waiter in done and waiter.result() is not None else None
        if isinstance(item, tuple) and item[0] == "error":
            await self.aclose(reason="handshake-error")
            raise self._pending_error or ProtocolError("handshake failed")
        if isinstance(item, tuple) and item[0] in ("closed", None):
            await self.aclose(reason="handshake-closed")
            raise ProtocolError("connection closed before a 'connected' frame arrived")
        if not self._connected_event.is_set():
            await self.aclose(reason="no-connected-frame")
            raise ProtocolError(
                "provider did not send a 'connected' frame after the handshake"
            )

    async def aclose(self, *, reason: str = "done") -> None:
        """Close exactly once. Safe to call from cancellation paths."""
        if self._closed:
            return
        self._closed = True
        self._stop_reason = reason
        if self._receiver is not None and not self._receiver.done():
            self._receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._receiver
        transport, self._transport = self._transport, None
        if transport is not None and self._owns_transport:
            with contextlib.suppress(Exception):
                await transport.close()
        # Wake anyone waiting on recv.
        self._queue.put_nowait(None)

    async def fence(self) -> None:
        """Stop consuming. The provider connection is left to the caller.

        This is *stopping consumption*, not cancelling provider computation:
        nothing in the reviewed docs cancels or refunds a synthesis or an
        in-flight recognition.
        """
        self._fenced = True
        await self.aclose(reason="fenced")

    # -- receive -------------------------------------------------------
    async def _receive_loop(self) -> None:
        """Parse and apply every inbound frame as it arrives.

        Control frames (`connected`, `settings_updated`, `error`) and the
        `processing` acknowledgement are applied **here**, immediately, and
        a notice is queued for the caller. Transcript frames are applied
        here too, so ordering and the sample-clock anchor are captured at
        arrival time; the queue exists so a caller can also iterate them
        live, not so that parsing can be deferred.

        Deferring parsing would deadlock the handshake: `connected` arrives
        before ``stream_pcm`` starts draining, so nothing would set the
        event that :meth:`_connect` is waiting on.
        """
        transport = self._transport
        if transport is None:
            return
        try:
            while not self._closed:
                try:
                    raw = await transport.recv(timeout=self.recv_timeout)
                except asyncio.TimeoutError:
                    if self._closed:
                        return
                    self._queue.put_nowait(("idle", None))
                    continue
                except ConnectionClosed:
                    self._queue.put_nowait(("closed", None))
                    return
                except ProviderError as exc:
                    self._pending_error = exc
                    self._queue.put_nowait(("error", None))
                    return
                try:
                    notice = self._handle(raw)
                except ProviderError as exc:
                    self._pending_error = exc
                    self._queue.put_nowait(("error", None))
                    return
                self._queue.put_nowait((notice, None))
        except asyncio.CancelledError:
            raise
        finally:
            self._queue.put_nowait(None)

    def _handle(self, raw: str | bytes) -> str:
        """Apply one provider frame. Returns the queue notice name."""
        message = decode_json_message(raw)
        kind = message["type"]
        now = time.time()

        if kind == "connected":
            config = message.get("config")
            self.server_config = dict(config) if isinstance(config, dict) else {}
            self._connected_event.set()
        elif kind == "processing":
            self.processing_count += 1
        elif kind == "transcript":
            self._record_transcript(message, now)
            return "transcript"
        elif kind == "settings_updated":
            config = message.get("config")
            if isinstance(config, dict):
                self.server_config.update(config)
        elif kind == "error":
            from gnani_coach.providers.redaction import redact

            self.errors.append(
                ev.ProviderErrorEvent(
                    provider=PROVIDER,
                    message=redact(str(message.get("message", "")), max_length=200),
                    server_timestamp=_as_str(message.get("timestamp")),
                    received_at=now,
                )
            )
        else:
            # A well-formed frame with a `type` this adapter does not know.
            #
            # Observed against the live endpoint on 2026-10-18: the server
            # emits `speech_start`, which is **not** in the published
            # message list. Treating protocol drift as a hard failure would
            # make the probe unusable against the real service; ignoring it
            # silently would hide the drift. It is therefore recorded as a
            # first-class observation and surfaced in every result.
            #
            # A *structurally* invalid frame (not JSON, or no string `type`)
            # is still a ProtocolError above — this branch is only reached
            # by a well-formed frame of an unrecognised kind.
            self.unrecognized_frames.append(
                ev.UnrecognizedFrame(
                    provider=PROVIDER,
                    message_type=kind,
                    keys=sorted(str(key) for key in message)[:12],
                    received_at=now,
                    note="present in live traffic; absent from the documented message list",
                )
            )
        # `provider_error` is a distinct notice name from the internal
        # `error` used by the receive loop, so a provider error frame is
        # recorded and surfaced, never mistaken for a receiver failure.
        return "provider_error" if kind == "error" else kind

    def _record_transcript(self, message: dict, now: float) -> None:
        segment_id = _as_str(message.get("segment_id"))
        index = message.get("segment_index")
        index = index if isinstance(index, int) else None
        text = message.get("text")
        text = text if isinstance(text, str) else ""

        status: str = "observed"
        if segment_id is not None:
            if segment_id in self._seen_ids:
                status = "duplicate"
                self.duplicate_segment_ids.append(segment_id)
            else:
                self._seen_ids.add(segment_id)
        if index is not None and self._max_index is not None and index <= self._max_index:
            status = "out_of_order"
            self.out_of_order_indexes.append(index)
        if index is not None:
            self._max_index = index if self._max_index is None else max(self._max_index, index)

        self.transcripts.append(
            ev.SttTranscriptEvent(
                segment_id=segment_id,
                segment_index=index,
                text=text,
                audio_duration_ms=_as_int(message.get("audio_duration_ms")),
                latency_ms=_as_int(message.get("latency")),
                server_timestamp=_as_str(message.get("timestamp")),
                received_at=now,
                learner_clock_samples=self.clock.submitted_samples,
                status=status,  # type: ignore[arg-type]
            )
        )

    # -- send ----------------------------------------------------------
    async def stream_pcm(
        self,
        raw_pcm: bytes,
        *,
        pad_tail: bool = True,
        real_time: bool = True,
        idle_grace_ms: int | None = None,
        trailing_silence_ms: int = 800,
    ) -> SttResult:
        """Submit raw PCM and collect the transcripts it produces.

        ``raw_pcm`` must already be de-headered signed 16-bit LE mono at the
        connection's sample rate. ``pad_tail`` adds the zero padding needed
        to reach a whole frame.

        ``trailing_silence_ms`` appends deliberate silence after the audio.
        The server's VAD closes a segment on *silence*, and it cannot know a
        stream has ended until the socket closes — without trailing silence
        the final segment simply never closes and no transcript is ever
        emitted. That silence is padding, not learner speech: it is recorded
        on the clock as padding and is excluded from the genuine span.
        """
        if self._transport is None or self._closed:
            raise CancelledError("session is closed", provider=PROVIDER)

        frame_ms = frame_duration_ms(self.config.sample_rate)
        grace = self.idle_grace_ms if idle_grace_ms is None else idle_grace_ms
        tail_bytes = (
            b"\x00" * int(round(trailing_silence_ms * self.config.sample_rate / 1000.0)) * 2
            if trailing_silence_ms > 0
            else b""
        )
        genuine_bytes = len(raw_pcm)
        combined = raw_pcm + tail_bytes
        pcm, pad_bytes = pad_to_frame(combined)
        genuine_samples_total = genuine_bytes // 2

        if self.budget is not None:
            # ``pcm`` here is the *framed submitted* audio: learner speech
            # plus the trailing silence that closes the provider's VAD
            # window, plus the zero pad to a frame boundary. That is what
            # goes on the wire, so that is what the plan must be sized on.
            submitted_seconds = pcm_seconds(pcm, self.config.sample_rate)
            self.budget.check_plan(1, submitted_seconds)
            token = self.budget.begin_call(f"{PROVIDER}:session")
            self.budget.admit_attempt(f"{PROVIDER}:session", call=token)
            self.budget.spend_audio(submitted_seconds)
        self.clock.started_at = time.time()
        self.processing_count = 0
        sent_frames = 0

        async def _pump() -> None:
            nonlocal sent_frames
            counted = 0
            try:
                for index, chunk in enumerate(
                    pcm_frames(pcm, sample_rate=self.config.sample_rate)
                ):
                    if self._closed or self._fenced:
                        return
                    await self._transport.send(chunk)  # type: ignore[union-attr]
                    sent_frames = index + 1
                    # Split the frame's samples between genuine audio and
                    # zero padding, so the clock never reports padding as
                    # learner speech span.
                    frame_samples = len(chunk) // 2
                    genuine_here = max(0, min(frame_samples, genuine_samples_total - counted))
                    counted += genuine_here
                    self.clock.advance(genuine_here)
                    if frame_samples - genuine_here:
                        self.clock.add_padding(frame_samples - genuine_here)
                    if real_time:
                        await asyncio.sleep(frame_ms / 1000.0)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, ProviderError) as exc:
                self._pending_error = exc
                self._queue.put_nowait(("error", None))

        pump = asyncio.create_task(_pump(), name="gnani-stt-pump")
        # Sending must complete before we start waiting for the stream to
        # go quiet. Draining concurrently with sending would end the wait on
        # the first idle gap and truncate the audio mid-utterance.
        with contextlib.suppress(asyncio.CancelledError):
            await pump
        if self._pending_error is not None:
            error = self._pending_error
            await self.aclose(reason="send-failed")
            raise error
        # Now let the last VAD window close and the transcript arrive.
        await self._drain(until_idle_ms=grace)

        await self.aclose(reason="stream-complete")
        self.clock.finished_at = time.time()
        return SttResult(
            transcripts=list(self.transcripts),
            processing_count=self.processing_count,
            sample_clock=self.clock,
            server_config=dict(self.server_config),
            errors=list(self.errors),
            duplicate_segment_ids=list(self.duplicate_segment_ids),
            out_of_order_indexes=list(self.out_of_order_indexes),
            unrecognized_frames=list(self.unrecognized_frames),
            submitted_audio_seconds=pcm_seconds(pcm, self.config.sample_rate),
            end_padding_ms=int(round(pad_bytes * 1000.0 / (self.config.sample_rate * 2))),
            frames_sent=sent_frames,
            closed_cleanly=True,
        )

    async def send_control_frame(self, payload: dict) -> None:
        """Send a documented client control frame (``update_settings``)."""
        if self._transport is None or self._closed:
            raise CancelledError("session is closed", provider=PROVIDER)
        await self._transport.send(json.dumps(payload))

    async def _drain(self, *, until_idle_ms: int) -> None:
        """Wait for the stream to go quiet for ``until_idle_ms``.

        Frames are applied by the receiver task; this only observes
        notices to decide when the stream has settled.
        """
        loop = asyncio.get_running_loop()
        deadline = None
        while True:
            timeout = until_idle_ms / 1000.0 if deadline is None else max(
                0.0, deadline - loop.time()
            )
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return
            if item is None:
                return
            kind, _payload = item  # type: ignore[misc]
            if kind == "transcript":
                deadline = loop.time() + until_idle_ms / 1000.0
            elif kind == "idle":
                return
            elif kind == "closed":
                return
            elif kind == "error":
                # The receiver stores the exception on the session so a
                # later await can raise it; re-surface it here.
                raise self._pending_error or ProtocolError("receiver failed")

    # -- streaming iterator -------------------------------------------
    async def iter_transcripts(self) -> AsyncIterator[ev.SttTranscriptEvent]:
        """Yield transcripts as they arrive, for a live microphone path."""
        seen = 0
        while not self._closed:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self.recv_timeout)
            except asyncio.TimeoutError:
                continue
            if item is None:
                return
            kind, _payload = item  # type: ignore[misc]
            if kind == "transcript":
                while seen < len(self.transcripts):
                    event = self.transcripts[seen]
                    seen += 1
                    yield event
            elif kind == "closed":
                return
            elif kind == "error":
                raise self._pending_error or ProtocolError("receiver failed")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_CATALOG_CODES: frozenset[str] = frozenset(
    {
        "bn-IN",
        "en-IN",
        "gu-IN",
        "hi-IN",
        "kn-IN",
        "ml-IN",
        "mr-IN",
        "pa-IN",
        "ta-IN",
        "te-IN",
    }
)


def _default_codes() -> frozenset[str]:
    return _CATALOG_CODES


def catalog_codes() -> frozenset[str]:
    """The ten documented STT language codes."""
    return _CATALOG_CODES


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def build_config(
    language_code: str,
    *,
    sample_rate: int = 16000,
    vad: VadSettings | None = None,
    output_format: str = FORMAT_VERBATIM,
    bias_words: tuple[str, ...] = (),
    bias_score: float = 0.0,
) -> SttConfig:
    """Build a config: verbatim, substitution off, no word bias by default.

    ``output_format`` and the word-boosting arguments exist for the
    bounded filler experiment, which needs to compare ``verbatim`` with
    ``transcribe`` and to ask the recogniser to prefer ``um``/``uh``.
    The baseline call is unchanged: verbatim, no bias.
    """
    return SttConfig(
        language_code=language_code,
        sample_rate=sample_rate,
        output_format=output_format,
        vad=vad or VadSettings(),
        enable_substitution=False,
        bias_words=tuple(bias_words),
        bias_score=bias_score,
    )


TransportFactory = Callable[[str, dict[str, str]], Transport]
