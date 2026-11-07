/**
 * The session-UI helpers — Phase 04.
 *
 * The glue between the browser and the voice service: the access-token
 * adapter, the HTTP base URL, the history routes, the plain-word feedback
 * helpers and the call state.
 */

export {
  getCallAccessToken,
  setRecordingRetentionConsent,
  subscribeToSignOut,
} from "./accessToken";
export { authHeaders, deriveVoiceHttpUrl } from "./http";
export {
  deleteRecording,
  fetchHistory,
  fetchRecording,
  postConsent,
  type DeleteResult,
  type HistoryResult,
  type HistorySession,
  type RecordingResult,
} from "./history";
export {
  compareAttempts,
  describeEvidence,
  describeMetric,
  FILLER_REASON,
  formatClock,
  formatMetricValue,
  formatSpokenDuration,
  insufficientReason,
  METRIC_LABELS,
  unavailableReason,
  type ComparisonRow,
  type MetricView,
} from "./feedback";
export { callReducer, initialCallState } from "./callState";
export type { CallAction, CallPhase, CallState } from "./callState";
export { useCallSession } from "./useCallSession";
export type { CallSession, UseCallSessionOptions } from "./useCallSession";
