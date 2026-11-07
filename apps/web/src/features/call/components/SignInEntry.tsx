"use client";

/**
 * The guest entry to the account page — Phase 10 FIX-1.
 *
 * One same-origin link, shown only to guests, in the landing view, the
 * empty Progress state and the Settings view. It stays inside the APK
 * WebView because it is a relative Next.js link.
 */

import Link from "next/link";

import styles from "../app.module.css";

export function SignInEntry() {
  return (
    <div className={styles.signInEntry}>
      <Link
        href="/auth/sign-in"
        className={`${styles.secondaryButton} ${styles.signInEntryLink}`}
      >
        Sign in or create an account
      </Link>
      <p className={styles.fieldHelp}>
        Guests can still practise — the call works the same — but nothing is saved.
      </p>
    </div>
  );
}

export default SignInEntry;
