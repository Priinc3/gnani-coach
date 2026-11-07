/**
 * The call client — Phase 04.
 *
 * The transport is tested against a fake WebSocket, so the whole contract
 * is exercised without a browser and without a service:
 *
 * - `start` is the first message, and it carries the settings and the
 *   caller's own token;
 * - binary frames follow the server's answer, and only whole 1,024-byte
 *   frames are sent;
 * - every control event is sent in the frozen shape;
 * - the connection, the sequence and the turn are fenced;
 * - an unexpected close reconnects a bounded number of times, with a new
 *   connection and no duplicate turn.
 */

import { expect, test } from "@playwright/test";

import { CallClient } from "../../src/lib/transport/client";
import type { SessionSettings } from "../../src/lib/transport/types";
import { validateEnvelope, validateSessionSettings } from "../fakes/contracts";

interface FakeSocket {
  url: string;
  readyState: number;
  binaryType: string;
  sent: Array<string | ArrayBuffer>;
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onerror: (() => void) | null;
  onclose: (() => void) | null;
  open(): void;
  emit(data: unknown): void;
}

const sockets: FakeSocket[] = [];

class FakeSocketClass {
  static readonly OPEN = 1;
  static readonly CONNECTING = 0;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readyState = FakeSocketClass.CONNECTING;
  binaryType = "blob";
  sent: Array<string | ArrayBuffer> = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    sockets.push(this as unknown as FakeSocket);
  }

  open(): void {
    this.readyState = FakeSocketClass.OPEN;
    this.onopen?.();
  }

  emit(data: unknown): void {
    this.onmessage?.({ data });
  }

  send(data: string | ArrayBuffer): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = FakeSocketClass.CLOSED;
    this.onclose?.();
  }
}

const globalScope = globalThis as unknown as { WebSocket?: unknown };
globalScope.WebSocket = FakeSocketClass;

const SETTINGS: SessionSettings = {
  settingsVersion: "0.1",
  practiceLanguageId: "english",
  coachingLanguageId: "english",
  scenarioId: "interview",
  scenarioPresetId: null,
  level: "beginner",
  coachingRoundTurns: 4,
  sessionLimitSeconds: 600,
  recordingRetention: false,
  consent: {
    consentVersion: "0.1",
    recordingRetentionGranted: false,
    recordingRetentionGrantedAt: null,
  },
};

const SESSION_ID = "ses_fake0000000001";
const CONNECTION_ID = "con_fake0000000001";
const TURN_ID = "trn_fake000000001";
const NEWER_TURN_ID = "trn_fake000000002";

function serverEvent(
  type: string,
  payload: Record<string, unknown>,
  options: { sequence: number; turnId?: string | null; connectionId?: string },
) {
  return {
    envelopeVersion: "0.1",
    direction: "server_to_client",
    type,
    sessionId: SESSION_ID,
    connectionId: options.connectionId ?? CONNECTION_ID,
    roundId: null,
    turnId: options.turnId ?? null,
    sequence: options.sequence,
    sampleTimeMs: null,
    emittedAt: new Date().toISOString(),
    payload,
  };
}

/** A manual clock, so no real timer is left running by a test. */
class ManualClock {
  private readonly handlers = new Map<number, { handler: () => void; delay: number }>();
  private nextId = 1;

  readonly setTimeout = (handler: () => void, delay = 0): number => {
    const id = this.nextId;
    this.nextId += 1;
    this.handlers.set(id, { handler, delay });
    return id;
  };

  readonly clearTimeout = (handle: number): void => {
    this.handlers.delete(handle);
  };

  /**
   * Run the callbacks that were scheduled with this delay.
   *
   * The reconnect backoff is 500, 1,000 and 2,000 ms, so the test asks for
   * those delays and the idle and call-limit watchdogs — 5,000 ms and
   * 540,000 ms — are never run.
   */
  runByDelay(delay: number): void {
    for (const [id, entry] of [...this.handlers]) {
      if (entry.delay !== delay) {
        continue;
      }
      this.handlers.delete(id);
      entry.handler();
    }
  }
}

interface Harness {
  client: CallClient;
  events: unknown[];
  binaries: { turnId: string; size: number }[];
  states: string[];
  clock: ManualClock;
}

type ClientOverrides = Partial<
  Pick<
    ConstructorParameters<typeof CallClient>[0],
    "getToken" | "onEvent" | "onBinary" | "onConnectionState"
  >
>;

