"use client";

/**
 * The session summary — Phase 17.
 *
 * Three short lines at most: one strength, one thing to try, and the time
 * spoken. Then Try again or Done. No scores and no invented measurements.
 */

import styles from "../app.module.css";
import { formatSpokenDuration } from "@/lib/session-ui";
import type { CallState } from "@/lib/session-ui";

export interface SummaryViewProps {
  state: CallState;
  onDone: () => void;
  onRetry: () => void;
}

export function SummaryView({ state, onDone, onRetry }: SummaryViewProps) {
  const last = state.rounds[state.rounds.length - 1];
  const strength = last?.strengths?.[0] ?? "No strength measured.";
  const improvement = last?.improvements?.[0] ?? "Keep practising.";

  return (
    <div className={`${styles.container} ${styles.containerNarrow}`} data-testid="summary-root">
      <h1 className={styles.screenTitle}>Summary</h1>

      {state.notice ? (
        <p className={styles.callNote} role="status" data-testid="summary-notice">
          {state.notice}
        </p>
      ) : null}

      <ul className={styles.summaryLines}>
        <li className={styles.summaryLine}>{strength}</li>
        <li className={styles.summaryLine}>{improvement}</li>
        <li className={styles.summaryLine}>
          Spoke for {formatSpokenDuration(state.elapsedMs)}.
        </li>
      </ul>

      <div className={styles.summaryActions}>
        <button type="button" className={styles.primaryButton} onClick={onRetry}>
          Try again
        </button>
        <button type="button" className={styles.secondaryButton} onClick={onDone}>
          Done
        </button>
      </div>
    </div>
  );
}

export default SummaryView;
