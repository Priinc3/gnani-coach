"use client";

/**
 * Web authentication — **Phase 06 owns this tree**.
 *
 * The frozen seam is this exact path and these exports:
 *
 * - `useSession()` — the current session state;
 * - `signOut()` — end the session.
 *
 * Phase 06 replaces the guest stub with the real session and keeps both
 * names and both shapes. The guest state is still a supported state: the
 * app works without an account, and a guest has no saved history and no
 * retained audio.
 *
 * The additive exports:
 *
 * - `getAccessToken()` — the caller's own access token, or `null` for a
 *   guest (ADDENDUM §C). It is the token the browser sends to our own
 *   voice service in the first `start` event; the service verifies it
 *   again, so a forged token buys nothing.
 * - `onSignOut(handler)` — the registry hook Phase 04 subscribes to, so
 *   that a signed-out learner does not keep a live call connection
 *   open. The name is published in `prompts/parallel-G1/COMM.md`.
 * - `setRecordingRetention(granted)` — the recording-retention consent.
 *
 * The rules:
 *
 * - the **publishable key** and the project URL are read on the server
 *   and passed to the browser client as props. The service-role key
 *   never reaches the web app;
 * - the identity of the caller comes from `getClaims()`, which verifies
 *   the token. `getSession()` is used only to read the raw token to
 *   forward, and the voice service verifies that token again;
 * - the proxy (`src/proxy.ts`) refreshes the session and sets no-cache
 *   headers; it never guards `/`, because a guest may call.
 */

import { useSyncExternalStore } from "react";

import {
  getAccessToken as getAccessTokenImpl,
  getServerSessionSnapshot,
  getSessionSnapshot,
  onSignOut as registerSignOutHandler,
  setRecordingRetention as setRecordingRetentionImpl,
  signOut as signOutImpl,
  subscribeSession,
} from "./browser";
import type { SessionState, SessionStatus } from "./types";

// Only the **types** are re-exported. A value re-export would become a
// client reference in a server component, and the frozen seam never
// exported one.
export type { SessionState, SessionStatus };

/**
 * The current session state.
 *
 * The shape is the frozen one: a status, an opaque user id and the
 * device-local recording preference. `status` is `"loading"` until the
 * session has been learned, `"guest"` when there is no verified session,
 * and `"authenticated"` when there is one.
 */
export function useSession(): SessionState {
  return useSyncExternalStore(
    subscribeSession,
    getSessionSnapshot,
    getServerSessionSnapshot,
  );
}

/**
 * End the session.
 *
 * The session ends on the server, and the sign-out handlers run
 * whatever happens, so a live call connection is closed even when the
 * sign-out itself fails.
 */
export async function signOut(): Promise<void> {
  await signOutImpl();
}

/**
 * The caller's own access token, or `null` for a guest.
 *
 * The token is short-lived and belongs to the caller. It is forwarded to
 * our own voice service, which verifies it before it writes anything.
 */
export async function getAccessToken(): Promise<string | null> {
  return getAccessTokenImpl();
}

/**
 * Subscribe to the sign-out.
 *
 * Phase 04 calls this to close a live call connection when the learner
 * signs out. The returned function unsubscribes.
 */
export function onSignOut(handler: () => void): () => void {
  return registerSignOutHandler(handler);
}

/**
 * Record or withdraw the recording-retention consent.
 *
 * Recording retention is **off by default**, and it is a separate
 * decision from the consent to process speech live. Turning it off stops
 * the service from keeping any further audio; it does not delete what
 * was already kept, and the deletion is an explicit action.
 */
export async function setRecordingRetention(granted: boolean): Promise<void> {
  await setRecordingRetentionImpl(granted);
}
