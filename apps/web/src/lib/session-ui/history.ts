/**
 * The history and recording routes — Phase 04.
 *
 * `prompts/parallel-G1/ADDENDUM.md` §B pins the four HTTP shapes:
 *
 * | Route | Success | Other |
 * |---|---|---|
 * | `GET /api/history` | `200 {"sessions":[…]}` newest first | guest/no token → `401` |
 * | `POST /api/consent` | `200 {…}` | withdrawing stops future retention |
 * | `GET /api/recordings/{id}` | `200 audio/wav` | someone else's or missing → `404` |
 * | `DELETE /api/recordings/{id}` | `204` | non-owner or a repeat → `404` |
 *
 * There is **no sample data** here. An empty list is an empty list.
 */

import { authHeaders } from "./http";

/** One completed session, as the history route returns it. */
export interface HistorySession {
  sessionId: string;
  recordedAt: string;
  practiceLanguageId: string;
  scenarioId: string;
  recordingId: string | null;
  turnCount: number;
  speakingTimeMs: number;
}

export type HistoryResult =
  | { kind: "list"; sessions: HistorySession[] }
  | { kind: "guest" }
  | { kind: "error"; message: string; advice: string };

/** Fetch the signed-in learner's sessions. */
export async function fetchHistory(
  httpBaseUrl: string,
  token: string | null,
): Promise<HistoryResult> {
  let response: Response;
  try {
    response = await fetch(`${httpBaseUrl}/api/history`, {
      method: "GET",
      headers: authHeaders(token),
      cache: "no-store",
    });
  } catch {
    return {
      kind: "error",
      message: "We could not reach the history service.",
      advice: "Check your connection and try again.",
    };
  }

  if (response.status === 401) {
    // Nobody is signed in. This is a real state, not a failure.
    return { kind: "guest" };
  }
  if (!response.ok) {
    return {
      kind: "error",
      message: "We could not load your past sessions.",
      advice: "Try again in a moment.",
    };
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return {
      kind: "error",
      message: "The history service sent something we could not read.",
      advice: "Try again in a moment.",
    };
  }
  const sessions = extractSessions(body);
  if (!sessions) {
    return {
      kind: "error",
      message: "The history service sent something we could not read.",
      advice: "Try again in a moment.",
    };
  }
  return { kind: "list", sessions };
}

function extractSessions(body: unknown): HistorySession[] | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const raw = (body as { sessions?: unknown }).sessions;
  if (!Array.isArray(raw)) {
    return null;
  }
  const sessions: HistorySession[] = [];
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null) {
      return null;
    }
    const record = entry as Record<string, unknown>;
    if (typeof record.sessionId !== "string" || typeof record.recordedAt !== "string") {
      return null;
    }
    sessions.push({
      sessionId: record.sessionId,
      recordedAt: record.recordedAt,
      practiceLanguageId:
        typeof record.practiceLanguageId === "string" ? record.practiceLanguageId : "",
      scenarioId: typeof record.scenarioId === "string" ? record.scenarioId : "",
      recordingId:
        typeof record.recordingId === "string" && record.recordingId.length > 0
          ? record.recordingId
          : null,
      turnCount: typeof record.turnCount === "number" ? record.turnCount : 0,
      speakingTimeMs:
        typeof record.speakingTimeMs === "number" ? record.speakingTimeMs : 0,
    });
  }
  return sessions;
}

/** The outcome of asking for a recording. */
export type RecordingResult =
  | { kind: "available"; url: string; revoke: () => void }
  | { kind: "unavailable" }
  | { kind: "error"; message: string };

/**
 * Fetch a recording.
 *
 * The route answers `404` for someone else's recording and for a missing
 * one, identically, so there is no existence leak. When the fetch works, a
 * replay control may be shown; when it does not, there must be no replay
 * control at all.
 */
export async function fetchRecording(
  httpBaseUrl: string,
  token: string | null,
  recordingId: string,
): Promise<RecordingResult> {
  let response: Response;
  try {
    response = await fetch(`${httpBaseUrl}/api/recordings/${encodeURIComponent(recordingId)}`, {
      method: "GET",
      headers: authHeaders(token),
      cache: "no-store",
    });
  } catch {
    return {
      kind: "error",
      message: "We could not reach the recording service.",
    };
  }
  if (response.status === 404) {
    return { kind: "unavailable" };
  }
  if (!response.ok) {
    return {
      kind: "error",
      message: "We could not load that recording.",
    };
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  return {
    kind: "available",
    url,
    revoke: () => URL.revokeObjectURL(url),
  };
}

/** The outcome of deleting a recording. */
export type DeleteResult =
  | { kind: "deleted" }
  | { kind: "missing" }
  | { kind: "error"; message: string };

/** Delete a recording. A repeat delete answers `404`, which is not an error. */
export async function deleteRecording(
  httpBaseUrl: string,
  token: string | null,
  recordingId: string,
): Promise<DeleteResult> {
  let response: Response;
  try {
    response = await fetch(`${httpBaseUrl}/api/recordings/${encodeURIComponent(recordingId)}`, {
      method: "DELETE",
      headers: authHeaders(token),
      cache: "no-store",
    });
  } catch {
    return {
      kind: "error",
      message: "We could not reach the recording service.",
    };
  }
  if (response.status === 204) {
    return { kind: "deleted" };
  }
  if (response.status === 404) {
    return { kind: "missing" };
  }
  return {
    kind: "error",
    message: "We could not delete that recording.",
  };
}

/** The outcome of recording the consent decision. */
export type ConsentResult = { kind: "saved" } | { kind: "not_saved"; message: string };

/**
 * Tell the service about the learner's recording decision.
 *
 * This is best effort: the flag also travels in the `start` event and the
 * service re-checks it when it writes, so a failed consent call never turns
 * into a silently kept recording.
 */
export async function postConsent(
  httpBaseUrl: string,
  token: string | null,
  recordingRetentionGranted: boolean,
): Promise<ConsentResult> {
  try {
    const response = await fetch(`${httpBaseUrl}/api/consent`, {
      method: "POST",
      headers: { ...authHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({
        consentVersion: "0.1",
        recordingRetentionGranted,
      }),
    });
    if (response.ok) {
      return { kind: "saved" };
    }
    return {
      kind: "not_saved",
      message:
        "We could not save that choice on the server. It still applies to this call.",
    };
  } catch {
    return {
      kind: "not_saved",
      message:
        "We could not save that choice on the server. It still applies to this call.",
    };
  }
}
