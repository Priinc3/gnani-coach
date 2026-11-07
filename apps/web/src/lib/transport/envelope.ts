/**
 * Building client events — Phase 04.
 *
 * Every message the client sends is an envelope of the frozen shape
 * (`packages/contracts/schemas/event-envelope.schema.json`). This module is
 * the only place that builds one, so the rules — `direction`, the
 * per-connection `sequence`, the null-until-known ids, the informational
 * `emittedAt` — are written down once.
 */

import type {
  ClientEventType,
  CoachingChoice,
  EndReason,
  Envelope,
  SessionSettings,
  StartPayload,
} from "./types";

export interface EnvelopeContext {
  /** The client's monotonic per-connection counter. */
  sequence: number;
  /** The session id, once the server has named one. */
  sessionId?: string | null;
  /** The connection id, once the server has named one. */
  connectionId?: string | null;
  /** The current round, when known. */
  roundId?: string | null;
  /** The turn the event belongs to, when it belongs to one. */
  turnId?: string | null;
}

/** Build a `client_to_server` envelope. */
export function buildClientEnvelope<P>(
  type: ClientEventType,
  payload: P,
  context: EnvelopeContext,
): Envelope<P> {
  return {
    envelopeVersion: "0.1",
    direction: "client_to_server",
    type,
    sessionId: context.sessionId ?? null,
    connectionId: context.connectionId ?? null,
    roundId: context.roundId ?? null,
    turnId: context.turnId ?? null,
    sequence: context.sequence,
    sampleTimeMs: null,
    emittedAt: new Date().toISOString(),
    payload,
  };
}

/** Build the `start` event. It is always the first event of a connection. */
export function buildStartEnvelope(
  payload: StartPayload,
  context: EnvelopeContext,
): Envelope<StartPayload> {
  return buildClientEnvelope("start", payload, context);
}

/* ------------------------------------------------------------------ */
/* Session settings validation                                         */
/* ------------------------------------------------------------------ */

const ID_PATTERN = /^[a-z][a-z0-9-]{1,31}$/;
const LEVELS = new Set(["beginner", "intermediate", "advanced"]);

export interface SettingsValidation {
  ok: boolean;
  problems: string[];
}

/**
 * Check the session settings against the frozen session-settings shape.
 *
 * The check mirrors `packages/contracts/schemas/session-settings.schema.json`
 * — including its cross-field rules — so a bad setting is caught on the
 * device instead of being refused by the service after the call started.
 */
export function validateSessionSettings(settings: SessionSettings): SettingsValidation {
  const problems: string[] = [];

  if (settings.settingsVersion !== "0.1") {
    problems.push("The settings version is not supported.");
  }
  for (const [name, value] of [
    ["practiceLanguageId", settings.practiceLanguageId],
    ["coachingLanguageId", settings.coachingLanguageId],
    ["scenarioId", settings.scenarioId],
  ] as const) {
    if (!ID_PATTERN.test(value)) {
      problems.push(`${name} is not a valid catalog id.`);
    }
  }
  if (settings.scenarioPresetId != null && !ID_PATTERN.test(settings.scenarioPresetId)) {
    problems.push("scenarioPresetId is not a valid catalog id.");
  }
  if (!LEVELS.has(settings.level)) {
    problems.push("The level is not one of the three supported levels.");
  }
  if (
    !Number.isInteger(settings.coachingRoundTurns) ||
    settings.coachingRoundTurns < 1 ||
    settings.coachingRoundTurns > 8
  ) {
    problems.push("A coaching round must be between 1 and 8 learner turns.");
  }
  if (
    !Number.isInteger(settings.sessionLimitSeconds) ||
    settings.sessionLimitSeconds < 60 ||
    settings.sessionLimitSeconds > 600
  ) {
    problems.push("A call may last between 60 and 600 seconds.");
  }
  if (typeof settings.recordingRetention !== "boolean") {
    problems.push("recordingRetention must be true or false.");
  }
  if (settings.consent?.consentVersion !== "0.1") {
    problems.push("The consent version is not supported.");
  }
  if (typeof settings.consent?.recordingRetentionGranted !== "boolean") {
    problems.push("recordingRetentionGranted must be true or false.");
  }
  if (
    settings.consent?.recordingRetentionGranted === true &&
    typeof settings.consent?.recordingRetentionGrantedAt !== "string"
  ) {
    problems.push("A granted recording permission needs the time it was granted.");
  }
  if (
    settings.consent?.recordingRetentionGranted === false &&
    settings.consent?.recordingRetentionGrantedAt !== null
  ) {
    problems.push("A recording permission that was not granted cannot have a time.");
  }
  if (settings.recordingRetention === true && settings.consent?.recordingRetentionGranted !== true) {
    problems.push("Keeping the recording needs the learner's permission.");
  }

  // The custom topic exists only for the custom scenario, and is never
  // persisted.
  if (settings.scenarioId === "custom") {
    const topic = settings.customTopic;
    if (!topic) {
      problems.push("The custom topic scenario needs a topic.");
    } else if (topic.persisted !== false) {
      problems.push("The custom topic is never persisted.");
    } else if (topic.text.trim().length === 0) {
      problems.push("The custom topic cannot be empty.");
    } else if (topic.text.length > 200) {
      problems.push("The custom topic can be at most 200 characters.");
    }
  } else if (settings.customTopic !== undefined) {
    problems.push("A custom topic is only allowed for the custom scenario.");
  }

  return { ok: problems.length === 0, problems };
}

/** The `start` payload for a set of settings and an optional access token. */
export function buildStartPayload(
  settings: SessionSettings,
  token: string | null,
  sampleRateHz: number,
): StartPayload {
  const payload: StartPayload = {
    audio: { sampleRateHz, channels: 1, sampleFormat: "s16le" },
    settings,
  };
  if (token) {
    payload.auth = { token };
  }
  return payload;
}

/** The `end` reason for a call the learner finished. */
export const LEARNER_ENDED: EndReason = "learner_ended";
/** The `end` reason for a call that hit the product cap. */
export const TIME_LIMIT: EndReason = "time_limit";
/** The `end` reason for a call the client gave up on. */
export const CLIENT_GONE: EndReason = "client_gone";

/** The three coaching choices in the frozen payload. */
export const COACHING_CHOICES: CoachingChoice[] = [
  "keep_talking",
  "coach_now",
  "skip_feedback",
];
