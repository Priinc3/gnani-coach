/**
 * The event envelope types — Phase 04.
 *
 * These mirror `packages/contracts/schemas/event-envelope.schema.json`
 * (frozen v0.1). The schema is the authority; this file is the typed view
 * of it that the client code uses, so a shape change shows up as a
 * typecheck error rather than a runtime surprise.
 */

/** The six events the client sends. */
export type ClientEventType =
  | "start"
  | "mute"
  | "end"
  | "interrupt"
  | "retry"
  | "coaching_choice";

/** The seven events the server sends. */
export type ServerEventType =
  | "status"
  | "transcript_partial"
  | "transcript_final"
  | "coach_text"
  | "round_feedback"
  | "error"
  | "audio.frame.descriptor";

export type EnvelopeType = ClientEventType | ServerEventType;

/** The envelope every message travels in. */
export interface Envelope<P = unknown> {
  envelopeVersion: "0.1";
  direction: "client_to_server" | "server_to_client";
  type: EnvelopeType;
  sessionId: string | null;
  connectionId: string | null;
  roundId: string | null;
  turnId: string | null;
  sequence: number;
  sampleTimeMs: number | null;
  emittedAt: string;
  payload: P;
}

/* ------------------------------------------------------------------ */
/* Client payloads                                                     */
/* ------------------------------------------------------------------ */

/** The audio format the client declares in `start`. */
export interface StartAudioFormat {
  sampleRateHz: number;
  channels: 1;
  sampleFormat: "s16le";
}

/** The consent block of the session settings. */
export interface ConsentBlock {
  consentVersion: "0.1";
  recordingRetentionGranted: boolean;
  recordingRetentionGrantedAt: string | null;
}

/**
 * The session settings, in the shape of
 * `packages/contracts/schemas/session-settings.schema.json`.
 */
export interface SessionSettings {
  settingsVersion: "0.1";
  practiceLanguageId: string;
  coachingLanguageId: string;
  scenarioId: string;
  scenarioPresetId?: string | null;
  customTopic?: { text: string; persisted: false };
  level: "beginner" | "intermediate" | "advanced";
  coachingRoundTurns: number;
  sessionLimitSeconds: number;
  recordingRetention: boolean;
  consent: ConsentBlock;
}

export interface StartPayload {
  audio: StartAudioFormat;
  settings: SessionSettings;
  auth?: { token: string };
}

export interface MutePayload {
  muted: boolean;
}

export type EndReason = "learner_ended" | "time_limit" | "client_gone";

export interface EndPayload {
  reason: EndReason;
}

export interface InterruptPayload {
  reason: "learner_speech";
}

export interface RetryPayload {
  turnId: string;
  focus?: string;
}

export type CoachingChoice = "keep_talking" | "coach_now" | "skip_feedback";

export interface CoachingChoicePayload {
  choice: CoachingChoice;
}

/* ------------------------------------------------------------------ */
/* Server payloads                                                     */
/* ------------------------------------------------------------------ */

/** Every state the `status` event can carry. */
export type StatusState =
  | "connecting"
  | "ready"
  | "listening"
  | "thinking"
  | "speaking"
  | "coaching"
  | "heartbeat"
  | "reconnecting"
  | "ended"
  | "error";

export interface StatusPayload {
  state: StatusState;
  detail?: string;
  elapsedMs?: number;
}

export interface TranscriptPayload {
  text: string;
  segmentId?: string;
}

/** Phase 19: a short spoken reaction is not the real reply. */
export type CoachAudioKind = "reply" | "backchannel";

export interface CoachTextPayload {
  text: string;
  kind?: CoachAudioKind;
}

/** The metric keys the evidence chips may carry. */
export type MetricKey =
  | "pause.longest_ms"
  | "pause.count"
  | "filler.count"
  | "speech.rate_wpm"
  | "speech.active_rate_wpm"
  | "turn.duration_ms";

/** The status every measurement carries. */
export type MeasurementStatus = "available" | "unavailable" | "insufficient_evidence";

export type EvidenceUnit = "milliseconds" | "count" | "words_per_minute";

export interface EvidenceEntry {
  metricKey: MetricKey;
  status: MeasurementStatus;
  value?: number | null;
  unit?: EvidenceUnit | null;
}

export interface RoundFeedbackPayload {
  strengths: string[];
  improvements: string[];
  languageNotes?: string[];
  evidence?: EvidenceEntry[];
}

/** The frozen error shape, inlined in the event envelope. */
export interface ErrorPayload {
  errorVersion: "0.1";
  code: string;
  category:
    | "invalid_request"
    | "unauthenticated"
    | "forbidden"
    | "not_found"
    | "conflict"
    | "rate_limited"
    | "provider_unavailable"
    | "timeout"
    | "cancelled"
    | "not_available"
    | "internal";
  message: string;
  retryable: boolean;
  correlationId: string;
  occurredAt: string;
}

export interface AudioFrameDescriptorPayload {
  sampleRateHz: number;
  sampleFormat: "s16le";
  channels: 1;
  frameByteLength: number;
  firstSampleIndex: number;
  /** Phase 19: defaults to "reply" when absent. */
  kind?: CoachAudioKind;
}

/** A server event with its payload typed. */
export type ServerEvent =
  | (Envelope<StatusPayload> & { type: "status" })
  | (Envelope<TranscriptPayload> & { type: "transcript_partial" })
  | (Envelope<TranscriptPayload> & { type: "transcript_final" })
  | (Envelope<CoachTextPayload> & { type: "coach_text" })
  | (Envelope<RoundFeedbackPayload> & { type: "round_feedback" })
  | (Envelope<ErrorPayload> & { type: "error" })
  | (Envelope<AudioFrameDescriptorPayload> & { type: "audio.frame.descriptor" });
