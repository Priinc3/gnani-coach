"use client";

/**
 * The account section in Settings — Phase 17.
 *
 * A guest sees one Sign in link. A signed-in learner sees Sign out and
 * Delete account. Deleting asks for the password once and states that it
 * cannot be undone.
 */

import { useState } from "react";

import { deleteAccount } from "@/lib/auth";

import styles from "../app.module.css";
import { TrashIcon } from "./Icon";
import { SignInEntry } from "./SignInEntry";

export interface AccountSectionProps {
  signedIn: boolean;
  onSignOut: () => void;
  onDeleted: () => void;
}

export function AccountSection({ signedIn, onSignOut, onDeleted }: AccountSectionProps) {
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (!signedIn) {
    return <SignInEntry />;
  }

  function close() {
    setConfirming(false);
    setPassword("");
    setMessage(null);
  }

  async function handleDelete(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) {
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const result = await deleteAccount(password);
      if (result.ok) {
        setPassword("");
        setConfirming(false);
        onDeleted();
        return;
      }
      setMessage(result.message ?? "That did not work. Please try again.");
    } catch {
      setMessage("We could not reach the service. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.accountActions}>
      <button type="button" className={styles.secondaryButton} onClick={onSignOut}>
        Sign out
      </button>
      <button
        type="button"
        className={`${styles.dangerButton} ${styles.accountDeleteButton}`}
        onClick={() => setConfirming(true)}
      >
        <TrashIcon size={16} />
        Delete account
      </button>

      {confirming ? (
        <div className={styles.confirmOverlay}>
          <div
            className={styles.confirmSheet}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-account-title"
          >
            <h2 className={styles.confirmTitle} id="delete-account-title">
              Delete your account?
            </h2>
            <p className={styles.confirmText}>This cannot be undone.</p>
            <form className={styles.confirmForm} onSubmit={(event) => void handleDelete(event)}>
              <label className={styles.fieldLabel} htmlFor="delete-account-password">
                Password
              </label>
              <input
                id="delete-account-password"
                className={`${styles.textInput} ${styles.confirmInput}`}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              {message ? (
                <p className={styles.confirmError} role="alert">
                  {message}
                </p>
              ) : null}
              <div className={styles.confirmActions}>
                <button type="button" className={styles.secondaryButton} onClick={close}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className={styles.endButton}
                  disabled={busy || password.length === 0}
                >
                  <TrashIcon size={16} />
                  Delete
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default AccountSection;
