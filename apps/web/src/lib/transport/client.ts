/**
 * The call client — Phase 04.
 *
 * One WebSocket carries the whole call, in both directions
 * (`docs/contracts/call-transport.md`). This client implements the browser
 * half of that contract:
 *
 * - it opens the socket to `VOICE_WS_URL` and sends `start` **first**;
 * - it sends binary PCM16 frames afterwards, each exactly 1,024 bytes;
 * - it handles every server event;
 * - it fences by `connectionId` and `sequence`, and drops stale turns;
 * - it watches the heartbeat, reconnects a **bounded** number of times with
 *   a new connection, and never creates a duplicate turn;
 * - it stops the call at the 10-minute product cap and warns at 9 minutes;
 * - it exposes the `interrupt`, `mute`, `end`, `retry` and `coaching_choice`
 *   controls.
 */

import { FRAME_BYTE_LENGTH } from "../audio/constants";
import {
  buildClientEnvelope,
  buildStartEnvelope,
  buildStartPayload,
  LEARNER_ENDED,
  TIME_LIMIT,
} from "./envelope";
import { describeError, type LocalError, type PlainError } from "./errors";
import { Fence } from "./fencing";
import type {
  AudioFrameDescriptorPayload,
  CoachingChoice,
  EndReason,
  ErrorPayload,
  ServerEvent,
  SessionSettings,
  StatusPayload,
  StatusState,
} from "./types";

/** The states the connection moves through. */
export type ConnectionState =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "failed";

/** The product cap: a call is at most 10 minutes. */
export const CALL_LIMIT_MS = 10 * 60 * 1000;
/** The warning: 9 minutes into the call. */
export const CALL_WARNING_MS = 9 * 60 * 1000;
/** How many times the client reconnects before giving up. */
export const MAX_RECONNECT_ATTEMPTS = 3;
/** The backoff between reconnect attempts. */
export const RECONNECT_DELAYS_MS = [500, 1000, 2000];
/** No server message for this long means the connection is dead. */
export const IDLE_TIMEOUT_MS = 45_000;
/** How often the idle watchdog looks. */
export const IDLE_CHECK_INTERVAL_MS = 5_000;

export interface CallClientOptions {
  /** The voice service WebSocket URL (`VOICE_WS_URL`). */
  url: string;
  /** The validated session settings for this call. */
  settings: SessionSettings;
  /** The caller's own access token, or null for a guest call. */
  getToken: () => Promise<string | null>;
  /** The declared audio sample rate. */
  sampleRateHz: number;
  /** A server event that passed the fence. */
  onEvent: (event: ServerEvent) => void;
  /** Binary audio that belongs to the current turn. */
  onBinary: (
    data: ArrayBuffer,
    turnId: string,
    kind: "reply" | "backchannel",
  ) => void;
  /** The connection moved. */
  onConnectionState: (state: ConnectionState, detail?: string) => void;
  /** A client-side failure. */
  onLocalError: (error: LocalError) => void;
  /** A server error, in plain words. */
  onServerError: (error: PlainError) => void;
  /** The coach's turn was interrupted locally. */
  onInterrupt: (turnId: string) => void;
  /** The call reached the warning point. */
  onWarning: (message: string) => void;
  /** The call reached the product cap. */
  onLimitReached: () => void;
  /** Injectable clock, for tests. */
  now?: () => number;
  /** Injectable scheduler, for tests. */
  setTimeoutFn?: (handler: () => void, timeout: number) => number;
  clearTimeoutFn?: (handle: number) => void;
}

export class CallClient {
  private readonly options: CallClientOptions;
  private readonly fence = new Fence();
  private socket: WebSocket | null = null;
  private sequence = 0;
  private reconnectAttempts = 0;
  private startedAtMs = 0;
  private lastMessageAtMs = 0;
  private closedByUs = false;
  private startSent = false;
  private serverReady = false;
  private activeDescriptorTurnId: string | null = null;
  private activeDescriptorKind: "reply" | "backchannel" = "reply";
  private activeSampleRateHz: number;
  private lastStatus: StatusState | null = null;
  private idleTimer: number | null = null;
  private limitTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private readonly now: () => number;
  private readonly setTimeoutFn: (handler: () => void, timeout: number) => number;
  private readonly clearTimeoutFn: (handle: number) => void;

