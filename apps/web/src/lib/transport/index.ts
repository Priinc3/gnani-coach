/**
 * The transport layer — Phase 04.
 *
 * One WebSocket carries the whole call, in both directions. See
 * `docs/contracts/call-transport.md`.
 */

export { CallClient } from "./client";
export type {
  CallClientOptions,
  ConnectionState,
} from "./client";
export {
  CALL_LIMIT_MS,
  CALL_WARNING_MS,
  IDLE_TIMEOUT_MS,
  MAX_RECONNECT_ATTEMPTS,
  RECONNECT_DELAYS_MS,
} from "./client";
export {
  buildClientEnvelope,
  buildStartEnvelope,
  buildStartPayload,
  validateSessionSettings,
  COACHING_CHOICES,
  CLIENT_GONE,
  LEARNER_ENDED,
  TIME_LIMIT,
} from "./envelope";
export type { EnvelopeContext, SettingsValidation } from "./envelope";
export { describeError, describeLocalError } from "./errors";
export type { LocalError, LocalErrorKind, PlainError } from "./errors";
export { Fence, TURN_BOUND_EVENT_TYPES } from "./fencing";
export type { FenceEvent, FenceRejection, FenceResult } from "./fencing";
export type * from "./types";
