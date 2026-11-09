"use client";

/**
 * The coaching break — Phase 17.
 *
 * One strength and one thing to try, both grounded in what was measured.
 * Nothing else. Three actions: Try again, Keep talking, Skip.
 */

import styles from "../app.module.css";
import { CheckIcon, LightbulbIcon, MicIcon } from "../components/Icon";
import type { RoundFeedbackPayload } from "@/lib/transport";

export interface CoachingViewProps {
  feedback: RoundFeedbackPayload;
  turnId: string | null;
  onRetry: (turnId: string) => void;
  onKeepTalking: () => void;
  onSkip: () => void;
}

export function CoachingView({
  feedback,
  turnId,
  onRetry,
  onKeepTalking,
  onSkip,
}: CoachingViewProps) {
  const strength = feedback.strengths?.[0] ?? "No strength measured.";
  const improvement = feedback.improvements?.[0] ?? "Keep practising.";

  return (
    <div className={`${styles.container} ${styles.containerNarrow}`}>
      <h1 className={styles.screenTitle}>Quick feedback</h1>

      <div className={`${styles.noteCard} ${styles.noteCardStrength}`}>
        <span className={styles.noteLabel}>
          <CheckIcon size={15} />
          Strength
        </span>
        <p className={styles.noteText}>{strength}</p>
      </div>

      <div className={`${styles.noteCard} ${styles.noteCardImprove}`}>
        <span className={styles.noteLabel}>
          <LightbulbIcon size={15} />
          Try
        </span>
        <p className={styles.noteText}>{improvement}</p>
      </div>

      <div className={styles.breakActions}>
        <button
          type="button"
          className={styles.primaryButton}
          onClick={() => turnId && onRetry(turnId)}
          disabled={!turnId}
        >
          <MicIcon size={18} />
          Try again
        </button>
        <button type="button" className={styles.secondaryButton} onClick={onKeepTalking}>
          Keep talking
        </button>
        <button
          type="button"
          className={styles.ghostButton}
          aria-label="Skip the feedback"
          onClick={onSkip}
        >
          Skip
        </button>
      </div>
    </div>
  );
}

export default CoachingView;
