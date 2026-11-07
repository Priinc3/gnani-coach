/**
 * The fake voice server — Phase 04.
 *
 * It speaks the frozen envelope of `docs/contracts/call-transport.md` over
 * a WebSocket the browser opens to `VOICE_WS_URL`, and it records every
 * message the client sends so the tests can check them.
 *
 * The server is installed with Playwright's `page.routeWebSocket`, so no
 * real service, no port and no credential is needed: the route answers the
 * browser's socket directly.
 *
 * Every scenario is a **fixture**: the tests that use it are labelled as
 * fixture tests, and nothing here is evidence about the real service.
 */

import type { Page } from "@playwright/test";

/** The scenarios the fake server can play. */
export type FakeScenario =
  /** ready → transcript → coach text → coach audio → round feedback. */
  | "happy"
  /** ready → transcript → the coach starts speaking, and then stops. */
  | "speaking"
  /** The coach starts speaking and the learner speaks over it. */
  | "interrupted"
  /** The service answers with the frozen error envelope. */
  | "server-error"
  /** The first connection gets a retryable error; the next one works. */
  | "recoverable"
  /** The service closes the socket right after the start event. */
  | "disconnect"
  /** The service never answers the start event. */
  | "hanging"
  /** A coach text for a new turn, then a descriptor for an older turn. */
  | "stale-turn"
  /** The same envelope is sent twice. */
  | "duplicate"
  /** ready and then nothing: used for the "still connecting" state. */
  | "silent";

/** The ids the fake server mints. They match the frozen id patterns. */
export const FAKE_IDS = {
  sessionId: "ses_fake0000000001",
  connectionId: "con_fake0000000001",
  roundId: "rnd_fake00000001",
  turnId: "trn_fake000000001",
  olderTurnId: "trn_fake000000000",
};

interface Envelope {
  envelopeVersion: string;
  direction: string;
  type: string;
  sessionId: string | null;
  connectionId: string | null;
  roundId: string | null;
  turnId: string | null;
  sequence: number;
  sampleTimeMs: number | null;
  emittedAt: string;
  payload: Record<string, unknown>;
}

export interface FakeVoiceServer {
  /** Every JSON envelope the client sent, in order. */
  readonly sent: Envelope[];
  /** The byte length of every binary frame the client sent. */
  readonly binaryFrameSizes: number[];
  /** Wait until the client has sent an envelope of this type. */
  waitFor(type: string, timeoutMs?: number): Promise<Envelope>;
  /** The envelopes of one type the client sent. */
  ofType(type: string): Envelope[];
}

function serverEnvelope(
  type: string,
  payload: Record<string, unknown>,
  context: {
    sequence: number;
    turnId?: string | null;
    roundId?: string | null;
  },
): Envelope {
  return {
    envelopeVersion: "0.1",
    direction: "server_to_client",
    type,
    sessionId: FAKE_IDS.sessionId,
    connectionId: FAKE_IDS.connectionId,
    roundId: context.roundId ?? null,
    turnId: context.turnId ?? null,
    sequence: context.sequence,
    sampleTimeMs: null,
    emittedAt: new Date().toISOString(),
    payload,
  };
}

/** 16 kHz mono s16le silence, 3,584 bytes — one observed provider chunk. */
function fakeAudioChunk(bytes: number): Buffer {
  const buffer = Buffer.alloc(bytes);
  for (let index = 0; index < bytes; index += 2) {
    buffer.writeInt16LE(0, index);
  }
  return buffer;
}

/**
 * Install the fake voice server on the page.
 *
 * The route matches the voice service URL the browser uses.
 */
