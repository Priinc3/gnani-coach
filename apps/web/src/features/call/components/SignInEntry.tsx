"use client";

/**
 * The guest entry to the account page — Phase 17.
 *
 * One same-origin link. It stays inside the APK WebView because it is a
 * relative Next.js link.
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
    </div>
  );
}

export default SignInEntry;
