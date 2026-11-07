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
 * It is a **server** component on purpose: the Supabase URL and the
 * publishable key are read from the server environment here and handed
 * to the client component as props, so neither is inlined into the
 * JavaScript bundle (ADDENDUM §E). The service-role key is never read
 * here and never leaves the Python service.
 *
 * The page is rendered per request, because the configuration is read at
 * request time.
 */
export const dynamic = "force-dynamic";

export default function SignInPage() {
  const supabaseUrl = process.env.SUPABASE_URL ?? "";
  const publishableKey = process.env.SUPABASE_PUBLISHABLE_KEY ?? "";
  const configured = supabaseUrl.length > 0 && publishableKey.length > 0;

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

      <SignInPanel
        supabaseUrl={supabaseUrl}
        publishableKey={publishableKey}
        configured={configured}
      />
    </main>
  );
}
