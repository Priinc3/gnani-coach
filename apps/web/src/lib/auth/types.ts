/**
 * The session vocabulary.
 *
 * **Phase 06 owns this tree.** The names are the frozen ones: the
 * `SessionState` shape is what the rest of the app reads, and it does
 * not change.
 */

/** `guest` means: no verified session. Not "signed out by error". */
export type SessionStatus = "loading" | "guest" | "authenticated";

export interface SessionState {
  /** `guest` means: no verified session. Not "signed out by error". */
  status: SessionStatus;
  /** The opaque user id, or null for a guest. Never an email address. */
  userId: string | null;
  /** Whether the learner opted in to keeping recordings on this device. */
  recordingRetention: boolean;
}

/**
 * The guest state.
 *
 * A guest is a supported state, not an error: a guest call still works,
 * a guest simply has no saved history and no retained audio.
 */
export const GUEST_SESSION: SessionState = {
  status: "guest",
  userId: null,
  recordingRetention: false,
};

/**
 * The state before the session is known.
 *
 * "loading" is not an error either: it is the moment between "the page
 * has not asked yet" and "the answer is a guest or a signed-in learner".
 */
export const LOADING_SESSION: SessionState = {
  status: "loading",
  userId: null,
  recordingRetention: false,
};
