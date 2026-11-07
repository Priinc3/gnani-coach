import type { Metadata } from "next";

import { SignOutButton } from "./SignOutButton";

export const metadata: Metadata = {
  title: "Sign out — Speaking Coach",
  description: "End the session on this device.",
};

export const dynamic = "force-dynamic";

/**
 * The sign-out page.
 *
 * It ends the session and sends the learner back to the app. A guest
 * that opens it is told plainly that there was nothing to end.
 */
export default function SignOutPage() {
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
      <h1 style={{ fontSize: "1.75rem", margin: "0 0 0.5rem" }}>Sign out</h1>
      <p style={{ color: "var(--ink-soft, #55555c)", margin: "0 0 1.5rem" }}>
        Signing out ends the session on this device. Your saved history
        and your recordings stay where they are; deleting a recording is a
        separate, explicit action.
      </p>
      <SignOutButton />
    </main>
  );
}
