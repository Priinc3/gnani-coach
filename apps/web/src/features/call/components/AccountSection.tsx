"use client";

/**
 * The account section in Settings — Phase 10 FIX-1.
 *
 * A guest sees the same sign-in entry as the landing view and the Progress
 * empty state. A signed-in learner sees the account state, a Sign out
 * button, and the delete flow.
 *
 * The delete flow reuses the End-call confirmation sheet: it asks for the
 * password again, states exactly what is erased, and calls
 * `deleteAccount(password)` once per confirmed submit. The password is
 * only held in component state for that request, and it is cleared when
 * the sheet closes. It is never logged and never stored.
 */

import { useState } from "react";

import { deleteAccount } from "@/lib/auth";

import styles from "../app.module.css";
import { TrashIcon, UsersIcon } from "./Icon";
import { SignInEntry } from "./SignInEntry";

export interface AccountSectionProps {
  signedIn: boolean;
  /** The same handler the live call screen uses for sign-out. */
  onSignOut: () => void;
  /** Return to the landing view and show the short confirmation. */
  onDeleted: () => void;
}

export function AccountSection({ signedIn, onSignOut, onDeleted }: AccountSectionProps) {
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (!signedIn) {
    return (
      <section className={styles.accountGuest} aria-labelledby="account-guest-title">
        <span className={styles.accountIcon} aria-hidden="true">
          <UsersIcon size={22} />
        </span>
        <h3 className={styles.accountTitle} id="account-guest-title">
          Keep your progress
        </h3>
        <SignInEntry />
      </section>
    );
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
    <section className={styles.accountSection} aria-labelledby="account-title">
      <span className={styles.accountIcon} aria-hidden="true">
        <UsersIcon size={22} />
      </span>
      <h3 className={styles.accountTitle} id="account-title">
        Your account
      </h3>
      <p className={styles.accountText}>Signed in. Your history is stored on our server.</p>
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
          Delete my account and data
        </button>
      </div>

      {confirming ? (
        <div className={styles.confirmOverlay}>
          <div
            className={styles.confirmSheet}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-account-title"
            aria-describedby="delete-account-text"
          >
            <h2 className={styles.confirmTitle} id="delete-account-title">
              Delete your account?
            </h2>
            <p className={styles.confirmText} id="delete-account-text">
              This deletes your account, history and saved recordings. It cannot be undone.
            </p>
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
                  Keep my account
                </button>
                <button
                  type="submit"
                  className={styles.endButton}
                  disabled={busy || password.length === 0}
                >
                  <TrashIcon size={16} />
                  {busy ? "Deleting…" : "Delete everything"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default AccountSection;
