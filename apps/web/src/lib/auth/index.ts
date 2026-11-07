"use client";

/**
 * Web authentication — the frozen seam.
 *
 * The frozen exports are `useSession()`, `signOut()`, `getAccessToken()`,
 * `onSignOut()`, `setRecordingRetention()` and their types. They keep
 * their names and shapes.
 *
 * The additive exports are `signIn()`, `signUp()` and `deleteAccount()`.
 * They let the sign-in page drive the local email/password provider, and
 * they let the settings screen delete an account with its password. The
 * name `deleteAccount` is published in `prompts/parallel-G2/COMM.md`.
 *
 * The rules:
 *
 * - the browser talks to our own voice service, never to a provider;
 * - the bearer token is kept in `localStorage` because the web app and
 *   the voice service are on different origins and the frozen CORS seam
 *   has `allow_credentials=False`. The strict `script-src 'self'` CSP is
 *   the XSS defence; the token is cleared on logout and on any `401`;
 * - the service verifies the token again, so a forged token buys
 *   nothing.
 */

import { useSyncExternalStore } from "react";

import {
  deleteAccount as deleteAccountImpl,
  getAccessToken as getAccessTokenImpl,
  getServerSessionSnapshot,
  getSessionSnapshot,
  onSignOut as registerSignOutHandler,
  setRecordingRetention as setRecordingRetentionImpl,
  signIn as signInImpl,
  signOut as signOutImpl,
  signUp as signUpImpl,
  subscribeSession,
  type AuthResult,
} from "./browser";
import type { SessionState, SessionStatus } from "./types";

// Only the **types** are re-exported. A value re-export would become a
// client reference in a server component, and the frozen seam never
// exported one.
export type { AuthResult, SessionState, SessionStatus };

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

/**
 * Create an account and sign in.
 *
 * The password is sent only to our own voice service, over HTTPS in a
 * production deployment, and is never stored in the browser.
 */
export async function signUp(
  email: string,
  password: string,
): Promise<AuthResult> {
  return signUpImpl(email, password);
}

/** Sign in with an email and password. */
export async function signIn(
  email: string,
  password: string,
): Promise<AuthResult> {
  return signInImpl(email, password);
}

/**
 * Delete the account, every row and every recording file.
 *
 * The password is required again, so a stolen token alone cannot erase
 * the account. This is the helper the settings screen (Phase 10) calls.
 */
export async function deleteAccount(password: string): Promise<AuthResult> {
  return deleteAccountImpl(password);
}
