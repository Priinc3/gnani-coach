/**
 * The call state — Phase 04.
 *
 * One pure reducer holds everything the call screen shows. Keeping it pure
 * means the rules ("the status comes only from a `status` event", "the
 * transcript is transient and is cleared at the end", "the last round's
 * feedback is what the break shows") can be tested without a browser, a
 * socket or a server.
 */

import type { LocalError, PlainError } from "../transport/errors";
import type {
  RoundFeedbackPayload,
  StatusPayload,
  StatusState,
} from "../transport/types";
import type { MicFailure } from "../audio/capture";

/** Where the call is in its life. */
export type CallPhase = "idle" | "starting" | "live" | "ended" | "failed";

export interface CallState {
  phase: CallPhase;
  /** The last state a `status` event reported. */
  status: StatusState | null;
  /** The optional detail a `status` event carried. */
  statusDetail: string | null;
  /**
   * A learner-facing notice from the service, without its ``notice:``
   * prefix. It is **sticky**: a following status does not erase it, so
   * the sign-in fallback survives ``ready`` -> ``listening`` and the
   * not-saved notice is visible in the summary.
   */
  notice: string | null;
  /** True while the client is opening a new connection. */
  reconnecting: boolean;
  /** How long the call has been running, in milliseconds. */
  elapsedMs: number;
  /** The learner's microphone is off. */
  muted: boolean;
  /** The coach's voice is audible. */
  speakerOn: boolean;
  /** The transient transcript is visible. */
  transcriptVisible: boolean;
  /** The learner's speech in progress, transient. */
  partialTranscript: string;
  /** The learner's finished speech, transient. */
  transcript: string[];
  /** The coach's last line, transient. */
  coachText: string | null;
  /** The latest round feedback. */
  feedback: RoundFeedbackPayload | null;
  /** Every round of this session, for the summary. */
  rounds: RoundFeedbackPayload[];
  /** The turn the last round belongs to. */
  feedbackTurnId: string | null;
  /** A server error in plain words. */
  error: PlainError | null;
  /** A client-side failure. */
  localError: LocalError | null;
  /** The microphone could not be started. */
  micFailure: MicFailure | null;
  /** A warning that is worth showing, e.g. the nine-minute warning. */
  warning: string | null;
  /** True once the learner has interrupted the coach. */
  interrupted: boolean;
}

export const initialCallState: CallState = {
  phase: "idle",
  status: null,
  statusDetail: null,
  notice: null,
  reconnecting: false,
  elapsedMs: 0,
  muted: false,
  speakerOn: true,
  transcriptVisible: false,
  partialTranscript: "",
  transcript: [],
  coachText: null,
  feedback: null,
  rounds: [],
  feedbackTurnId: null,
  error: null,
  localError: null,
  micFailure: null,
  warning: null,
  interrupted: false,
};

export type CallAction =
  | { type: "start_requested" }
  | { type: "mic_failed"; failure: MicFailure }
  | { type: "status"; payload: StatusPayload }
  | { type: "transcript_partial"; text: string }
  | { type: "transcript_final"; text: string }
  | { type: "coach_text"; text: string }
  | { type: "round_feedback"; payload: RoundFeedbackPayload; turnId: string | null }
  | { type: "server_error"; error: PlainError }
  | { type: "local_error"; error: LocalError }
  | { type: "tick"; elapsedMs: number }
  | { type: "set_muted"; muted: boolean }
  | { type: "set_speaker"; on: boolean }
  | { type: "set_transcript_visible"; visible: boolean }
  | { type: "interrupted" }
  | { type: "warning"; message: string }
  | { type: "reconnecting"; reconnecting: boolean }
  | { type: "ended" }
  | { type: "reset" };

/** The prefix the service uses for a learner-facing notice inside `detail`. */
export const NOTICE_PREFIX = "notice:";

/** Split one `detail` into the ordinary detail and the notice. */
export function splitNotice(detail: string | null): {
  detail: string | null;
  notice: string | null;
} {
  if (!detail) {
    return { detail: null, notice: null };
  }
  const index = detail.indexOf(NOTICE_PREFIX);
  if (index === -1) {
    return { detail, notice: null };
  }
  const before = detail.slice(0, index).trim();
  const notice = detail.slice(index + NOTICE_PREFIX.length).trim();
  return { detail: before.length > 0 ? before : null, notice: notice.length > 0 ? notice : null };
}

/** The call reducer. */
export function callReducer(state: CallState, action: CallAction): CallState {
  switch (action.type) {
    case "start_requested":
      return {
        ...state,
        phase: "starting",
        status: null,
        statusDetail: null,
        notice: null,
        error: null,
        localError: null,
        micFailure: null,
        warning: null,
        elapsedMs: 0,
        transcript: [],
        partialTranscript: "",
        rounds: [],
        feedback: null,
        coachText: null,
      };

    case "mic_failed":
      return {
        ...state,
        phase: "failed",
        micFailure: action.failure,
      };

    case "status": {
      const status = action.payload.state;
      const rawDetail = action.payload.detail ?? null;
      const { detail, notice } = splitNotice(rawDetail);
      const stickyNotice = notice ?? state.notice;
      if (status === "ended") {
        return {
          ...state,
          status,
          statusDetail: detail,
          notice: stickyNotice,
          phase: "ended",
        };
      }
      if (status === "error") {
        return { ...state, status, statusDetail: detail, notice: stickyNotice };
      }
      if (status === "reconnecting") {
        return {
          ...state,
          status,
          statusDetail: detail,
          notice: stickyNotice,
          reconnecting: true,
        };
      }
      if (status === "heartbeat") {
        // A heartbeat carries no measurement and no state change.
        return state;
      }
      return {
        ...state,
        status,
        statusDetail: detail,
        notice: stickyNotice,
        phase: state.phase === "ended" ? state.phase : "live",
        reconnecting: false,
      };
    }

    case "transcript_partial":
      return { ...state, partialTranscript: action.text };

    case "transcript_final":
      return {
        ...state,
        partialTranscript: "",
        transcript: [...state.transcript, action.text],
      };

    case "coach_text":
      return { ...state, coachText: action.text };

    case "round_feedback":
      return {
        ...state,
        feedback: action.payload,
        feedbackTurnId: action.turnId,
        rounds: [...state.rounds, action.payload],
        phase: "live",
      };

    case "server_error":
      return { ...state, error: action.error };

    case "local_error":
      return { ...state, localError: action.error, phase: "failed" };

    case "tick":
      return { ...state, elapsedMs: action.elapsedMs };

    case "set_muted":
      return { ...state, muted: action.muted };

    case "set_speaker":
      return { ...state, speakerOn: action.on };

    case "set_transcript_visible":
      return { ...state, transcriptVisible: action.visible };

    case "interrupted":
      return { ...state, interrupted: true };

    case "warning":
      return { ...state, warning: action.message };

    case "reconnecting":
      return { ...state, reconnecting: action.reconnecting };

    case "ended":
      // The transcript is transient: it is cleared when the call ends.
      return {
        ...state,
        phase: "ended",
        transcript: [],
        partialTranscript: "",
      };

    case "reset":
      return { ...initialCallState };

    default:
      return state;
  }
}
