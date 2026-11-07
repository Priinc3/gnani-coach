/**
 * The call reducer and the error wording — Phase 04.
 *
 * Two plain-word promises are checked here:
 *
 * - the **status comes only from a `status` event**, and a heartbeat
 *   changes nothing;
 * - the **transcript is transient** and is cleared when the call ends;
 * - every error category has plain words, and the **retry rule comes from
 *   the shape**.
 */

import { expect, test } from "@playwright/test";

import { callReducer, initialCallState } from "../../src/lib/session-ui/callState";
import { describeError, describeLocalError } from "../../src/lib/transport/errors";
import type { ErrorPayload } from "../../src/lib/transport/types";

const CATEGORIES: ErrorPayload["category"][] = [
  "invalid_request",
  "unauthenticated",
  "forbidden",
  "not_found",
  "conflict",
  "rate_limited",
  "provider_unavailable",
  "timeout",
  "cancelled",
  "not_available",
  "internal",
];

function errorPayload(
  category: ErrorPayload["category"],
  retryable: boolean,
): ErrorPayload {
  return {
    errorVersion: "0.1",
    code: `${category}.test`,
    category,
    message: "Something happened.",
    retryable,
    correlationId: "cor_fixture000001",
    occurredAt: new Date().toISOString(),
  };
}

test("the status comes only from a status event", () => {
  let state = callReducer(initialCallState, { type: "start_requested" });
  expect(state.phase).toBe("starting");
  expect(state.status).toBeNull();

  state = callReducer(state, { type: "status", payload: { state: "listening" } });
  expect(state.status).toBe("listening");
  expect(state.phase).toBe("live");

  // A heartbeat carries no measurement and no state change.
  const before = state;
  state = callReducer(state, { type: "status", payload: { state: "heartbeat" } });
  expect(state).toBe(before);
});

test("the reconnecting and ended states are carried", () => {
  let state = callReducer(initialCallState, { type: "status", payload: { state: "reconnecting" } });
  expect(state.reconnecting).toBe(true);
  state = callReducer(state, { type: "status", payload: { state: "ended" } });
  expect(state.phase).toBe("ended");
});

test("the transcript is transient and is cleared when the call ends", () => {
  let state = callReducer(initialCallState, { type: "transcript_final", text: "Hello there." });
  state = callReducer(state, { type: "transcript_partial", text: "Hello" });
  expect(state.transcript).toEqual(["Hello there."]);
  expect(state.partialTranscript).toBe("Hello");

  state = callReducer(state, { type: "ended" });
  expect(state.transcript).toEqual([]);
  expect(state.partialTranscript).toBe("");
});

test("every round feedback is kept for the summary", () => {
  const payload = { strengths: ["Good."], improvements: ["Try again."] };
  let state = callReducer(initialCallState, {
    type: "round_feedback",
    payload,
    turnId: "trn_fixture00001",
  });
  expect(state.feedback).toEqual(payload);
  expect(state.rounds.length).toBe(1);
  state = callReducer(state, {
    type: "round_feedback",
    payload,
    turnId: "trn_fixture00002",
  });
  expect(state.rounds.length).toBe(2);
});

test("every error category has plain words and a retry rule", () => {
  for (const category of CATEGORIES) {
    const plain = describeError(errorPayload(category, true));
    expect(plain.title.length).toBeGreaterThan(0);
    expect(plain.advice.length).toBeGreaterThan(0);
    // The retry rule is the shape's, never the client's guess.
    expect(plain.retryable).toBe(true);
    expect(plain.message).toBe("Something happened.");
  }
});

test("a client mistake is never offered as retryable", () => {
  for (const category of [
    "invalid_request",
    "unauthenticated",
    "forbidden",
    "not_found",
    "conflict",
    "not_available",
  ] as const) {
    const plain = describeError(errorPayload(category, false));
    expect(plain.retryable).toBe(false);
  }
});

test("the local failures have plain words too", () => {
  for (const kind of [
    "offline",
    "socket_failed",
    "socket_closed",
    "mic_unavailable",
    "unsupported_browser",
  ] as const) {
    const plain = describeLocalError(kind);
    expect(plain.title.length).toBeGreaterThan(0);
    expect(plain.message.length).toBeGreaterThan(0);
    expect(plain.advice.length).toBeGreaterThan(0);
  }
  expect(describeLocalError("unsupported_browser").retryable).toBe(false);
  expect(describeLocalError("offline").retryable).toBe(true);
});