function makeClient(overrides: ClientOverrides = {}): Harness {
  const events: unknown[] = [];
  const binaries: { turnId: string; size: number }[] = [];
  const states: string[] = [];
  const clock = new ManualClock();
  const client = new CallClient({
    url: "ws://localhost:8000/ws/call",
    settings: SETTINGS,
    sampleRateHz: 16000,
    getToken: async () => null,
    onEvent: (event) => events.push(event),
    onBinary: (data, turnId) => binaries.push({ turnId, size: data.byteLength }),
    onConnectionState: (state) => states.push(state),
    onLocalError: () => undefined,
    onServerError: () => undefined,
    onInterrupt: () => undefined,
    onWarning: () => undefined,
    onLimitReached: () => undefined,
    setTimeoutFn: clock.setTimeout,
    clearTimeoutFn: clock.clearTimeout,
    ...overrides,
  });
  return { client, events, binaries, states, clock };
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function latestSocket(): FakeSocket {
  return sockets[sockets.length - 1];
}

test("the start event is the first message and it is valid", async () => {
  sockets.length = 0;
  const { client, events } = makeClient();
  client.start();
  await flush();
  const socket = latestSocket();
  socket.open();
  await flush();

  expect(socket.sent.length).toBe(1);
  const envelope = JSON.parse(String(socket.sent[0]));
  expect(envelope.type).toBe("start");
  expect(envelope.direction).toBe("client_to_server");
  expect(envelope.envelopeVersion).toBe("0.1");
  expect(validateEnvelope(envelope)).toBe(true);
  expect(validateSessionSettings(envelope.payload.settings)).toBe(true);
  expect(envelope.payload.audio).toEqual({
    sampleRateHz: 16000,
    channels: 1,
    sampleFormat: "s16le",
  });
  // A guest call carries no token at all.
  expect(envelope.payload.auth).toBeUndefined();
  expect(events.length).toBe(0);
});

test("a caller's own token travels in the start event, never in the URL", async () => {
  sockets.length = 0;
  const { client } = makeClient({ getToken: async () => "the-callers-own-token" });
  client.start();
  await flush();
  const socket = latestSocket();
  socket.open();
  await flush();
  const envelope = JSON.parse(String(socket.sent[0]));
  expect(envelope.payload.auth).toEqual({ token: "the-callers-own-token" }); // secret-scan: allow
  expect(socket.url).not.toContain("token");
  expect(socket.url).not.toContain("the-callers-own-token");
});

test("binary frames are only sent after the server has answered, and only whole frames", async () => {
  sockets.length = 0;
  const { client } = makeClient();
  client.start();
  await flush();
  const socket = latestSocket();
  socket.open();
  await flush();

  const frame = new Uint8Array(1024);
  // Before the server's answer, nothing is sent.
  client.sendFrame(frame);
  expect(socket.sent.length).toBe(1);

  socket.emit(JSON.stringify(serverEvent("status", { state: "ready" }, { sequence: 0 })));
  client.sendFrame(frame);
  expect(socket.sent.length).toBe(2);
  expect(socket.sent[1]).toBeInstanceOf(ArrayBuffer);
  expect((socket.sent[1] as ArrayBuffer).byteLength).toBe(1024);

  // A frame that is not exactly 1,024 bytes is never sent.
  client.sendFrame(new Uint8Array(512));
  client.sendFrame(new Uint8Array(2048));
  expect(socket.sent.length).toBe(2);
});

test("the control events are sent in the frozen shape", async () => {
  sockets.length = 0;
  const { client } = makeClient();
  client.start();
  await flush();
  const socket = latestSocket();
  socket.open();
  await flush();
  socket.emit(JSON.stringify(serverEvent("status", { state: "ready" }, { sequence: 0 })));
  socket.emit(
    JSON.stringify(
      serverEvent("coach_text", { text: "Hello." }, { sequence: 1, turnId: TURN_ID }),
    ),
  );

  client.setMuted(true);
  client.retry(TURN_ID, "say it differently");
  client.coachingChoice("keep_talking");
  client.interrupt();
  client.close("learner_ended");

  const types = socket.sent.slice(1).map((raw) => JSON.parse(String(raw)).type);
  expect(types).toEqual(["mute", "retry", "coaching_choice", "interrupt", "end"]);
  for (const raw of socket.sent) {
    const envelope = JSON.parse(String(raw));
    expect(validateEnvelope(envelope)).toBe(true);
  }
  const [mute, retry, choice, interrupt, end] = socket.sent
    .slice(1)
    .map((raw) => JSON.parse(String(raw)));
  expect(mute.payload).toEqual({ muted: true });
  expect(retry.payload).toEqual({ turnId: TURN_ID, focus: "say it differently" });
  expect(choice.payload).toEqual({ choice: "keep_talking" });
  expect(interrupt.payload).toEqual({ reason: "learner_speech" });
  expect(end.payload).toEqual({ reason: "learner_ended" });
});

test("a duplicate sequence is applied once", async () => {
  sockets.length = 0;
  const { client, events } = makeClient();
  client.start();
  await flush();
  const socket = latestSocket();
  socket.open();
  await flush();
  const status = JSON.stringify(
    serverEvent("status", { state: "listening" }, { sequence: 0 }),
  );
  socket.emit(status);
  socket.emit(status);
  expect(events.length).toBe(1);
});

test("an event from a stale connection is dropped", async () => {
  sockets.length = 0;
  const { client, events } = makeClient();
  client.start();
  await flush();
  const socket = latestSocket();
  socket.open();
  await flush();
  // The first event establishes the connection.
  socket.emit(
    JSON.stringify(serverEvent("status", { state: "listening" }, { sequence: 0 })),
  );
  expect(events.length).toBe(1);
  // An event from another connection is dropped.
  socket.emit(
    JSON.stringify(
      serverEvent(
        "status",
        { state: "listening" },
        { sequence: 1, connectionId: "con_other00001" },
      ),
    ),
  );
  expect(events.length).toBe(1);
});

test("audio for a stale or fenced turn is never played", async () => {
  sockets.length = 0;
  const { client, binaries } = makeClient();
  client.start();
  await flush();
  const socket = latestSocket();
  socket.open();
  await flush();

  // The first coach turn, then a second one.
  socket.emit(
    JSON.stringify(
      serverEvent("coach_text", { text: "Hello." }, { sequence: 0, turnId: TURN_ID }),
    ),
  );
  socket.emit(
    JSON.stringify(
      serverEvent("coach_text", { text: "And more." }, { sequence: 1, turnId: NEWER_TURN_ID }),
    ),
  );
  socket.emit(
    JSON.stringify(
      serverEvent(
        "audio.frame.descriptor",
        {
          sampleRateHz: 16000,
          sampleFormat: "s16le",
          channels: 1,
          frameByteLength: 1024,
          firstSampleIndex: 0,
        },
        { sequence: 2, turnId: NEWER_TURN_ID },
      ),
    ),
  );
  socket.emit(new ArrayBuffer(1024));
  expect(binaries.length).toBe(1);
  expect(binaries[0].turnId).toBe(NEWER_TURN_ID);

  // A descriptor for the older turn is dropped, so it does not change the
  // attribution: the binary frames carry no turn id of their own, and they
  // belong to the last descriptor that was accepted.
  socket.emit(
    JSON.stringify(
      serverEvent(
        "audio.frame.descriptor",
        {
          sampleRateHz: 16000,
          sampleFormat: "s16le",
          channels: 1,
          frameByteLength: 1024,
          firstSampleIndex: 1024,
        },
        { sequence: 3, turnId: TURN_ID },
      ),
    ),
  );
  socket.emit(new ArrayBuffer(1024));
  expect(binaries.length).toBe(2);
  expect(binaries[1].turnId).toBe(NEWER_TURN_ID);

  // After an interrupt the turn is fenced: no more audio for it.
  client.interrupt();
  socket.emit(new ArrayBuffer(1024));
  expect(binaries.length).toBe(2);
});

test("an unexpected close reconnects with a new connection and a new start", async () => {
  sockets.length = 0;
  const { client, states, clock } = makeClient();
  client.start();
  await flush();
  expect(sockets.length).toBe(1);
  const first = latestSocket();
  first.open();
  await flush();
  expect(first.sent.length).toBe(1);

  // The connection drops without the client asking.
  first.readyState = 3;
  first.onclose?.();
  await flush();
  expect(states).toContain("reconnecting");

  // The backoff is real, so the new socket is opened by the clock.
  clock.runByDelay(500);
  await flush();
  expect(sockets.length).toBe(2);
  const second = latestSocket();
  second.open();
  await flush();
  // The new connection starts the call again — but it does not replay the
  // learner's audio, so no duplicate turn is created.
  expect(second.sent.length).toBe(1);
  const envelope = JSON.parse(String(second.sent[0]));
  expect(envelope.type).toBe("start");
  expect(validateEnvelope(envelope)).toBe(true);
});

test("the reconnect is bounded", async () => {
  sockets.length = 0;
  const { client, states, clock } = makeClient();
  client.start();
  await flush();
  const backoffs = [500, 1000, 2000];
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const socket = latestSocket();
    socket.readyState = 3;
    socket.onclose?.();
    await flush();
    for (const delay of backoffs) {
      clock.runByDelay(delay);
    }
    await flush();
  }
  // Three reconnects are allowed; the fourth failure gives up.
  expect(sockets.length).toBe(4);
  expect(states).toContain("failed");
});
