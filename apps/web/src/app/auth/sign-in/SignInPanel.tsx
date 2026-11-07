"use client";

/**
 * The sign-in panel.
 *
 * **Phase 06 owns this tree.** It is a client component: it configures
 * the browser Supabase client from the props the server passed down
 * (ADDENDUM §E) and it drives the sign-in.
 *
 * The sign-in method is an **email magic link** (a one-time password by
 * email). It was chosen over a password because it keeps the credential
 * out of this application entirely: there is no password to store, to
 * hash, to leak or to reset, and the link expires.
 *
 * Source: the Supabase email one-time-password guide
 * (<https://supabase.com/docs/guides/auth/auth-otp/email-otp>, checked
 * 2026-10-20).
 *
 * What the deployment needs:
 *
 * - the **Redirect URLs** of the project have to allow this origin (the
 *   magic link comes back to `/auth/sign-in`);
 * - the project needs an email provider, so that the link can be sent.
 *
 * Without a configured project the panel says so plainly. It never
 * pretends to be signed in.
 */

import { useEffect, useState } from "react";

import {
  configureBrowserSupabase,
  getBrowserSupabase,
  refreshSession,
} from "@/lib/auth/browser";
import { signOut, useSession } from "@/lib/auth";

export interface SignInPanelProps {
  supabaseUrl: string;
  publishableKey: string;
  configured: boolean;
}

export function SignInPanel({
  supabaseUrl,
  publishableKey,
  configured,
}: SignInPanelProps) {
  const session = useSession();
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!configured) {
      return;
    }
    configureBrowserSupabase({ url: supabaseUrl, publishableKey });
    void refreshSession();
  }, [configured, publishableKey, supabaseUrl]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const client = getBrowserSupabase();
    if (!client) {
      setMessage("Sign-in is not available in this deployment.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const { error } = await client.auth.signInWithOtp({
        email: email.trim(),
        options: {
          shouldCreateUser: true,
          emailRedirectTo: `${window.location.origin}/auth/sign-in`,
        },
      });
      if (error) {
        setMessage("We could not send the sign-in link. Please try again.");
        return;
      }
      setMessage("Check your email: the sign-in link is on its way.");
    } catch {
      setMessage("We could not send the sign-in link. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Sign in">
      {!configured ? (
        <p data-testid="auth-not-configured">
          Signing in is not configured in this deployment. You can still
          practise as a guest.
        </p>
      ) : session.status === "authenticated" ? (
        <div>
          <p data-testid="auth-signed-in">You are signed in.</p>
          <button type="button" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      ) : (
        <form onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {busy ? "Sending…" : "Send the sign-in link"}
          </button>
        </form>
      )}

      {message ? (
        <p role="status" data-testid="auth-message">
          {message}
        </p>
      ) : null}

      {/*
        The session state, rendered so that the shape of `useSession()` is
        visible in the interface and checkable in a test.
      */}
      <dl aria-label="Session state" data-testid="session-state">
        <dt>status</dt>
        <dd data-testid="session-status">{session.status}</dd>
        <dt>userId</dt>
        <dd data-testid="session-user-id">{session.userId ?? ""}</dd>
        <dt>recordingRetention</dt>
        <dd data-testid="session-recording-retention">
          {session.recordingRetention ? "true" : "false"}
        </dd>
      </dl>
    </section>
  );
}
