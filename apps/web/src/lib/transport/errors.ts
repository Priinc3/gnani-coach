/**
 * Errors in plain words — Phase 04.
 *
 * Every `error` category in the frozen error shape gets a plain-word
 * headline and a plain-word next step, and the **retry rule comes from the
 * shape**: `retryable` is true only for genuinely transient conditions, so a
 * client mistake is never offered as "try again".
 *
 * The service's own `message` is already written for the learner and is
 * shown when it arrives; the category decides the headline and the advice.
 */

import type { ErrorPayload } from "./types";

export interface PlainError {
  category: ErrorPayload["category"];
  /** The stable machine code. Never shown to the learner. */
  code: string;
  /** A short plain-word headline. */
  title: string;
  /** The plain-word message: the service's own when it sent one. */
  message: string;
  /** What to do next, in plain words. */
  advice: string;
  /** True only when the shape says retrying could genuinely succeed. */
  retryable: boolean;
  /** The correlation id, for support. Shown small, never as the headline. */
  correlationId: string;
}

const CATEGORY_COPY: Record<
  ErrorPayload["category"],
  { title: string; fallback: string; advice: string }
> = {
  invalid_request: {
    title: "That request was not valid.",
    fallback: "We could not understand that request.",
    advice: "Start a new call and set it up again.",
  },
  unauthenticated: {
    title: "Your sign-in has expired.",
    fallback: "We could not confirm who you are.",
    advice: "Sign in again, then start a new call.",
  },
  forbidden: {
    title: "You do not have access to that.",
    fallback: "This action is not allowed for this account.",
    advice: "Use the account that owns it, or ask for access.",
  },
  not_found: {
    title: "We could not find that.",
    fallback: "That item no longer exists.",
    advice: "Go back and choose it again.",
  },
  conflict: {
    title: "That is already in progress.",
    fallback: "Something else is already running.",
    advice: "Wait for it to finish, then try again.",
  },
  rate_limited: {
    title: "Too many requests at once.",
    fallback: "We are receiving too many requests.",
    advice: "Wait a few seconds and try again.",
  },
  provider_unavailable: {
    title: "The speech service is having trouble.",
    fallback: "The speech service is not answering right now.",
    advice: "Try again in a moment. Nothing was saved.",
  },
  timeout: {
    title: "That took too long.",
    fallback: "The service did not answer in time.",
    advice: "Try again — the call did not start.",
  },
  cancelled: {
    title: "That was cancelled.",
    fallback: "The request was cancelled.",
    advice: "Start again whenever you like.",
  },
  not_available: {
    title: "Live calling is not available yet.",
    fallback: "This part of the service is still being built.",
    advice: "There is nothing to retry — this build cannot make the call.",
  },
  internal: {
    title: "Something went wrong on our side.",
    fallback: "We hit an unexpected problem.",
    advice: "Try again. If it keeps happening, check the service status.",
  },
};

/** Turn the frozen error payload into something a learner can read. */
export function describeError(payload: ErrorPayload): PlainError {
  const copy = CATEGORY_COPY[payload.category] ?? CATEGORY_COPY.internal;
  const serviceMessage = payload.message?.trim();
  return {
    category: payload.category,
    code: payload.code,
    title: copy.title,
    message: serviceMessage && serviceMessage.length > 0 ? serviceMessage : copy.fallback,
    advice: copy.advice,
    // The retry rule is the shape's, never the client's guess.
    retryable: payload.retryable === true,
    correlationId: payload.correlationId,
  };
}

/** The client-side failures that never reach the server. */
export type LocalErrorKind =
  | "offline"
  | "socket_failed"
  | "socket_closed"
  | "mic_unavailable"
  | "unsupported_browser";

export interface LocalError {
  kind: LocalErrorKind;
  title: string;
  message: string;
  advice: string;
  retryable: boolean;
}

export function describeLocalError(kind: LocalErrorKind): LocalError {
  switch (kind) {
    case "offline":
      return {
        kind,
        title: "You are offline.",
        message: "This device has no internet connection right now.",
        advice: "Reconnect, then start the call again.",
        retryable: true,
      };
    case "socket_failed":
      return {
        kind,
        title: "We could not reach the coach.",
        message: "The connection to the voice service could not be opened.",
        advice: "Check your connection and try again.",
        retryable: true,
      };
    case "socket_closed":
      return {
        kind,
        title: "The call was disconnected.",
        message: "The connection to the voice service closed unexpectedly.",
        advice: "Try again — you can start a new call.",
        retryable: true,
      };
    case "mic_unavailable":
      return {
        kind,
        title: "We could not use your microphone.",
        message: "The microphone could not be started.",
        advice: "Check your microphone, then try again.",
        retryable: true,
      };
    case "unsupported_browser":
      return {
        kind,
        title: "This browser cannot run a live call.",
        message: "Live calling needs a recent browser with microphone and AudioWorklet support.",
        advice: "Try a recent version of Chrome, Edge, Safari or Firefox.",
        retryable: false,
      };
  }
}
