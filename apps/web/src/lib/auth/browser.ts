"use client";

/**
 * The browser-side session store.
 *
 * **Phase 06 owns this tree.** One module holds the session state, the
 * browser Supabase client and the sign-out registry, so that the public
 * seam (`@/lib/auth`) stays small and stable.
 *
 * How the session is learned:
 *
 * 1. when the browser Supabase client is configured (the sign-in page
 *    configures it from the props the server passed down), the client is
 *    asked with `getClaims()`, which **verifies** the token;
 * 2. otherwise the browser asks our own server (`/auth/session`), which
 *    verifies the session cookie with `getClaims()` and answers with the
 *    state and the access token.
 *
 * `getSession()` is only used to read the raw access token that has to
 * be forwarded to our own voice service. That service verifies the
 * token again, so the decision about who the caller is never rests on
 * this call.
 */

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import {
  GUEST_SESSION,
  LOADING_SESSION,
  type SessionState,
} from "./types";

/** The endpoint that answers "who is the caller?" from our own server. */
export const SESSION_ENDPOINT = "/auth/session";

/** The local-storage key of the device-local recording preference. */
export const RECORDING_FLAG_KEY = "gnani.recordingRetention";

/** The consent version this client writes. */
export const CONSENT_VERSION = "0.1";

let browserClient: SupabaseClient | null = null;
let current: SessionState = LOADING_SESSION;

const listeners = new Set<() => void>();
const signOutHandlers = new Set<() => void>();

/**
 * Configure the browser Supabase client.
 *
 * The URL and the publishable key arrive **as props from the server**:
 * they are read from the server environment and never inlined into the
 * bundle (ADDENDUM §E). The service-role key never reaches this file.
 */
export function configureBrowserSupabase(config: {
  url: string;
  publishableKey: string;
}): SupabaseClient {
  browserClient = createBrowserClient(config.url, config.publishableKey);
  return browserClient;
}

/** The browser Supabase client, or `null` when it is not configured. */
export function getBrowserSupabase(): SupabaseClient | null {
  return browserClient;
}

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

/** The device-local recording preference. */
export function readDeviceRecordingFlag(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.localStorage.getItem(RECORDING_FLAG_KEY) === "1";
  } catch {
    // A browser in private mode may refuse storage. The preference is
    // a convenience; the consent that matters lives on the server.
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
    // As above: a refused write is not a failure.
  }
}

/**
 * Learn the session, from the browser client when there is one and from
 * our own server otherwise.
 */
export async function refreshSession(): Promise<void> {
  const retention = readDeviceRecordingFlag();
  const client = getBrowserSupabase();
  if (client) {
    try {
      const { data, error } = await client.auth.getClaims();
      const subject = data?.claims?.sub;
      if (error || typeof subject !== "string" || subject.length === 0) {
        setSession({ ...GUEST_SESSION, recordingRetention: retention });
        return;
      }
      setSession({
        status: "authenticated",
        userId: subject,
        recordingRetention: retention,
      });
    } catch {
      setSession({ ...GUEST_SESSION, recordingRetention: retention });
    }
    return;
  }

  try {
    const response = await fetch(SESSION_ENDPOINT, {
      method: "GET",
      credentials: "same-origin",
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      setSession({ ...GUEST_SESSION, recordingRetention: retention });
      return;
    }
    const body = (await response.json()) as {
      status?: string;
      userId?: string | null;
    };
    if (body.status === "authenticated" && typeof body.userId === "string") {
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

/**
 * Register a handler that runs when the learner signs out.
 *
 * Phase 04 uses this to close a live call connection: a signed-out
 * caller must not keep a socket open. The returned function
 * unsubscribes.
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
 * The session is ended on the server first (the browser client clears
 * the session cookie, or our own endpoint does), and the sign-out
 * handlers run **whatever happens**, so a live call connection is closed
 * even when the sign-out itself fails.
 */
export async function signOut(): Promise<void> {
  try {
    const client = getBrowserSupabase();
    if (client) {
      const { error } = await client.auth.signOut();
      if (error) {
        throw error;
      }
    } else {
      await fetch(SESSION_ENDPOINT, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  } finally {
    runSignOutHandlers();
    await refreshSession();
  }
}

/**
 * The caller's own access token, or `null` for a guest.
 *
 * The token is the caller's own short-lived session token. It is
 * forwarded to our own voice service, which verifies it again; it is
 * never a provider credential and never a service credential.
 */
export async function getAccessToken(): Promise<string | null> {
  const client = getBrowserSupabase();
  if (client) {
    try {
      const { data } = await client.auth.getSession();
      const token = data.session?.access_token;
      return typeof token === "string" && token.length > 0 ? token : null;
    } catch {
      return null;
    }
  }
  try {
    const response = await fetch(SESSION_ENDPOINT, {
      method: "GET",
      credentials: "same-origin",
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    const body = (await response.json()) as { accessToken?: string | null };
    return typeof body.accessToken === "string" && body.accessToken.length > 0
      ? body.accessToken
      : null;
  } catch {
    return null;
  }
}

/**
 * The HTTP URL of our own voice service.
 *
 * It is derived from the frozen `VOICE_WS_URL` (`ws` becomes `http`,
 * `wss` becomes `https`, the path is dropped). Phase 04 derives the
 * same URL in its own library; this one exists only so that the consent
 * write can reach the service.
 */
function voiceHttpUrl(): string {
  const configured = process.env.NEXT_PUBLIC_VOICE_WS_URL;
  const fallback = "ws://localhost:8000/ws/call";
  try {
    const url = new URL(configured ?? fallback);
    url.protocol = url.protocol === "wss:" ? "https:" : "http:";
    url.pathname = "";
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/+$/, "");
  } catch {
    return "http://localhost:8000";
  }
}

/**
 * Record or withdraw the recording-retention consent.
 *
 * The device-local preference is written first, so the interface reacts
 * at once. The consent that matters is written on the **voice service**,
 * with the caller's own bearer token, because that is where the
 * retention decision is enforced: a recording is only written when the
 * consent is in place at write time.
 */
export async function setRecordingRetention(granted: boolean): Promise<void> {
  writeDeviceRecordingFlag(granted);
  setSession({ ...current, recordingRetention: granted });

  const token = await getAccessToken();
  if (!token) {
    // A guest has no account to consent with. The service would refuse
    // the write anyway.
    return;
  }
  try {
    await fetch(`${voiceHttpUrl()}/api/consent`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
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
