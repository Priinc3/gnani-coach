"use client";

/**
 * The sign-out button.
 *
 * **Phase 06 owns this tree.** It calls the frozen `signOut()`, which
 * ends the session on the server and closes any live call connection
 * through the `onSignOut` registry.
 */

import { useState } from "react";

import { signOut } from "@/lib/auth";

export function SignOutButton() {
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handle() {
    setBusy(true);
    try {
      await signOut();
      setDone(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button type="button" onClick={() => void handle()} disabled={busy}>
        {busy ? "Signing out…" : "Sign out"}
      </button>
      <p role="status" data-testid="sign-out-state">
        {done ? "You are signed out." : ""}
      </p>
    </div>
  );
}
