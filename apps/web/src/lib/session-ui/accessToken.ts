/**
 * The web-auth adapter — Phase 04.
 *
 * `prompts/parallel-G1/ADDENDUM.md` §C: Phase 06 adds **additive** exports
 * to `apps/web/src/lib/auth/index.ts`. Phase 04 must typecheck before they
 * exist, so the app reads them through this adapter and falls back to the
 * guest case when they are missing.
 *
 * The caller's own short-lived token is the only credential the browser
 * ever holds, and it travels in the first `start` event — never in a URL
 * (`docs/contracts/call-transport.md` §7).
 *
 * The sign-out hook is the one published in `prompts/parallel-G1/COMM.md`
 * entry 05: a signed-out learner must not keep a live call connection
 * open.
 */

type AuthModule = {
  getAccessToken?: () => Promise<string | null>;
  onSignOut?: (handler: () => void) => () => void;
  setRecordingRetention?: (granted: boolean) => Promise<void>;
};

async function loadAuth(): Promise<AuthModule> {
  try {
    return (await import("@/lib/auth")) as unknown as AuthModule;
  } catch {
    return {};
  }
}

/**
 * The caller's access token, or null for a guest call.
 *
 * Never throws: a guest call is a normal, supported case.
 */
export async function getCallAccessToken(): Promise<string | null> {
  const auth = await loadAuth();
  if (typeof auth.getAccessToken !== "function") {
    return null;
  }
  try {
    const token = await auth.getAccessToken();
    return typeof token === "string" && token.length > 0 ? token : null;
  } catch {
    return null;
  }
}

/**
 * Subscribe to the sign-out so a live call connection is closed.
 *
 * Returns the unsubscribe function. When the seam is not there yet, this
 * is a no-op that returns a no-op unsubscribe.
 */
export async function subscribeToSignOut(handler: () => void): Promise<() => void> {
  const auth = await loadAuth();
  if (typeof auth.onSignOut !== "function") {
    return () => undefined;
  }
  try {
    return auth.onSignOut(handler);
  } catch {
    return () => undefined;
  }
}

/**
 * Record or withdraw the recording-retention permission.
 *
 * Returns true when the service accepted the decision. The decision also
 * travels in the `start` event and the service re-checks it when it
 * writes, so a failure here never turns into a silently kept recording.
 */
export async function setRecordingRetentionConsent(granted: boolean): Promise<boolean> {
  const auth = await loadAuth();
  if (typeof auth.setRecordingRetention !== "function") {
    return false;
  }
  try {
    await auth.setRecordingRetention(granted);
    return true;
  } catch {
    return false;
  }
}
