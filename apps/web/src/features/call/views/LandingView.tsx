"use client";

/**
 * The landing view — Phase 17.
 *
 * One illustration, one title, one Start button. A guest also gets a small
 * Sign in link. Nothing else is needed to begin.
 */

import Link from "next/link";

import styles from "../app.module.css";
import { CoachAvatar } from "../components/CoachAvatar";
import { MicIcon, SparkIcon } from "../components/Icon";

export interface LandingViewProps {
  onStart: () => void;
  /** Whether the learner has a verified session. */
  signedIn?: boolean;
  /** A short confirmation after an account was deleted. */
  notice?: string | null;
}

export function LandingView({ onStart, signedIn = false, notice = null }: LandingViewProps) {
  return (
    <div className={styles.landingSimple} data-testid="landing-root">
      {notice ? (
        <p className={styles.callNote} role="status" data-testid="account-notice">
          {notice}
        </p>
      ) : null}

      <div className={styles.landingArt}>
        <div className={styles.artFrame}>
          <CoachAvatar className={styles.artAvatar} />
        </div>
        <span className={`${styles.floatingCard} ${styles.floatingCardTop}`} aria-hidden="true">
          <MicIcon size={16} />
          Listening
        </span>
        <span className={`${styles.floatingCard} ${styles.floatingCardBottom}`} aria-hidden="true">
          <SparkIcon size={16} />
          Feedback
        </span>
      </div>

      <h1 className={styles.landingTitle} id="landing-title">
        Speak with <span className={styles.heroTitleAccent}>confidence</span>
      </h1>
      <p className={styles.landingLine}>Practice out loud.</p>

      <button
        type="button"
        className={`${styles.primaryButton} ${styles.startBig}`}
        onClick={onStart}
        aria-label="Start a practice call"
      >
        Start
      </button>

      {!signedIn ? (
        <Link href="/auth/sign-in" className={styles.signInLink}>
          Sign in
        </Link>
      ) : null}
    </div>
  );
}

export default LandingView;
