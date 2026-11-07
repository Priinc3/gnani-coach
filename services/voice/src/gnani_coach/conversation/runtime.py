"""The call runtime: the state machine behind ``/ws/call``.

States
------

``connecting`` → ``listening`` → ``thinking`` → ``speaking`` → ``coaching``

* **connecting** — the socket is accepted; the ``start`` event has not
  arrived yet.
* **listening** — the learner's turn is open.
* **thinking** — the reasoning model is producing the coach's line.
* **speaking** — the synthesised audio is being sent.
* **coaching** — the round feedback is being delivered.

The rules of the loop are **the application's own**. The model never
changes them: it produces a line of text and nothing else. The turn
policy, the round size, the interruption rule and the metrics are all
decided here.

What the runtime guarantees
---------------------------

* the first message must be a valid ``start`` event; a malformed one is
  refused with the frozen error shape and a policy-violation close, and
  an oversized one with a message-too-big close;
* a binary frame is exactly 1,024 bytes, and the learner-audio sample
  clock advances only by real frames;
* every envelope carries a monotonic per-connection ``sequence``;
* a heartbeat goes out every 15 seconds when nothing else was sent;
* an idle connection is closed after 90 seconds, and a call is closed
  cleanly at the 600-second cap;
* a late reply or late audio of a fenced turn is **never** sent;
* the learner-only audio stream reaches the analysis, and the coach's
  audio never does;
* the logs carry ids, counts and durations only.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from gnani_coach.conversation import errors as call_errors
from gnani_coach.conversation.audio import pcm_duration_ms, wav_bytes
from gnani_coach.conversation.config import (
    BINARY_FRAME_BYTES,
    DEFAULT_MIN_TURN_WORDS,
    DEFAULT_TURN_HOLD_MS,
    ENDPOINTING_HANGOVER_MS,
    HEARTBEAT_INTERVAL_S,
    IDLE_TIMEOUT_S,
    MAX_CALL_SECONDS,
    MAX_JSON_MESSAGE_BYTES,
    MAX_REPLY_CHARS,
    MAX_TRANSCRIPT_CHARS,
    MAX_TURN_AUDIO_BYTES,
    MAX_TURN_MS,
    MUTE_HOLD_EXTENSION_MS,
    SEGMENT_GRACE_MS,
    START_DEADLINE_S,
)
from gnani_coach.conversation.envelope import (
    new_connection_id,
    new_round_id,
    new_session_id,
    new_turn_id,
    server_envelope,
    utc_now_iso,
)
from gnani_coach.conversation.feedback import (
    RoundFacts,
    facts_only_message,
    parse_feedback,
    validate_feedback,
)
from gnani_coach.conversation.metrics import (
    DurableMetrics,
    TurnMetrics,
    derive_speech_active_ms,
    validate_durable_metrics,
)
from gnani_coach.conversation.prompts import (
    build_feedback_instruction,
    build_turn_instruction,
    sanitize_reply,
    sanitize_transcript,
)
from gnani_coach.conversation.recognition import RecognitionStream
from gnani_coach.conversation.turns import Endpointing, LearnerTurn, turn_is_complete
from gnani_coach.conversation.validation import (
    InvalidStart,
    StartRequest,
    validate_start_envelope,
)
from gnani_coach.observability.latency import registry as latency_registry
from gnani_coach.ports.analysis import AnalysisPort, AnalysisRequest, AnalysisResult
from gnani_coach.ports.identity import IdentityPort
from gnani_coach.ports.reasoning import ReasoningPort, ReasoningRequest
from gnani_coach.ports.speech_to_text import SttOpenRequest
from gnani_coach.ports.text_to_speech import SpeechChunk, TextToSpeechPort, TtsOpenRequest
from gnani_coach.ports.types import ConnectionId, RoundId, SessionId, TurnId

LOGGER = logging.getLogger("gnani_coach.conversation")

#: The frame duration at 16 kHz mono s16le: 512 samples.
FRAME_DURATION_MS = 32

#: The maximum number of queued inbound events. The queue applies
#: backpressure to the socket instead of growing without bound.
EVENT_QUEUE_SIZE = 256

#: The notice a caller sees when the token could not be confirmed. The
#: call continues as a guest; nothing is saved. It is carried in the
#: frozen ``status`` payload's optional ``detail`` (bounded at 200 by the
#: contract), with a ``notice:`` prefix so the interface can tell a
#: learner-facing notice from an ordinary status detail.
NOTICE_PREFIX = "notice:"
AUTH_NOTICE = (
    "Your sign-in could not be confirmed, so this call continues as a guest "
    "and nothing will be saved."
)
NOT_SAVED_NOTICE = (
    "This session was not saved. The call ended normally, but the storage "
    "service was not available."
)
#: The metrics can be written while the audio cannot. Saying "not saved"
#: there would be false, and saying nothing would let the learner believe
#: the recording exists, so the audio failure has its own sentence.
RECORDING_NOT_SAVED_NOTICE = (
    "The recording could not be saved, so this session has no audio. "
    "Your practice metrics were saved."
)


class CallEnded(Exception):
    """The call ended cleanly. Not a failure, and not an error envelope."""


class CallFailure(Exception):
    """A failure that ends the call.

    ``failure`` is the mapped error shape; ``close_code`` is the
    WebSocket close code.
    """

    def __init__(self, failure: call_errors.Failure, *, close_code: int = 1000) -> None:
        super().__init__(failure.code)
        self.failure = failure
        self.close_code = close_code


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


@dataclass
class FrameEvent:
    """One binary audio frame from the learner."""

    data: bytes
    #: When the frame was read off the socket. Used to measure the
    #: interrupt-to-fence latency.
    received_at: float = 0.0


@dataclass
class ControlEvent:
    """One JSON control event from the learner."""

    envelope: dict[str, Any]
    #: When the event was read off the socket.
    received_at: float = 0.0


@dataclass
class DisconnectEvent:
    """The client went away."""

    code: int


@dataclass
class CallProviders:
    """The ports one call may use.

    Every provider is reached through a port; no provider class is ever
    imported by the runtime.
    """

    stt: Any
    tts: TextToSpeechPort
    reasoning: ReasoningPort
    language_code: str
    stt_vad: Any
    tts_voice: str
    tts_model: str
    tts_language: str


@dataclass
class CallOptions:
    """Everything the runtime needs that is not the socket itself."""

    identity: IdentityPort
    analyzer: AnalysisPort
    #: The providers of this call, when they are already built (the
    #: tests build fakes). ``None`` means "ask the factory".
    providers: CallProviders | None = None
    #: Builds the providers for a practice language id. ``None`` when the
    #: credentials or the catalog entry are missing.
    providers_factory: Callable[[str], CallProviders | None] | None = None
    practice_language: str = "English"
    coaching_language: str = "English"
    #: The consent captured at the ``start`` event.
    consent_granted: bool = False
    #: The consent check that runs again at write time. A withdrawal
    #: between the ``start`` event and the end of the call must stop the
    #: write, not merely be noted. It receives the verified user id and
    #: may be sync or async; the Supabase consent store is async.
    consent_checker: Callable[[str], Any] | None = None
    session_store: Any | None = None
    recording_store: Any | None = None
    #: The live-connection registry, for the per-account bound.
    connections: Any | None = None
    hold_ms: int = DEFAULT_TURN_HOLD_MS
    min_words: int = DEFAULT_MIN_TURN_WORDS
    call_cap_seconds: float = MAX_CALL_SECONDS
    keep_recording: bool = True


@dataclass
class _TurnRecord:
    """The runtime's memory of one completed turn."""

    turn: LearnerTurn
    observations: tuple[Any, ...] = ()
    recognition_status: str = "missing-transcription"
    speech_active_ms: int = 0


