"use client";

/**
 * The browser-side session store.
 *
 * The deployment has no Supabase project. This module talks to our own
 * voice service instead:
 *
 * - `POST /api/auth/register` and `POST /api/auth/login` return a bearer
 *   token;
 * - `GET /api/auth/me` says who the token belongs to;
 * - `POST /api/auth/logout` revokes it;
 * - `DELETE /api/auth/account` deletes the account, its rows and its
 *   recording files.
 *
 * The token is kept in `localStorage`. That is a deliberate trade-off:
 * the web app is on Vercel and the voice service is on another origin, so
 * a cookie would need `SameSite=None; Secure` and a cross-site CORS
 * credential policy. The frozen CORS seam has `allow_credentials=False`,
 * so a cookie is not available. The XSS defence is the strict
 * `script-src 'self'` CSP on the web app; the token is never put in a URL
 * and is cleared on logout and on any `401`.
 *
 * The public seam (`@/lib/auth`) keeps the frozen exports. Everything in
 * this file is an implementation detail except the names re-exported
 * there.
 */

import { deriveVoiceHttpUrl } from "@/lib/session-ui/http";

import { GUEST_SESSION, LOADING_SESSION, type SessionState } from "./types";

/** The local-storage key of the bearer token. */
export const TOKEN_KEY = "gnani.accessToken";

/** The local-storage key of the device-local recording preference. */
export const RECORDING_FLAG_KEY = "gnani.recordingRetention";

/** The consent version this client writes. */
export const CONSENT_VERSION = "0.1";

/** The voice service HTTP base, derived from the frozen WebSocket URL. */
export function voiceHttpUrl(): string {
  const configured =
    process.env.NEXT_PUBLIC_VOICE_WS_URL ?? "ws://localhost:8000/ws/call";
  try {
    return deriveVoiceHttpUrl(configured);
  } catch {
    return "http://localhost:8000";
  }
}

let current: SessionState = LOADING_SESSION;

const listeners = new Set<() => void>();
const signOutHandlers = new Set<() => void>();

/** Replace the session state and tell the subscribers. */
function setSession(next: SessionState): void {
  if (
    next.status === current.status &&
    next.userId === current.userId &&
    next.recordingRetention === current.recordingRetention
  ) {
    return;
  }
  current = next;
  for (const listener of Array.from(listeners)) {
    try {
      listener();
    } catch {
      // A broken subscriber must not break the session.
    }
  }
}

/** The current state. The object identity is stable between changes. */
export function getSessionSnapshot(): SessionState {
  return current;
}

/** The state a server render sees: the session is not known yet. */
export function getServerSessionSnapshot(): SessionState {
  return LOADING_SESSION;
}

/** Subscribe to the session. The returned function unsubscribes. */
export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  void refreshSession();
  return () => {
    listeners.delete(listener);
  };
}

// ---------------------------------------------------------------------------
// token storage
// ---------------------------------------------------------------------------

/** Read the bearer token, or `null`. Storage can be refused in private mode. */
export function readToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const token = window.localStorage.getItem(TOKEN_KEY);
    return typeof token === "string" && token.length > 0 ? token : null;
  } catch {
    return null;
  }
}

/** Write the bearer token. */
function writeToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // The in-memory session still works for this page.
  }
}

/** Remove the bearer token. */
function clearToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // As above.
  }
}

/** The device-local recording preference. */
export function readDeviceRecordingFlag(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.localStorage.getItem(RECORDING_FLAG_KEY) === "1";
  } catch {
    return false;
  }
}

/** Write the device-local recording preference. */
export function writeDeviceRecordingFlag(granted: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(RECORDING_FLAG_KEY, granted ? "1" : "0");
  } catch {
    // A refused write is not a failure.
  }
}

// ---------------------------------------------------------------------------
// the voice-service client
// ---------------------------------------------------------------------------

/** A request against our own voice service, with the caller's token. */
async function voiceFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = readToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${voiceHttpUrl()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (response.status === 401 && token) {
    // The token is expired or revoked. Drop it at once so the interface
    // stops pretending to be signed in.
    clearToken();
    setSession({ ...GUEST_SESSION, recordingRetention: readDeviceRecordingFlag() });
  }
  return response;
}

