"use client";

/**
 * The coaching break — Phase 04.
 *
 * Mobile screen 5 of the reference flow.
 *
 * The rules:
 *
 * - **at most one strength and at most two changes**, each tied to what was
 *   observed;
 * - every metric shows **its own status**: a measured value with its unit,
 *   or a plain-word reason and no number;
 * - **filled pauses are always the insufficient-evidence state** — the
 *   filler capability is unvalidated, so there is never a filler count;
 * - three actions: **Try again**, **Keep talking**, **Skip**.
 */

import { useState } from "react";

import styles from "../app.module.css";
import { CheckIcon, LightbulbIcon, MicIcon } from "../components/Icon";
import { describeEvidence } from "@/lib/session-ui";
import type { RoundFeedbackPayload } from "@/lib/transport";

export interface CoachingViewProps {
  feedback: RoundFeedbackPayload;
  turnId: string | null;
  onRetry: (turnId: string) => void;
  onKeepTalking: () => void;
  onSkip: () => void;
}

type Tab = "strengths" | "improvements" | "language";

export function CoachingView({
  feedback,
  turnId,
  onRetry,
  onKeepTalking,
  onSkip,
}: CoachingViewProps) {
  const [tab, setTab] = useState<Tab>("strengths");
  const strengths = feedback.strengths ?? [];
  const improvements = feedback.improvements ?? [];
  const languageNotes = feedback.languageNotes ?? [];
  const evidence = describeEvidence(feedback);

  return (
    <div className={`${styles.container} ${styles.containerNarrow}`}>
      <header className={styles.breakHeader}>
        <span className={styles.pill}>
          <LightbulbIcon size={14} />
          Coaching break
        </span>
        <h2 className={styles.breakTitle}>Here is a quick look at that round</h2>
        <p className={styles.breakLede}>
          It is based on what was measured in your own audio. Anything that could not be measured
          is marked as such rather than guessed at.
        </p>
      </header>

      <div className={styles.tabRow} role="tablist" aria-label="Coaching break sections">
        <button
          type="button"
          role="tab"
          id="tab-strengths"
          aria-selected={tab === "strengths"}
          aria-controls="panel-strengths"
          className={`${styles.tab} ${tab === "strengths" ? styles.tabActive : ""}`}
          onClick={() => setTab("strengths")}
        >
          Strengths
        </button>
        <button
          type="button"
          role="tab"
          id="tab-improvements"
          aria-selected={tab === "improvements"}
          aria-controls="panel-improvements"
          className={`${styles.tab} ${tab === "improvements" ? styles.tabActive : ""}`}
          onClick={() => setTab("improvements")}
        >
          Improve
        </button>
        <button
          type="button"
          role="tab"
          id="tab-language"
          aria-selected={tab === "language"}
          aria-controls="panel-language"
          className={`${styles.tab} ${tab === "language" ? styles.tabActive : ""}`}
          onClick={() => setTab("language")}
        >
          Language
        </button>
      </div>

      <div
        role="tabpanel"
        id="panel-strengths"
        aria-labelledby="tab-strengths"
        hidden={tab !== "strengths"}
      >
        {strengths.length > 0 ? (
          strengths.map((strength) => (
            <div className={`${styles.noteCard} ${styles.noteCardStrength}`} key={strength}>
              <span className={styles.noteLabel}>
                <CheckIcon size={15} />
                Strength
              </span>
              <p className={styles.noteText}>{strength}</p>
            </div>
          ))
        ) : (
          <div className={styles.noteCard}>
            <span className={styles.noteLabel}>Strength</span>
            <p className={styles.noteText}>
              Nothing was measured strongly enough in this round to call out.
            </p>
          </div>
        )}
      </div>

      <div
        role="tabpanel"
        id="panel-improvements"
        aria-labelledby="tab-improvements"
        hidden={tab !== "improvements"}
      >
        {improvements.length > 0 ? (
          improvements.map((improvement) => (
            <div className={`${styles.noteCard} ${styles.noteCardImprove}`} key={improvement}>
              <span className={styles.noteLabel}>
                <LightbulbIcon size={15} />
                Try next time
              </span>
              <p className={styles.noteText}>{improvement}</p>
            </div>
          ))
        ) : (
          <div className={styles.noteCard}>
            <span className={styles.noteLabel}>Try next time</span>
            <p className={styles.noteText}>
              There was not enough measured evidence in this round to suggest a change.
            </p>
          </div>
        )}
      </div>

      <div
        role="tabpanel"
        id="panel-language"
        aria-labelledby="tab-language"
        hidden={tab !== "language"}
      >
        {languageNotes.length > 0 ? (
          languageNotes.map((note) => (
            <div className={styles.noteCard} key={note}>
              <span className={styles.noteLabel}>Language</span>
              <p className={styles.noteText}>{note}</p>
            </div>
          ))
        ) : (
          <div className={styles.noteCard}>
            <span className={styles.noteLabel}>Language</span>
            <p className={styles.noteText}>
              There was nothing to say about the language in this round.
            </p>
          </div>
        )}
      </div>

      {evidence.length > 0 ? (
        <section aria-labelledby="evidence-title" style={{ marginTop: 18 }}>
          <h3 className={styles.noteLabel} id="evidence-title">
            What was measured
          </h3>
          <div className={styles.evidenceRow}>
            {evidence.map((metric) => (
              <span
                className={`${styles.chip} ${
                  metric.status === "available" ? "" : styles.chipInsufficient
                }`}
                key={metric.metricKey}
              >
                <span className={styles.chipLabel}>{metric.label}</span>
                <span
                  className={`${styles.chipValue} ${
                    metric.status === "available" ? "" : styles.chipValueMuted
                  }`}
                >
                  {metric.text}
                </span>
              </span>
            ))}
          </div>
        </section>
      ) : null}

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
        <button type="button" className={styles.ghostButton} onClick={onSkip}>
          Skip the feedback
        </button>
      </div>
    </div>
  );
}

export default CoachingView;
