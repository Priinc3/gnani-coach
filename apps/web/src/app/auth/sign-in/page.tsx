import type { Metadata } from "next";

import { SignInPanel } from "./SignInPanel";

export const metadata: Metadata = {
  title: "Sign in — Speaking Coach",
  description:
    "Sign in to keep your practice history and, if you choose, your recordings.",
};

/**
 * The sign-in page.
 *
 * The page is a client-driven form now: there is no Supabase project and
 * no server-side session to read. The browser talks to our own voice
 * service, which owns the accounts and the SQLite database.
 */
export default function SignInPage() {
  return (
    <main
      style={{
        maxWidth: "36rem",
        margin: "0 auto",
        padding: "2rem 1.25rem 4rem",
        fontFamily:
          "var(--font-sans, system-ui, -apple-system, 'Segoe UI', sans-serif)",
        color: "var(--ink, #1c1c1e)",
        background: "var(--canvas, #fbfaf7)",
        minHeight: "100vh",
      }}
    >
      <h1 style={{ fontSize: "1.75rem", margin: "0 0 0.5rem" }}>Sign in</h1>
      <p style={{ color: "var(--ink-soft, #55555c)", margin: "0 0 1.5rem" }}>
        A guest can practise straight away. Signing in is what lets the
        service keep your session history &mdash; and, only if you ask for
        it, your recordings.
      </p>

      <SignInPanel />
    </main>
  );
}