@dataclass
class _RuntimeState:
    """The mutable state of one call."""

    state: str = "connecting"
    turns: list[_TurnRecord] = field(default_factory=list)
    round_id: RoundId | None = None
    round_turn_start: int = 0
    completed_in_round: int = 0
    fenced_turns: set[TurnId] = field(default_factory=set)
    muted: bool = False
    speaking: bool = False
    pending_choice: str | None = None
    last_audio_sent_at: float | None = None
    interrupt_latency_ms: int | None = None
    #: The gap between the interrupt arriving and the turn being fenced.
    fence_latency_ms: int | None = None
    interrupt_count: int = 0


class CallRuntime:
    """One call, from the handshake to the durable metrics."""

    def __init__(
        self,
        websocket: Any,
        options: CallOptions,
        *,
        stream_factory: Callable[[CallProviders], RecognitionStream] | None = None,
    ) -> None:
        self._websocket = websocket
        self._options = options
        self._session_id: SessionId = new_session_id()
        self._connection_id: ConnectionId = new_connection_id()
        self._sequence = 0
        self._state = _RuntimeState()
        self._events: asyncio.Queue[Any] = asyncio.Queue(maxsize=EVENT_QUEUE_SIZE)
        self._send_lock = asyncio.Lock()
        self._reader: asyncio.Task[None] | None = None
        self._coach_task: asyncio.Task[Any] | None = None
        self._coach_turn_id: TurnId | None = None
        self._stream: RecognitionStream | None = None
        self._tts_session: Any | None = None
        self._endpointing = Endpointing(
            hold_ms=options.hold_ms, min_words=options.min_words
        )
        self._turn: LearnerTurn | None = None
        self._start_request: StartRequest | None = None
        self._user_id: str | None = None
        self._started_at = 0.0
        self._last_client_frame_at = 0.0
        self._last_sent_at = 0.0
        self._recording: bytearray | None = None
        self._recording_abandoned = False
        self._stream_factory = stream_factory
        self._closed = False
        #: Set when a collection did not complete the turn: the runtime
        #: waits for new speech before it collects again.
        self._awaiting_speech = False
        #: A learner-facing notice for the next/ending ``status`` event.
        self._notice: str | None = None
        #: When each completed turn became ready for the coach. The gap
        #: to the first coach audio byte is the latency we report.
        self._turn_ready_at: dict[TurnId, float] = {}
        #: Turns whose first coach audio byte was already measured.
        self._latency_recorded: set[TurnId] = set()
        #: The durable write has already run (so ``_shutdown`` does not
        #: repeat it after an explicit end).
        self._persisted = False

    # ------------------------------------------------------------------
    # ids and state
    # ------------------------------------------------------------------
    @property
    def session_id(self) -> SessionId:
        return self._session_id

    @property
    def connection_id(self) -> ConnectionId:
        return self._connection_id

    @property
    def state(self) -> str:
        return self._state.state

    @property
    def interrupt_latency_ms(self) -> int | None:
        """The measured gap between the last coach audio byte and the
        interrupt. Numbers only."""
        return self._state.interrupt_latency_ms

    # ------------------------------------------------------------------
    # sending
    # ------------------------------------------------------------------
    async def _send(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        round_id: RoundId | None = None,
        turn_id: TurnId | None = None,
        sample_time_ms: int | None = None,
    ) -> None:
        """Send one envelope and advance the per-connection sequence."""
        async with self._send_lock:
            self._sequence += 1
            envelope = server_envelope(
                event_type,
                payload,
                session_id=self._session_id,
                connection_id=self._connection_id,
                sequence=self._sequence,
                round_id=round_id if round_id is not None else self._state.round_id,
                turn_id=turn_id,
                sample_time_ms=sample_time_ms,
            )
            self._last_sent_at = time.monotonic()
            await self._websocket.send_json(envelope)

    @staticmethod
    def _detail_with_notice(detail: str | None, notice: str | None) -> str | None:
        """Compose a bounded detail, with a notice when there is one.

        The frozen ``status`` payload allows one optional ``detail`` of at
        most 200 characters. A learner-facing notice uses the ``notice:``
        prefix; an ordinary detail may precede it, so the caller still
        learns why the call ended.
        """
        parts: list[str] = []
        if detail:
            parts.append(detail)
        if notice:
            parts.append(f"{NOTICE_PREFIX}{notice}")
        if not parts:
            return None
        composed = " ".join(parts)
        # Keep the notice readable when the bound is reached: trim the
        # ordinary detail, never the learner-facing notice.
        if len(composed) > 200 and notice:
            room = max(0, 200 - len(f"{NOTICE_PREFIX}{notice}") - 1)
            prefix = (detail or "")[:room].rstrip()
            composed = f"{prefix} {NOTICE_PREFIX}{notice}".strip()
        return composed[:200]

    async def _send_status(
        self,
        state: str,
        detail: str | None = None,
        *,
        turn_id: TurnId | None = None,
        notice: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"state": state}
        composed = self._detail_with_notice(detail, notice)
        if composed:
            payload["detail"] = composed
        await self._send("status", payload, turn_id=turn_id)

    async def _send_failure(self, failure: call_errors.Failure) -> None:
        await self._send("error", failure.payload())

    # ------------------------------------------------------------------
    # the call
    # ------------------------------------------------------------------
    async def run(self) -> None:
        """Run the whole call. Never raises: every failure ends cleanly."""
        self._started_at = time.monotonic()
        self._last_client_frame_at = self._started_at
        self._last_sent_at = self._started_at
        try:
            await self._send_status("connecting")
            await self._receive_start()
            await self._open_stream()
            self._reader = asyncio.create_task(self._read_loop(), name="call-reader")
            await self._main_loop()
        except CallEnded:
            await self._end_socket()
        except CallFailure as failure:
            await self._fail(failure)
        except asyncio.CancelledError:
            await self._shutdown(reason="cancelled")
            raise
        except Exception:  # noqa: BLE001 - an unexpected failure ends the call
            LOGGER.exception(
                "call failed session=%s connection=%s",
                self._session_id,
                self._connection_id,
            )
            await self._fail(CallFailure(call_errors.INTERNAL, close_code=1011))
        finally:
            await self._shutdown(reason="done")

    async def _receive_start(self) -> None:
        """Wait for the first message and validate it as a ``start``."""
        try:
            message = await asyncio.wait_for(
                self._websocket.receive(), timeout=START_DEADLINE_S
            )
        except asyncio.TimeoutError as exc:
            raise CallFailure(call_errors.INVALID_START, close_code=1008) from exc
        await self._handle_start_message(message)

    async def _handle_start_message(self, message: dict[str, Any]) -> None:
        """Validate the first message and open the call."""
        if message.get("type") == "websocket.disconnect":
            raise CallEnded
        raw_text = message.get("text")
        if raw_text is None:
            # A binary first message is not a start event.
            raise CallFailure(call_errors.INVALID_START, close_code=1008)
        if len(raw_text.encode("utf-8")) > MAX_JSON_MESSAGE_BYTES:
            raise CallFailure(call_errors.MESSAGE_TOO_LARGE, close_code=1009)
        try:
            document = json.loads(raw_text)
        except ValueError as exc:
            raise CallFailure(call_errors.INVALID_START, close_code=1008) from exc
        try:
            start = validate_start_envelope(document)
        except InvalidStart as exc:
            failure = (
                call_errors.UNSUPPORTED_AUDIO_FORMAT
                if exc.code == "unsupported_audio_format"
                else call_errors.INVALID_START
            )
            raise CallFailure(failure, close_code=1008) from exc
        self._start_request = start

        # The token travels in the first event, never in a URL. An absent,
        # unverifiable or rejected token means a guest: the call still
        # runs, nothing is saved, and the learner is told why in the
        # ``ready`` status. A failing Auth server must not take the call
        # down with it.
        token = start.token
        if token:
            try:
                self._user_id = await self._options.identity.verify_token(token)
            except Exception:  # noqa: BLE001 - Auth down is a guest, not a failure
                LOGGER.warning(
                    "token verification failed session=%s connection=%s "
                    "category=identity_unavailable",
                    self._session_id,
                    self._connection_id,
                )
                self._user_id = None
            if self._user_id is None:
                self._notice = AUTH_NOTICE
                LOGGER.info(
                    "call continues as guest session=%s connection=%s "
                    "reason=auth_unverified",
                    self._session_id,
                    self._connection_id,
                )

        if self._options.providers is None and self._options.providers_factory is not None:
            try:
                self._options.providers = self._options.providers_factory(
                    start.practice_language_id
                )
            except Exception:  # noqa: BLE001 - an unusable configuration is not a call
                LOGGER.warning(
                    "provider construction failed session=%s connection=%s",
                    self._session_id,
                    self._connection_id,
                )
                self._options.providers = None
        if self._options.providers is None:
            # Never half-start: no provider session is opened when a
            # credential is missing.
            await self._send_status("error", "the speech service is not configured")
            raise CallFailure(call_errors.PROVIDER_NOT_CONFIGURED, close_code=1000)

        self._options.practice_language = _language_name(start.practice_language_id)
        self._options.coaching_language = _language_name(start.coaching_language_id)

        # The per-account bound is checked once the account is known.
        if self._user_id and self._options.connections is not None:
            if not self._options.connections.reserve_user(self._user_id):
                await self._send_status("error", "too many calls for this account")
                raise CallFailure(call_errors.TOO_MANY_CONNECTIONS, close_code=1008)

        self._options.consent_granted = start.recording_retention_granted
        if start.recording_retention_granted and self._user_id and self._options.keep_recording:
            self._recording = bytearray()

        # The notice is delivered once, in ``ready``. The interface keeps
        # the most recent notice in its own state, so a following
        # ``listening`` status does not erase it.
        await self._send_status("ready", notice=self._notice)
        self._notice = None
        self._state.state = "listening"

    async def _open_stream(self) -> None:
        """Open the recognition stream for this connection."""
        providers = self._options.providers
        assert providers is not None  # checked in _handle_start_message
        if self._stream_factory is not None:
            self._stream = self._stream_factory(providers)
        else:
            from gnani_coach.conversation.recognition import PortRecognitionStream

            self._stream = PortRecognitionStream(
                port=providers.stt,
                request=SttOpenRequest(
                    language_code=providers.language_code,
                    sample_rate=16000,
                    vad=providers.stt_vad,
                    connection_id=self._connection_id,
                ),
            )
        await self._send_status("listening")

    # ------------------------------------------------------------------
    # reading
    # ------------------------------------------------------------------
    async def _read_loop(self) -> None:
        """Read the socket into the event queue.

        The queue is bounded, so a burst applies backpressure to the
        socket instead of growing the process's memory.
        """
        try:
            while True:
                message = await self._websocket.receive()
                kind = message.get("type")
                if kind == "websocket.disconnect":
                    await self._put(DisconnectEvent(code=message.get("code", 1000)))
                    return
                data = message.get("bytes")
                if data is not None:
                    await self._put(FrameEvent(data=data, received_at=time.monotonic()))
                    continue
                text = message.get("text")
                if text is None:
                    continue
                if len(text.encode("utf-8")) > MAX_JSON_MESSAGE_BYTES:
                    await self._put(
                        ControlEvent(
                            envelope={"type": "__oversized__"},
                            received_at=time.monotonic(),
                        )
                    )
                    return
                try:
                    document = json.loads(text)
                except ValueError:
                    await self._put(
                        ControlEvent(
                            envelope={"type": "__malformed__"},
                            received_at=time.monotonic(),
                        )
                    )
                    return
                if isinstance(document, dict):
                    await self._put(
                        ControlEvent(
                            envelope=document, received_at=time.monotonic()
                        )
                    )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the reader reports by disconnect
            with contextlib.suppress(Exception):
                await self._put(DisconnectEvent(code=1011))

    async def _put(self, event: Any) -> None:
        await self._events.put(event)

    # ------------------------------------------------------------------
    # the main loop
    # ------------------------------------------------------------------
    async def _main_loop(self) -> None:
        """Consume events until the call ends."""
        while True:
            timeout = self._next_timeout()
            try:
                event = await asyncio.wait_for(self._events.get(), timeout=timeout)
            except asyncio.TimeoutError:
                await self._on_timeout()
                continue
            if isinstance(event, DisconnectEvent):
                await self._send_status("ended", "the client left")
                raise CallEnded
            if isinstance(event, FrameEvent):
                await self._on_frame(event)
                continue
            await self._on_control(event)

    def _next_timeout(self) -> float:
        """The next deadline: heartbeat, idle or the call cap."""
        now = time.monotonic()
        deadlines = [
            now + HEARTBEAT_INTERVAL_S,
            self._last_client_frame_at + IDLE_TIMEOUT_S,
            self._started_at + self._options.call_cap_seconds,
        ]
        return max(0.01, min(deadlines) - now)

    async def _on_timeout(self) -> None:
        """Handle the deadlines."""
        now = time.monotonic()
        if now - self._started_at >= self._options.call_cap_seconds:
            await self._send_status("ended", "the call reached its time limit")
            raise CallEnded
        if now - self._last_client_frame_at >= IDLE_TIMEOUT_S:
            await self._send_status("ended", "the call was idle")
            raise CallEnded
        if now - self._last_sent_at >= HEARTBEAT_INTERVAL_S:
            await self._send_status("heartbeat")

    # ------------------------------------------------------------------
    # frames
    # ------------------------------------------------------------------
    async def _on_frame(self, event: FrameEvent) -> None:
        """One frame of learner audio."""
        self._last_client_frame_at = time.monotonic()
        if len(event.data) != BINARY_FRAME_BYTES:
            raise CallFailure(call_errors.INVALID_FRAME_SIZE, close_code=1008)
        if self._state.muted:
            return
        self._endpointing.advance(FRAME_DURATION_MS)
        speech = self._endpointing.observe(event.data)
        if speech:
            self._awaiting_speech = False
        if self._recording is not None:
            self._append_recording(event.data)
        if (
            speech
            and self._state.speaking
            and self._endpointing.speech_run_ms >= ENDPOINTING_HANGOVER_MS
        ):
            # The learner started speaking while the coach was playing:
            # stop the audio and fence the turn. A short noise is not
            # speech, so the run has to last the hangover first.
            await self._interrupt(
                reason="learner_speech", since=event.received_at
            )
        turn = self._current_turn()
        if turn is not None:
            turn.ended_clock_ms = self._endpointing.clock_ms
            if len(turn.audio) < MAX_TURN_AUDIO_BYTES:
                turn.audio.extend(event.data)
        if self._stream is not None:
            await self._stream.push_frame(event.data)
        await self._maybe_finish_turn()

    def _current_turn(self) -> LearnerTurn | None:
        """The open turn, opened by the first frame of the call."""
        if self._turn is None:
            self._turn = LearnerTurn(
                turn_id=new_turn_id(),
                round_id=self._state.round_id,
                started_clock_ms=self._endpointing.clock_ms,
            )
        return self._turn

    def _append_recording(self, data: bytes) -> None:
        """Buffer the learner's audio for an opted-in recording."""
        if self._recording is None or self._recording_abandoned:
            return
        from gnani_coach.conversation.config import MAX_RECORDING_BYTES

        if len(self._recording) + len(data) > MAX_RECORDING_BYTES:
            # The bound is reached: the recording is abandoned rather than
            # truncated silently, and no recording id is written.
            self._recording_abandoned = True
            self._recording = bytearray()
            return
        self._recording.extend(data)

    async def _maybe_finish_turn(self) -> None:
        """Close the turn when the end-of-turn policy fires."""
        turn = self._turn
        if turn is None or self._state.speaking or self._awaiting_speech:
            return
        if not self._endpointing.hold_expired():
            return
        stream = self._stream
        if stream is not None:
            try:
                segments = await stream.collect(grace_ms=SEGMENT_GRACE_MS)
            except Exception as exc:  # noqa: BLE001 - the call survives
                failure = call_errors.from_exception(exc)
                LOGGER.warning(
                    "recognition failed session=%s category=%s",
                    self._session_id,
                    failure.category,
                )
                if failure is call_errors.BUDGET_EXHAUSTED:
                    # The call's own allowance is gone: the call ends
                    # cleanly with the frozen error shape.
                    raise CallFailure(failure, close_code=1000) from exc
                with contextlib.suppress(Exception):
                    await self._send_failure(failure)
                # Reconnect with the same VAD object and keep the call
                # alive: the learner may keep talking.
                with contextlib.suppress(Exception):
                    await stream.reopen()
                self._awaiting_speech = True
                return
            for segment in segments:
                turn.add_segment(segment)
                await self._send(
                    "transcript_final",
                    _transcript_payload(segment),
                    turn_id=turn.turn_id,
                )
        turn.ended_clock_ms = self._endpointing.clock_ms
        if not turn_is_complete(
            turn,
            self._endpointing,
            min_words=self._options.min_words,
            max_turn_ms=MAX_TURN_MS,
        ):
            # Not enough words yet: the turn stays open, the hold is
            # extended and the learner may keep talking.
            self._awaiting_speech = True
            return
        await self._complete_turn(turn)

    async def _complete_turn(self, turn: LearnerTurn) -> None:
        """Finish a learner turn: measure it, then let the coach answer."""
        turn.completed = True
        self._turn = None
        self._endpointing.reset()
        self._awaiting_speech = False
        self._state.completed_in_round += 1
        if self._state.round_id is None:
            self._state.round_id = new_round_id()
        turn.round_id = self._state.round_id

        record = _TurnRecord(turn=turn)
        record.observations, record.recognition_status, record.speech_active_ms = (
            await self._measure(turn)
        )
        self._state.turns.append(record)
        # The clock starts when the learner's turn is complete. The gap
        # to the first coach audio byte is reported per turn.
        self._turn_ready_at[turn.turn_id] = time.monotonic()
        self._coach_turn_id = turn.turn_id
        self._coach_task = asyncio.create_task(self._coach_turn(turn), name="call-coach")

    async def _measure(self, turn: LearnerTurn) -> tuple[tuple[Any, ...], str, int]:
        """Measure one turn with the analysis port.

        Only the learner's own audio is measured. The coach's audio never
        enters an analysis request.
        """
        request = AnalysisRequest(
            audio=bytes(turn.audio),
            sample_rate=16000,
            turn_id=turn.turn_id,
            round_id=turn.round_id,
            recognized_text=turn.text or None,
            audio_source="learner-audio",
            synthetic=False,
        )
        analyzer = self._options.analyzer
        speech_active_ms = 0
        result: AnalysisResult | None = None
        measurement = getattr(analyzer, "measure", None)
        if callable(measurement):
            try:
                measured = await measurement(request)
                result = measured.result
                speech_active_ms = int(measured.speech_active_ms or 0)
            except Exception:  # noqa: BLE001 - the measurement is best effort
                LOGGER.warning(
                    "measurement failed session=%s turn=%s",
                    self._session_id,
                    turn.turn_id,
                )
                result = None
        if result is None:
            result = await self._options.analyzer.analyze(request)
        if not speech_active_ms:
            speech_active_ms = derive_speech_active_ms(
                result.observations, duration_ms=turn.duration_ms
            )
        return tuple(result.observations), result.recognition_status, speech_active_ms

    # ------------------------------------------------------------------
    # the coach
    # ------------------------------------------------------------------
    async def _coach_turn(self, turn: LearnerTurn) -> None:
        """Produce and speak one coach reply."""
        providers = self._options.providers
        assert providers is not None
        try:
            self._state.state = "thinking"
            await self._send_status("thinking", turn_id=turn.turn_id)
            transcript = sanitize_transcript(turn.text, max_chars=MAX_TRANSCRIPT_CHARS)
            request = ReasoningRequest(
                recognized_text=transcript or "",
                instruction=build_turn_instruction(
                    scenario=self._scenario(),
                    level=self._level(),
                    practice_language=self._options.practice_language,
                    coaching_language=self._options.coaching_language,
                    topic=self._topic(),
                ),
                scenario=self._scenario(),
                level=self._level(),
                reply_language=self._options.coaching_language,
            )
            reply = await providers.reasoning.reply(request)
            if self._is_fenced(turn.turn_id):
                # A late reply of a fenced turn is never adopted.
                return
            text = sanitize_reply(reply.text)
            if not text:
                return
            await self._send("coach_text", {"text": text[:MAX_REPLY_CHARS]}, turn_id=turn.turn_id)
            await self._speak(text, turn.turn_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a provider failure ends the line
            failure = call_errors.from_exception(exc)
            LOGGER.warning(
                "coach turn failed session=%s turn=%s category=%s",
                self._session_id,
                turn.turn_id,
                failure.category,
            )
            with contextlib.suppress(Exception):
                await self._send_failure(failure)
        finally:
            self._state.speaking = False
            self._tts_session = None
            self._coach_turn_id = None
            if self._state.state in ("thinking", "speaking"):
                self._state.state = "listening"
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._send_status("listening")

        # The round break, announced at the natural boundary after the
        # coach's reply.
        if self._state.completed_in_round >= self._round_turns():
            await self._deliver_round_feedback()
        await self._apply_pending_choice(force=True)

    async def _speak(self, text: str, turn_id: TurnId) -> None:
        """Synthesise and send one coach line."""
        providers = self._options.providers
        assert providers is not None
        session = providers.tts.open_session(
            TtsOpenRequest(
                text=text,
                voice=providers.tts_voice,
                model=providers.tts_model,
                language=providers.tts_language,
            )
        )
        self._tts_session = session
        self._state.speaking = True
        descriptor_sent = False
        try:
            await self._send_status("speaking", turn_id=turn_id)

            async def forward(chunk: SpeechChunk) -> None:
                nonlocal descriptor_sent
                if self._is_fenced(turn_id):
                    # Late audio of a fenced turn is never sent.
                    return
                if not descriptor_sent:
                    descriptor_sent = True
                    await self._send(
                        "audio.frame.descriptor",
                        {
                            "sampleRateHz": 16000,
                            "sampleFormat": "s16le",
                            "channels": 1,
                            "frameByteLength": max(2, len(chunk.data)),
                            "firstSampleIndex": self._endpointing.clock_ms * 16,
                        },
                        turn_id=turn_id,
                    )
                await self._send_binary(chunk.data)
                self._record_first_audio(turn_id)

            await session.synthesize(on_chunk=forward)
        finally:
            self._state.speaking = False
            self._tts_session = None
            with contextlib.suppress(Exception):
                await session.aclose(reason="done")

    async def _send_binary(self, data: bytes) -> None:
        async with self._send_lock:
            self._last_sent_at = time.monotonic()
            self._state.last_audio_sent_at = self._last_sent_at
            await self._websocket.send_bytes(data)

    def _record_first_audio(self, turn_id: TurnId) -> None:
        """Log the end-of-turn to first-coach-audio latency, once.

        Numbers only: the session and turn ids, both opaque, and the
        milliseconds. No transcript, no reply and no user id.
        """
        if turn_id in self._latency_recorded:
            return
        ready_at = self._turn_ready_at.pop(turn_id, None)
        if ready_at is None:
            return
        self._latency_recorded.add(turn_id)
        measured = latency_registry.record((time.monotonic() - ready_at) * 1000.0)
        LOGGER.info(
            "turn latency session=%s connection=%s turn=%s turn_latency_ms=%d",
            self._session_id,
            self._connection_id,
            turn_id,
            measured,
        )

    # ------------------------------------------------------------------
    # interruption
    # ------------------------------------------------------------------
    def _is_fenced(self, turn_id: TurnId | None) -> bool:
        if turn_id is None:
            return False
        return turn_id in self._state.fenced_turns

    async def _interrupt(self, *, reason: str, since: float = 0.0) -> None:
        """Stop the coach, fence the turn and keep the round state.

        Stopping the playback is **not** cancelling the provider: the
        provider request may still be running and may still be billed.
        Nothing here says otherwise.

        Two numbers are measured and logged, both in milliseconds and
        both about *this* service:

        * ``last_audio_gap_ms`` — the gap between the last coach audio
          byte and the interrupt;
        * ``fence_latency_ms`` — the gap between the interrupt arriving
          and the turn being fenced;
        * ``voice_onset_gap_ms`` — the **learner-audio** time since the
          learner's voice started, which is what the hang-over waits for.
        """
        now = time.monotonic()
        last_audio = self._state.last_audio_sent_at
        latency = -1 if last_audio is None else int(round((now - last_audio) * 1000))
        self._state.interrupt_latency_ms = latency
        self._state.interrupt_count += 1
        fence_latency = (
            -1 if since <= 0 else int(round((now - since) * 1000))
        )
        self._state.fence_latency_ms = fence_latency

        coach_turn = self._coach_turn_id
        if coach_turn is not None:
            self._state.fenced_turns.add(coach_turn)
        if self._turn is not None:
            self._state.fenced_turns.add(self._turn.turn_id)

        # Stop delivering the coach's audio.
        session = self._tts_session
        if session is not None:
            with contextlib.suppress(Exception):
                await session.cancel_consumption()
        # Stop the wait for the model.
        task = self._coach_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._coach_task = None
        self._coach_turn_id = None
        self._state.speaking = False
        if self._state.state in ("thinking", "speaking"):
            self._state.state = "listening"
            with contextlib.suppress(Exception):
                await self._send_status("listening")
        LOGGER.info(
            "interrupt session=%s connection=%s reason=%s last_audio_gap_ms=%d "
            "fence_latency_ms=%d voice_onset_gap_ms=%d",
            self._session_id,
            self._connection_id,
            reason,
            latency,
            fence_latency,
            self._endpointing.voice_onset_gap_ms,
        )

    # ------------------------------------------------------------------
    # control events
    # ------------------------------------------------------------------
    async def _on_control(self, event: ControlEvent) -> None:
        """Handle one client control event."""
        envelope = event.envelope
        kind = envelope.get("type")
        if kind == "__oversized__":
            raise CallFailure(call_errors.MESSAGE_TOO_LARGE, close_code=1009)
        if kind == "__malformed__":
            raise CallFailure(call_errors.INVALID_START, close_code=1008)
        if kind == "interrupt":
            await self._interrupt(
                reason="learner_speech", since=event.received_at
            )
            return
        if kind == "mute":
            payload = envelope.get("payload") or {}
            muted = bool(payload.get("muted"))
            if muted and not self._state.muted:
                # "Give me a moment": the learner is thinking, not
                # ending a turn, and the hold grows.
                self._endpointing.extend_hold(MUTE_HOLD_EXTENSION_MS)
            self._state.muted = muted
            return
        if kind == "end":
            # Persist *before* announcing the end, so a storage failure can
            # be told to the learner in the same ``status ended`` event.
            outcome = await self._persist_once()
            notice = (
                NOT_SAVED_NOTICE
                if outcome == "not_saved"
                else self._notice
            )
            await self._send_status(
                "ended", "the learner ended the call", notice=notice
            )
            raise CallEnded
        if kind == "retry":
            await self._on_retry(envelope)
            return
        if kind == "coaching_choice":
            payload = envelope.get("payload") or {}
            choice = payload.get("choice")
            if choice in ("keep_talking", "coach_now", "skip_feedback"):
                self._state.pending_choice = choice
                await self._apply_pending_choice()
            return
        # Any other client event is ignored: the schema's client
        # vocabulary is closed and the runtime never guesses.

    async def _apply_pending_choice(self, *, force: bool = False) -> None:
        """Apply a coaching choice, when the coach is not speaking."""
        choice = self._state.pending_choice
        if choice is None:
            return
        if not force and self._coach_task is not None and not self._coach_task.done():
            return
        self._state.pending_choice = None
        if choice == "coach_now":
            await self._deliver_round_feedback()
        elif choice == "skip_feedback":
            # The round ends without feedback and a new round begins.
            self._state.round_id = new_round_id()
            self._state.round_turn_start = len(self._state.turns)
            self._state.completed_in_round = 0

    async def _on_retry(self, envelope: dict[str, Any]) -> None:
        """Repeat or reframe one answer.

        The retry uses the **same metric definitions** on the same prompt:
        the turn's transcript is reused as it was, and no new measurement
        is produced.
        """
        payload = envelope.get("payload") or {}
        turn_id = payload.get("turnId")
        focus = payload.get("focus")
        record = next(
            (item for item in self._state.turns if item.turn.turn_id == turn_id),
            None,
        )
        if record is None:
            return
        self._coach_turn_id = turn_id
        self._coach_task = asyncio.create_task(
            self._do_retry(record, focus), name="call-retry"
        )

    async def _do_retry(self, record: _TurnRecord, focus: Any) -> None:
        """The retry itself, in its own task so an interrupt can fence it."""
        providers = self._options.providers
        assert providers is not None
        turn_id = record.turn.turn_id
        try:
            transcript = sanitize_transcript(record.turn.text, max_chars=MAX_TRANSCRIPT_CHARS)
            request = ReasoningRequest(
                recognized_text=transcript or "",
                instruction=build_turn_instruction(
                    scenario=self._scenario(),
                    level=self._level(),
                    practice_language=self._options.practice_language,
                    coaching_language=self._options.coaching_language,
                    topic=self._topic(),
                    focus=focus if isinstance(focus, str) else None,
                ),
                scenario=self._scenario(),
                level=self._level(),
                reply_language=self._options.coaching_language,
            )
            reply = await providers.reasoning.reply(request)
            if self._is_fenced(turn_id):
                return
            text = sanitize_reply(reply.text)
            if not text:
                return
            await self._send("coach_text", {"text": text[:MAX_REPLY_CHARS]}, turn_id=turn_id)
            await self._speak(text, turn_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            with contextlib.suppress(Exception):
                await self._send_failure(call_errors.from_exception(exc))
        finally:
            self._coach_turn_id = None
            self._state.speaking = False

    # ------------------------------------------------------------------
    # the coaching break
    # ------------------------------------------------------------------
    async def _deliver_round_feedback(self) -> None:
        """Deliver one coaching break."""
        self._state.state = "coaching"
        await self._send_status("coaching")
        facts = self._round_facts()
        providers = self._options.providers
        assert providers is not None

        draft = None
        transcript = self._round_transcript()
        if facts.turn_count > 0 and transcript:
            try:
                reply = await providers.reasoning.reply(
                    ReasoningRequest(
                        recognized_text=transcript,
                        instruction=build_feedback_instruction(
                            scenario=self._scenario(),
                            level=self._level(),
                            coaching_language=self._options.coaching_language,
                            facts=facts.facts_document(),
                        ),
                        scenario=self._scenario(),
                        level=self._level(),
                        reply_language=self._options.coaching_language,
                    )
                )
                candidate = parse_feedback(reply.text)
                if candidate is None:
                    LOGGER.info(
                        "round feedback rejected session=%s reason=unparsable",
                        self._session_id,
                    )
                else:
                    reason = validate_feedback(candidate, facts)
                    if reason is None:
                        draft = candidate
                    else:
                        LOGGER.info(
                            "round feedback rejected session=%s reason=%s",
                            self._session_id,
                            reason,
                        )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "round feedback call failed session=%s category=%s",
                    self._session_id,
                    call_errors.from_exception(exc).category,
                )

        if draft is None:
            payload = {
                "strengths": [],
                "improvements": [],
                "languageNotes": [],
                "evidence": facts.evidence(),
            }
            spoken = facts_only_message(
                facts, coaching_language=self._options.coaching_language
            )
        else:
            payload = {
                "strengths": draft.strengths[:1],
                "improvements": draft.improvements[:2],
                "languageNotes": draft.language_notes[:1],
                "evidence": facts.evidence(),
            }
            spoken = " ".join(
                [*draft.strengths, *draft.improvements, *draft.language_notes]
            ).strip()

        # The round break belongs to the last learner turn of the round.
        # The interface needs that id to offer "Try again"; without it the
        # retry control is present but cannot do anything. The id is the
        # learner's turn, not the coach's spoken summary turn.
        round_records = self._state.turns[self._state.round_turn_start :]
        feedback_turn_id = (
            round_records[-1].turn.turn_id if round_records else None
        )
        await self._send("round_feedback", payload, turn_id=feedback_turn_id)
        if spoken:
            await self._send("coach_text", {"text": spoken[:MAX_REPLY_CHARS]})
            await self._speak(spoken, new_turn_id())

        # The round is over: the next turn starts a new one.
        self._state.round_id = new_round_id()
        self._state.round_turn_start = len(self._state.turns)
        self._state.completed_in_round = 0
        self._state.state = "listening"
        await self._send_status("listening")

    def _round_facts(self) -> RoundFacts:
        """The measured facts of the round that just ended."""
        records = self._state.turns[self._state.round_turn_start :]
        observations: list[Any] = []
        for record in records:
            observations.extend(record.observations)
        return RoundFacts(
            turn_count=len(records),
            observations=tuple(observations),
        )

    def _round_transcript(self) -> str:
        """The round's transcript, as the model's context.

        It is transient: it is never logged, never measured and never
        written to the durable metrics.
        """
        records = self._state.turns[self._state.round_turn_start :]
        parts = [record.turn.text for record in records if record.turn.text]
        return sanitize_transcript(" ".join(parts), max_chars=3900) or ""

    # ------------------------------------------------------------------
    # settings helpers
    # ------------------------------------------------------------------
    def _scenario(self) -> str:
        start = self._start_request
        if start is None:
            return "everyday"
        if start.scenario_preset_id:
            return f"{start.scenario_id}/{start.scenario_preset_id}"
        return start.scenario_id

    def _level(self) -> str:
        start = self._start_request
        return start.level if start is not None else "beginner"

    def _topic(self) -> str | None:
        start = self._start_request
        return start.custom_topic if start is not None else None

    def _round_turns(self) -> int:
        start = self._start_request
        return start.coaching_round_turns if start is not None else 4

    # ------------------------------------------------------------------
    # ending
    # ------------------------------------------------------------------
    async def _end_socket(self) -> None:
        """Close the socket cleanly."""
        with contextlib.suppress(Exception):
            await self._websocket.close(code=1000, reason="ended")

    async def _fail(self, failure: CallFailure) -> None:
        """Report a failure and close the socket."""
        try:
            await self._send_failure(failure.failure)
        except Exception as exc:  # noqa: BLE001 - the close must still happen
            LOGGER.warning(
                "error envelope could not be sent session=%s reason=%s",
                self._session_id,
                type(exc).__name__,
            )
        with contextlib.suppress(Exception):
            await self._websocket.close(
                code=failure.close_code, reason=failure.failure.code[:120]
            )

    async def _shutdown(self, *, reason: str) -> None:
        """Close everything this call owns, exactly once."""
        if self._closed:
            return
        self._closed = True
        if self._coach_task is not None and not self._coach_task.done():
            self._coach_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._coach_task
        if self._reader is not None and not self._reader.done():
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
        if self._stream is not None:
            with contextlib.suppress(Exception):
                await self._stream.close(reason=reason)
        if self._user_id and self._options.connections is not None:
            with contextlib.suppress(Exception):
                self._options.connections.release_user(self._user_id)
        await self._persist_once()

    async def _persist_once(self) -> str:
        """Run the durable write exactly once, and report its outcome.

        ``"saved"`` — the metrics (and, when allowed, the audio) were
        written; ``"guest"`` — there was no account to write for;
        ``"not_saved"`` — an authenticated caller's session could not be
        written. The last case is what the learner is told at the end.
        """
        if self._persisted:
            return "saved" if self._user_id else "guest"
        self._persisted = True
        return await self._persist()

    async def _persist(self) -> str:
        """Compute and write the durable metrics, and the opt-in recording.

        A **guest writes nothing**. An authenticated caller gets the
        metrics; the audio is written only when the consent is granted
        *and* still granted at write time.
        """
        elapsed_ms = int((time.monotonic() - self._started_at) * 1000)
        if self._user_id is None:
            LOGGER.info(
                "call ended session=%s connection=%s turns=%d duration_ms=%d guest=1",
                self._session_id,
                self._connection_id,
                len(self._state.turns),
                elapsed_ms,
            )
            return "guest"

        recording_id = await self._persist_recording()
        document = self._durable_metrics(recording_id=recording_id)
        problems = validate_durable_metrics(document)
        store = self._options.session_store
        outcome = "saved"
        if problems:
            LOGGER.warning(
                "durable metrics refused session=%s problems=%d",
                self._session_id,
                len(problems),
            )
            outcome = "not_saved"
        elif store is None:
            # An authenticated caller with no configured storage: saying
            # "saved" would be a lie.
            LOGGER.warning("metrics not written session=%s reason=no_store", self._session_id)
            outcome = "not_saved"
        else:
            try:
                await store.save_metrics(document)
            except Exception:  # noqa: BLE001 - a store failure is not fatal
                LOGGER.warning("metrics write failed session=%s", self._session_id)
                outcome = "not_saved"
        LOGGER.info(
            "call ended session=%s connection=%s turns=%d duration_ms=%d guest=0 "
            "recording=%d saved=%d",
            self._session_id,
            self._connection_id,
            len(self._state.turns),
            elapsed_ms,
            1 if recording_id else 0,
            1 if outcome == "saved" else 0,
        )
        return outcome

    def _durable_metrics(self, *, recording_id: str | None) -> dict[str, Any]:
        """The durable-metrics document of this call."""
        start = self._start_request
        turns = [
            TurnMetrics(
                turn_id=record.turn.turn_id,
                round_id=record.turn.round_id,
                duration_ms=record.turn.duration_ms,
                recognition_status=record.recognition_status,
                audio_source_classification="learner-audio",
                observations=record.observations,
                speech_active_ms=record.speech_active_ms,
            )
            for record in self._state.turns
        ]
        speaking = sum(record.speech_active_ms for record in self._state.turns)
        return DurableMetrics(
            session_id=self._session_id,
            recorded_at=utc_now_iso(),
            practice_language_id=start.practice_language_id if start else "english",
            scenario_id=start.scenario_id if start else "everyday",
            turns=turns,
            recording_id=recording_id,
            speaking_time_ms=speaking,
        ).to_document()

    async def _persist_recording(self) -> str | None:
        """Write the recording, when consent still allows it.

        The consent is checked **again** here: a withdrawal between the
        ``start`` event and the end of the call must stop the write, not
        merely be noted.
        """
        store = self._options.recording_store
        if store is None or self._recording is None:
            return None
        if not await self._consent_is_granted():
            LOGGER.info(
                "recording not written session=%s reason=consent", self._session_id
            )
            return None
        pcm = bytes(self._recording)
        if not pcm:
            return None
        # The buffer is raw s16le PCM; the store and the replay route speak
        # WAV. The samples are wrapped, never changed, and the duration is
        # still the sample count.
        try:
            reference = await store.save_recording(
                self._user_id,
                self._session_id,
                wav_bytes(pcm),
                duration_ms=pcm_duration_ms(pcm),
            )
        except Exception:  # noqa: BLE001 - a store failure is not fatal
            LOGGER.warning("recording write failed session=%s", self._session_id)
            self._notice = RECORDING_NOT_SAVED_NOTICE
            return None
        recording_id = getattr(reference, "recording_id", None)
        return recording_id if isinstance(recording_id, str) else None

    async def _consent_is_granted(self) -> bool:
        """The consent, re-checked at write time.

        The checker is the real consent store, so a withdrawal during the
        call is seen here even though the ``start`` event granted it. A
        checker that fails or raises is **not** a consent: the audio is
        not written.
        """
        checker = self._options.consent_checker
        if checker is None:
            return bool(self._options.consent_granted)
        if self._user_id is None:
            return False
        try:
            outcome = checker(self._user_id)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            return bool(outcome)
        except Exception:  # noqa: BLE001 - an unknown state is not a consent
            return False


def _transcript_payload(segment: Any) -> dict[str, Any]:
    """The transient payload of a recognised segment."""
    payload: dict[str, Any] = {"text": (segment.text or "")[:MAX_TRANSCRIPT_CHARS]}
    segment_id = getattr(segment, "segment_id", None)
    if isinstance(segment_id, str) and segment_id:
        payload["segmentId"] = segment_id[:80]
    return payload


def _language_name(language_id: str) -> str:
    """The display name of a catalog language, or its id."""
    from gnani_coach.conversation.catalog import language_names

    return language_names().get(language_id, language_id)
