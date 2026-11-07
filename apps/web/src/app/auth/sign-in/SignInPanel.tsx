"use client";

/**
 * The sign-in / sign-up panel.
 *
 * One screen, one email field and one password field. The toggle chooses
 * between creating an account and signing in. The errors are plain words:
 * a wrong password and an unknown email get the same sentence from the
 * service, so the screen cannot be used to discover accounts.
 *
 * A guest is always one link away: "Continue as guest" returns to the app
 * without an account. A guest call still works; a guest simply has no
 * saved history and no retained audio.
 *
 * The copy is honest about the storage: history is kept on our server,
 * can be deleted, and the speech providers process audio live. There is
 * no "end-to-end encrypted" claim.
 */

import Link from "next/link";
import { useState } from "react";

import { signIn, signOut, signUp, useSession } from "@/lib/auth";

type Mode = "sign-in" | "create";

export function SignInPanel() {
  const session = useSession();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const result =
        mode === "create"
          ? await signUp(email.trim(), password)
          : await signIn(email.trim(), password);
      if (!result.ok) {
        setMessage(result.message ?? "That did not work. Please try again.");
      } else {
        setPassword("");
      }
    } catch {
      setMessage("We could not reach the service. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (session.status === "authenticated") {
    return (
      <section aria-label="Account">
        <p data-testid="auth-signed-in">
          You are signed in. Your practice history is stored on our server.
          You can delete it at any time from settings.
        </p>
        <button
          type="button"
          onClick={() => void signOut()}
          style={buttonStyle}
        >
          Sign out
        </button>
        <p style={{ marginTop: "1rem" }}>
          <Link href="/">Back to practice</Link>
        </p>
        <SessionStateList session={session} />
      </section>
    );
  }

  return (
    <section aria-label={mode === "create" ? "Create account" : "Sign in"}>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        <button
          type="button"
          onClick={() => {
            setMode("sign-in");
            setMessage(null);
          }}
          aria-pressed={mode === "sign-in"}
          style={toggleStyle(mode === "sign-in")}
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("create");
            setMessage(null);
          }}
          aria-pressed={mode === "create"}
          style={toggleStyle(mode === "create")}
        >
          Create account
        </button>
      </div>

      <form onSubmit={submit} style={{ display: "grid", gap: "0.75rem" }}>
        <label htmlFor="email" style={labelStyle}>
          Email address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          maxLength={254}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          style={inputStyle}
        />

        <label htmlFor="password" style={labelStyle}>
          Password
        </label>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete={mode === "create" ? "new-password" : "current-password"}
            required
            minLength={mode === "create" ? 10 : 1}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={{ ...inputStyle, flex: 1, minWidth: 0 }}
          />
          <button
            type="button"
            onClick={() => setShowPassword((visible) => !visible)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
            style={{ ...buttonStyle, width: "auto", padding: "0 0.9rem" }}
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>

        <button type="submit" disabled={busy} style={buttonStyle}>
          {busy
            ? "Please wait…"
            : mode === "create"
              ? "Create account"
              : "Sign in"}
        </button>
      </form>

      {message ? (
        <p role="alert" data-testid="auth-message" style={{ marginTop: "1rem" }}>
          {message}
        </p>
      ) : null}

      <p style={{ marginTop: "1.5rem" }}>
        <Link href="/">Continue as guest</Link>
      </p>
      <p style={{ color: "var(--ink-soft, #55555c)", fontSize: "0.95rem" }}>
        Your practice history is stored on our server and can be deleted at
        any time. The speech providers process audio live while you practise.
      </p>

      <SessionStateList session={session} />
    </section>
  );
}

function SessionStateList({ session }: { session: ReturnType<typeof useSession> }) {
  return (
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
  );
}

const labelStyle: React.CSSProperties = {
  fontSize: "1rem",
  fontWeight: 600,
};

const inputStyle: React.CSSProperties = {
  fontSize: "16px",
  minHeight: "48px",
  padding: "0.6rem 0.75rem",
  border: "1px solid var(--line, #c9c7c0)",
  borderRadius: "0.5rem",
  width: "100%",
  boxSizing: "border-box",
};

const buttonStyle: React.CSSProperties = {
  fontSize: "16px",
  minHeight: "48px",
  padding: "0 1.25rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--ink, #1c1c1e)",
  background: "var(--ink, #1c1c1e)",
  color: "var(--canvas, #fbfaf7)",
  cursor: "pointer",
};

function toggleStyle(active: boolean): React.CSSProperties {
  return {
    fontSize: "16px",
    minHeight: "48px",
    padding: "0 1rem",
    borderRadius: "0.5rem",
    border: "1px solid var(--ink, #1c1c1e)",
    background: active ? "var(--ink, #1c1c1e)" : "transparent",
    color: active ? "var(--canvas, #fbfaf7)" : "var(--ink, #1c1c1e)",
    cursor: "pointer",
  };
}