  constructor(options: CallClientOptions) {
    this.options = options;
    this.activeSampleRateHz = options.sampleRateHz;
    this.now = options.now ?? (() => Date.now());
    this.setTimeoutFn =
      options.setTimeoutFn ?? ((handler, timeout) => setTimeout(handler, timeout) as unknown as number);
    this.clearTimeoutFn =
      options.clearTimeoutFn ?? ((handle) => clearTimeout(handle as unknown as ReturnType<typeof setTimeout>));
  }

  /**
   * The last state a `status` event reported.
   *
   * The client keeps it itself, so a decision that has to be made the
   * moment an event arrives — "is the coach talking right now?" — does not
   * wait for the next render.
   */
  currentStatus(): StatusState | null {
    return this.lastStatus;
  }

  /** Open the socket and send `start`. Safe to call once. */
  start(): void {    if (this.socket) {
      return;
    }
    this.closedByUs = false;
    this.startedAtMs = this.now();
    this.lastMessageAtMs = this.startedAtMs;
    this.openSocket("connecting");
    this.startIdleWatchdog();
    this.startLimitWatchdog();
  }

  /** Close the socket for good. */
  close(reason: EndReason = LEARNER_ENDED): void {
    this.closedByUs = true;
    this.stopTimers();
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      try {
        this.send("end", { reason });
      } catch {
        // The socket went away between the check and the send.
      }
    }
    this.closeSocket();
    this.options.onConnectionState("closed");
  }

  /**
   * Ask the service to end the call, and keep the socket open long enough
   * to hear its answer.
   *
   * The explicit ``end`` is how the learner is told "this session was not
   * saved" in the same turn: the service persists first, then sends
   * ``status ended`` with the notice. Closing immediately would throw that
   * away. A two-second fallback closes the socket if the service does not
   * answer, so a hung service cannot keep the microphone or the socket
   * alive.
   */
  requestEnd(reason: EndReason = LEARNER_ENDED): void {
    if (this.closedByUs) {
      return;
    }
    this.closedByUs = true;
    this.stopTimers();
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      this.closeSocket();
      this.options.onConnectionState("closed");
      return;
    }
    try {
      this.send("end", { reason });
    } catch {
      // The socket went away between the check and the send.
    }
    this.setTimeoutFn(() => {
      this.closeSocket();
      this.options.onConnectionState("closed");
    }, 2_000);
  }

  /* ---------------------------------------------------------------- */
  /* Controls                                                         */
  /* ---------------------------------------------------------------- */

  /** Send one audio frame. Only whole 1,024-byte frames are accepted. */
  sendFrame(frame: Uint8Array): void {
    if (frame.length !== FRAME_BYTE_LENGTH) {
      return;
    }
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    if (!this.startSent || !this.serverReady) {
      // The contract puts the binary frames after the `start` event and the
      // server's answer to it.
      return;
    }
    const buffer = frame.buffer.slice(
      frame.byteOffset,
      frame.byteOffset + frame.byteLength,
    ) as ArrayBuffer;
    this.socket.send(buffer);
  }

  /** Tell the server the learner muted or unmuted. */
  setMuted(muted: boolean): void {
    this.send("mute", { muted });
  }

  /**
   * The learner started speaking while the coach was playing.
   *
   * The turn is fenced immediately, so a late coach text, a late
   * descriptor and late audio for that turn are dropped.
   */
  interrupt(): void {
    const turnId = this.fence.currentTurn();
    this.send("interrupt", { reason: "learner_speech" });
    if (turnId) {
      this.fence.fenceTurn(turnId);
      this.options.onInterrupt(turnId);
    }
  }

  /** Ask to repeat or reframe one answer. */
  retry(turnId: string, focus?: string): void {
    const payload: { turnId: string; focus?: string } = { turnId };
    if (focus && focus.trim().length > 0) {
      payload.focus = focus.trim().slice(0, 400);
    }
    this.send("retry", payload, turnId);
  }

  /** "Keep talking", "Coach me now" or "Skip feedback". */
  coachingChoice(choice: CoachingChoice): void {
    this.send("coaching_choice", { choice });
  }

  /* ---------------------------------------------------------------- */
  /* Internals                                                        */
  /* ---------------------------------------------------------------- */

  private openSocket(state: ConnectionState): void {
    this.options.onConnectionState(state);
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.options.url);
    } catch {
      this.options.onLocalError({
        kind: "socket_failed",
        title: "We could not reach the coach.",
        message: "The connection to the voice service could not be opened.",
        advice: "Check your connection and try again.",
        retryable: true,
      });
      this.options.onConnectionState("failed");
      return;
    }
    socket.binaryType = "arraybuffer";
    this.socket = socket;
    this.sequence = 0;
    this.startSent = false;
    this.serverReady = false;

    socket.onopen = () => {
      this.options.onConnectionState("open");
      void this.sendStart();
    };

    socket.onmessage = (event: MessageEvent) => {
      this.lastMessageAtMs = this.now();
      if (typeof event.data === "string") {
        this.handleJson(event.data);
        return;
      }
      if (event.data instanceof ArrayBuffer) {
        this.handleBinary(event.data);
        return;
      }
    };

    socket.onerror = () => {
      // The close event carries the outcome; the error event only says
      // "something went wrong", so it is not turned into a message here.
    };

    socket.onclose = () => {
      this.socket = null;
      if (this.closedByUs) {
        return;
      }
      this.handleUnexpectedClose();
    };
  }

  private async sendStart(): Promise<void> {
    let token: string | null = null;
    try {
      token = await this.options.getToken();
    } catch {
      token = null;
    }
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const payload = buildStartPayload(this.options.settings, token, this.options.sampleRateHz);
    const envelope = buildStartEnvelope(payload, {
      sequence: this.sequence,
      sessionId: null,
      connectionId: null,
    });
    this.sequence += 1;
    this.startSent = true;
    this.socket.send(JSON.stringify(envelope));
  }

  private send<P>(type: Parameters<typeof buildClientEnvelope>[0], payload: P, turnId?: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const envelope = buildClientEnvelope(type, payload, {
      sequence: this.sequence,
      sessionId: this.fence.currentConnectionId() ? this.sessionId : null,
      connectionId: this.fence.currentConnectionId(),
      roundId: null,
      turnId: turnId ?? null,
    });
    this.sequence += 1;
    this.socket.send(JSON.stringify(envelope));
  }

  private sessionId: string | null = null;

  private handleJson(raw: string): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return;
    }
    if (typeof parsed !== "object" || parsed === null) {
      return;
    }
    const envelope = parsed as Partial<ServerEvent> & { type?: string };
    if (typeof envelope.type !== "string") {
      return;
    }
    const verdict = this.fence.accept({
      type: envelope.type,
      connectionId: envelope.connectionId ?? null,
      sequence: typeof envelope.sequence === "number" ? envelope.sequence : -1,
      turnId: envelope.turnId ?? null,
    });
    if (!verdict.accepted) {
      return;
    }
    if (envelope.sessionId) {
      this.sessionId = envelope.sessionId;
    }
    const event = envelope as ServerEvent;
    switch (event.type) {
      case "status": {
        const payload = event.payload as StatusPayload;
        this.lastStatus = payload.state;
        if (payload.state === "ready" || payload.state === "listening") {
          this.serverReady = true;
        }
        if (payload.state === "ended") {
          this.closedByUs = true;
        }
        break;
      }
      case "audio.frame.descriptor": {
        const payload = event.payload as AudioFrameDescriptorPayload;
        this.activeDescriptorTurnId = event.turnId;
        this.activeDescriptorKind = payload.kind ?? "reply";
        this.activeSampleRateHz = payload.sampleRateHz;
        break;
      }
      case "error": {
        this.options.onServerError(describeError(event.payload as ErrorPayload));
        break;
      }
      default:
        break;
    }
    this.options.onEvent(event);
  }

  private handleBinary(data: ArrayBuffer): void {
    const turnId = this.activeDescriptorTurnId;
    if (!turnId) {
      // No descriptor yet: the frames cannot be attributed to a turn, so
      // they are dropped rather than guessed at.
      return;
    }
    if (this.fence.isTurnFenced(turnId)) {
      return;
    }
    if (this.fence.currentTurn() !== turnId) {
      return;
    }
    this.options.onBinary(data, turnId, this.activeDescriptorKind);
  }

  private handleUnexpectedClose(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.options.onLocalError({
        kind: "socket_closed",
        title: "The call was disconnected.",
        message: "The connection to the voice service closed unexpectedly.",
        advice: "Try again — you can start a new call.",
        retryable: true,
      });
      this.options.onConnectionState("failed");
      this.stopTimers();
      return;
    }
    const delay = RECONNECT_DELAYS_MS[
      Math.min(this.reconnectAttempts, RECONNECT_DELAYS_MS.length - 1)
    ];
    this.reconnectAttempts += 1;
    this.options.onConnectionState("reconnecting");
    // A reconnect is a new connection: the fence keeps the old connection
    // id so late events from it are dropped, and the server's new id is
    // recognised when it arrives.
    this.fence.beginNewConnection();
    this.activeDescriptorTurnId = null;
    this.activeDescriptorKind = "reply";
    this.reconnectTimer = this.setTimeoutFn(() => {
      this.reconnectTimer = null;
      this.openSocket("reconnecting");
    }, delay);
  }

  private closeSocket(): void {
    if (this.socket) {
      this.socket.onopen = null;
      this.socket.onmessage = null;
      this.socket.onerror = null;
      this.socket.onclose = null;
      try {
        this.socket.close();
      } catch {
        // Already closing.
      }
      this.socket = null;
    }
  }

  private startIdleWatchdog(): void {
    this.stopIdleWatchdog();
    this.idleTimer = this.setTimeoutFn(() => {
      this.idleTimer = null;
      const silence = this.now() - this.lastMessageAtMs;
      if (silence > IDLE_TIMEOUT_MS && this.socket) {
        // The connection looks dead. Close it so the bounded reconnect
        // path runs; a new connection gets a new connection id.
        this.closeSocket();
        this.handleUnexpectedClose();
        return;
      }
      this.startIdleWatchdog();
    }, IDLE_CHECK_INTERVAL_MS);
  }

  private stopIdleWatchdog(): void {
    if (this.idleTimer !== null) {
      this.clearTimeoutFn(this.idleTimer);
      this.idleTimer = null;
    }
  }

  private startLimitWatchdog(): void {
    this.stopLimitWatchdog();
    this.limitTimer = this.setTimeoutFn(() => {
      this.limitTimer = null;
      this.options.onWarning(
        "You have one minute left. The call ends at ten minutes so the service stays within its limit.",
      );
      this.limitTimer = this.setTimeoutFn(() => {
        this.limitTimer = null;
        this.options.onLimitReached();
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
          this.send("end", { reason: TIME_LIMIT });
        }
        this.closedByUs = true;
        this.closeSocket();
        this.options.onConnectionState("closed");
      }, CALL_LIMIT_MS - CALL_WARNING_MS);
    }, CALL_WARNING_MS);
  }

  private stopLimitWatchdog(): void {
    if (this.limitTimer !== null) {
      this.clearTimeoutFn(this.limitTimer);
      this.limitTimer = null;
    }
  }

  private stopTimers(): void {
    this.stopIdleWatchdog();
    this.stopLimitWatchdog();
    if (this.reconnectTimer !== null) {
      this.clearTimeoutFn(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

/* Re-exported so the feature code has one import for the transport types. */
export type {
  CoachingChoice,
  RoundFeedbackPayload,
  TranscriptPayload,
  CoachTextPayload,
} from "./types";