/** The plain-word message of a failed auth request. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { message?: unknown };
    if (typeof body.message === "string" && body.message.trim().length > 0) {
      return body.message;
    }
  } catch {
    // A body that is not JSON gets the generic message below.
  }
  return "That did not work. Please try again.";
}

export interface AuthResult {
  ok: boolean;
  message: string | null;
}

interface AuthResponse {
  token?: unknown;
  userId?: unknown;
  expiresAt?: unknown;
}

async function acceptAuthResponse(response: Response): Promise<AuthResult> {
  if (!response.ok) {
    return { ok: false, message: await errorMessage(response) };
  }
  let body: AuthResponse;
  try {
    body = (await response.json()) as AuthResponse;
  } catch {
    return { ok: false, message: "That did not work. Please try again." };
  }
  if (typeof body.token !== "string" || typeof body.userId !== "string") {
    return { ok: false, message: "That did not work. Please try again." };
  }
  writeToken(body.token);
  setSession({
    status: "authenticated",
    userId: body.userId,
    recordingRetention: readDeviceRecordingFlag(),
  });
  return { ok: true, message: null };
}

/** Create an account and sign in. */
export async function signUp(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await voiceFetch("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    return await acceptAuthResponse(response);
  } catch {
    return {
      ok: false,
      message: "We could not reach the service. Please try again.",
    };
  }
}

/** Sign in with an email and password. */
export async function signIn(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await voiceFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    return await acceptAuthResponse(response);
  } catch {
    return {
      ok: false,
      message: "We could not reach the service. Please try again.",
    };
  }
}

/** Learn the session from the stored token. */
export async function refreshSession(): Promise<void> {
  const retention = readDeviceRecordingFlag();
  const token = readToken();
  if (!token) {
    setSession({ ...GUEST_SESSION, recordingRetention: retention });
    return;
  }
  try {
    const response = await voiceFetch("/api/auth/me", { method: "GET" });
    if (!response.ok) {
      setSession({ ...GUEST_SESSION, recordingRetention: retention });
      return;
    }
    const body = (await response.json()) as { userId?: unknown };
    if (typeof body.userId === "string" && body.userId.length > 0) {
      setSession({
        status: "authenticated",
        userId: body.userId,
        recordingRetention: retention,
      });
      return;
    }
    setSession({ ...GUEST_SESSION, recordingRetention: retention });
  } catch {
    setSession({ ...GUEST_SESSION, recordingRetention: retention });
  }
}

// ---------------------------------------------------------------------------
// sign-out registry
// ---------------------------------------------------------------------------

/**
 * Register a handler that runs when the learner signs out.
 *
 * Phase 04 uses this to close a live call connection: a signed-out
 * caller must not keep a socket open. The returned function unsubscribes.
 */
export function onSignOut(handler: () => void): () => void {
  signOutHandlers.add(handler);
  return () => {
    signOutHandlers.delete(handler);
  };
}

/** Run every sign-out handler. A broken handler must not stop the rest. */
function runSignOutHandlers(): void {
  for (const handler of Array.from(signOutHandlers)) {
    try {
      handler();
    } catch {
      // A subscriber's failure is its own problem.
    }
  }
}

/**
 * End the session.
 *
 * The token is revoked on the service when possible, and the local copy
 * is removed **whatever happens**, so a live call connection is closed
 * even when the network is down.
 */
export async function signOut(): Promise<void> {
  try {
    if (readToken()) {
      await voiceFetch("/api/auth/logout", { method: "POST" });
    }
  } catch {
    // The local token is cleared below either way.
  } finally {
    clearToken();
    runSignOutHandlers();
    setSession({ ...GUEST_SESSION, recordingRetention: readDeviceRecordingFlag() });
  }
}

/**
 * Delete the account, every row and every recording file.
 *
 * The password is required again. Phase 10 calls this from the settings
 * screen; the export is published in `prompts/parallel-G2/COMM.md`.
 */
export async function deleteAccount(password: string): Promise<AuthResult> {
  try {
    const response = await voiceFetch("/api/auth/account", {
      method: "DELETE",
      body: JSON.stringify({ password }),
    });
    if (!response.ok) {
      return { ok: false, message: await errorMessage(response) };
    }
    clearToken();
    runSignOutHandlers();
    setSession({ ...GUEST_SESSION, recordingRetention: false });
    return { ok: true, message: null };
  } catch {
    return {
      ok: false,
      message: "We could not reach the service. Please try again.",
    };
  }
}

/**
 * The caller's own access token, or `null` for a guest.
 *
 * It is forwarded to our own voice service, which verifies it again; it
 * is never a provider credential and never a service credential.
 */
export async function getAccessToken(): Promise<string | null> {
  return readToken();
}

/**
 * Record or withdraw the recording-retention consent.
 *
 * The device-local preference is written first, so the interface reacts
 * at once. The consent that matters is written on the voice service with
 * the caller's own bearer token, because that is where retention is
 * enforced at write time.
 */
export async function setRecordingRetention(granted: boolean): Promise<void> {
  writeDeviceRecordingFlag(granted);
  setSession({ ...current, recordingRetention: granted });

  if (!readToken()) {
    // A guest has no account to consent with.
    return;
  }
  try {
    await voiceFetch("/api/consent", {
      method: "POST",
      body: JSON.stringify({
        consentVersion: CONSENT_VERSION,
        recordingRetentionGranted: granted,
      }),
    });
  } catch {
    // The device preference is already written; the server-side consent
    // is retried the next time the toggle changes.
  }
}