export async function installFakeVoiceServer(
  page: Page,
  scenario: FakeScenario,
): Promise<FakeVoiceServer> {
  const sent: Envelope[] = [];
  const binaryFrameSizes: number[] = [];
  let sequence = 0;

  const server = {
    sent,
    binaryFrameSizes,
    ofType(type: string) {
      return sent.filter((envelope) => envelope.type === type);
    },
    async waitFor(type: string, timeoutMs = 10_000): Promise<Envelope> {
      const deadline = Date.now() + timeoutMs;
      for (;;) {
        const found = sent.find((envelope) => envelope.type === type);
        if (found) {
          return found;
        }
        if (Date.now() > deadline) {
          throw new Error(`the client never sent a "${type}" event`);
        }
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
    },
  };

  await page.routeWebSocket(/ws\/call$/, (ws) => {
    ws.onMessage((message) => {
      if (typeof message === "string") {
        let envelope: Envelope;
        try {
          envelope = JSON.parse(message) as Envelope;
        } catch {
          return;
        }
        sent.push(envelope);
        if (envelope.type === "start") {
          const startCount = sent.filter((entry) => entry.type === "start").length;
          playScenario(ws, scenario, (type, payload, turnId) => {
            sequence += 1;
            ws.send(
              JSON.stringify(
                serverEnvelope(type, payload, {
                  sequence,
                  turnId: turnId ?? null,
                  roundId: type === "round_feedback" ? FAKE_IDS.roundId : null,
                }),
              ),
            );
          }, startCount);
        }
        return;
      }
      // A binary frame: the client sends raw PCM, never a container.
      binaryFrameSizes.push(message.length);
    });
  });

  return server;
}

/** The gap between two steps of a fixture scenario, in milliseconds. */
const STEP_MS = 150;

type Emit = (
  type: string,
  payload: Record<string, unknown>,
  turnId?: string | null,
) => void;

function playScenario(
  ws: {
    send: (message: string | Buffer) => void;
    close: (options?: { code?: number; reason?: string }) => Promise<void>;
  },
  scenario: FakeScenario,
  emit: Emit,
  startCount: number,
): void {
  /** Run a step after a short delay, so every state is observable. */
  const later = (delay: number, step: () => void) => {
    setTimeout(step, delay);
  };

  if (scenario === "disconnect") {
    void ws.close({ code: 1011, reason: "fixture_disconnect" });
    return;
  }

  if (scenario === "server-error") {
    emit("error", {
      errorVersion: "0.1",
      code: "provider.unavailable",
      category: "provider_unavailable",
      message: "The speech service is not answering right now.",
      retryable: true,
      correlationId: "cor_fixture000001",
      occurredAt: new Date().toISOString(),
    });
    return;
  }

  if (scenario === "recoverable") {
    if (startCount === 1) {
      // The first attempt fails with a retryable error; the second one works.
      emit("error", {
        errorVersion: "0.1",
        code: "provider.unavailable",
        category: "provider_unavailable",
        message: "The speech service is not answering right now.",
        retryable: true,
        correlationId: "cor_fixture000001",
        occurredAt: new Date().toISOString(),
      });
      return;
    }
  }

  if (scenario === "hanging") {
    // The service never answers: the client shows that it is still
    // connecting.
    return;
  }

  emit("status", { state: "ready" });
  later(STEP_MS, () => emit("status", { state: "listening" }));

  if (scenario === "silent") {
    return;
  }

  if (scenario === "stale-turn") {
    // A coach turn, then a descriptor for an **older** turn: the client
    // must drop the stale one and keep the current turn.
    later(STEP_MS * 2, () =>
      emit("coach_text", { text: "That is a clear answer." }, FAKE_IDS.turnId),
    );
    later(STEP_MS * 3, () => {
      emit(
        "audio.frame.descriptor",
        {
          sampleRateHz: 16000,
          sampleFormat: "s16le",
          channels: 1,
          frameByteLength: 3584,
          firstSampleIndex: 0,
        },
        FAKE_IDS.turnId,
      );
      ws.send(fakeAudioChunk(3584));
    });
    later(STEP_MS * 4, () =>
      emit("coach_text", { text: "And one more thing." }, FAKE_IDS.olderTurnId),
    );
    return;
  }

  if (scenario === "duplicate") {
    const transcript = { text: "I have led teams for six years." };
    later(STEP_MS * 2, () => emit("transcript_partial", { text: "I have led teams for" }));
    later(STEP_MS * 3, () => emit("transcript_final", transcript));
    later(STEP_MS * 4, () => emit("transcript_final", transcript));
    later(STEP_MS * 5, () => emit("status", { state: "thinking" }));
    const coachText = { text: "That is a strong opening." };
    later(STEP_MS * 6, () => emit("coach_text", coachText, FAKE_IDS.turnId));
    later(STEP_MS * 7, () => emit("coach_text", coachText, FAKE_IDS.turnId));
    return;
  }

  // The happy path.
  later(STEP_MS * 2, () => emit("transcript_partial", { text: "I have led teams for" }));
  later(STEP_MS * 3, () =>
    emit("transcript_final", { text: "I have led teams for six years." }),
  );
  later(STEP_MS * 4, () => emit("status", { state: "thinking" }));
  later(STEP_MS * 5, () =>
    emit("coach_text", { text: "That is a strong opening." }, FAKE_IDS.turnId),
  );
  later(STEP_MS * 6, () => emit("status", { state: "speaking" }));
  later(STEP_MS * 7, () => {
    emit(
      "audio.frame.descriptor",
      {
        sampleRateHz: 16000,
        sampleFormat: "s16le",
        channels: 1,
        frameByteLength: 3584,
        firstSampleIndex: 0,
      },
      FAKE_IDS.turnId,
    );
    ws.send(fakeAudioChunk(3584));
    ws.send(fakeAudioChunk(1024));
  });

  if (scenario === "speaking") {
    // The coach keeps talking: the call screen shows the speaking state.
    return;
  }

  if (scenario === "interrupted") {
    // The learner speaks over the coach: the client interrupts, the turn
    // is fenced and the audio stops.
    later(STEP_MS * 9, () => emit("transcript_partial", { text: "I have led teams for" }));
    return;
  }

  later(STEP_MS * 8, () => emit("status", { state: "coaching" }));
  later(STEP_MS * 9, () =>
    emit(
      "round_feedback",
      {
        strengths: ["You opened with the outcome, which is easy to follow."],
        improvements: [
          "Try pausing a beat before your second point so it lands.",
          "One number about the team would make it concrete.",
        ],
        languageNotes: ["Your pace was steady throughout the answer."],
        evidence: [
          {
            metricKey: "pause.longest_ms",
            status: "available",
            value: 1180,
            unit: "milliseconds",
          },
          { metricKey: "pause.count", status: "available", value: 3, unit: "count" },
          {
            metricKey: "filler.count",
            status: "insufficient_evidence",
            value: null,
            unit: null,
          },
          {
            metricKey: "speech.rate_wpm",
            status: "available",
            value: 112,
            unit: "words_per_minute",
          },
        ],
      },
      FAKE_IDS.turnId,
    ),
  );
}
