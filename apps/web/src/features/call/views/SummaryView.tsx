"use client";

/**
 * The session summary — Phase 04.
 *
 * Mobile screen 6 of the reference flow.
 *
 * The rules:
 *
 * - the summary shows **evidence-backed metrics**, each with its own
 *   status;
 * - a **retry comparison** shows only the metrics that both attempts
 *   measured, and a difference is computed only from two available values
 *   and is labelled an estimate;
 * - there is **no overall score, no confidence percentage and no
 *   pronunciation grade**. If nothing was measured, the summary says so.
 */

import styles from "../app.module.css";
import { ArrowLeftIcon, ChartIcon, PlayIcon } from "../components/Icon";
import { compareAttempts, describeEvidence, formatSpokenDuration } from "@/lib/session-ui";
import type { CallState } from "@/lib/session-ui";

export interface SummaryViewProps {
  state: CallState;
  onDone: () => void;
  onOpenHistory: () => void;
}

export function SummaryView({ state, onDone, onOpenHistory }: SummaryViewProps) {
  const rounds = state.rounds;
  const first = rounds[0] ?? null;
  const second = rounds[1] ?? null;
  const comparison = first && second ? compareAttempts(first, second) : [];
  const lastEvidence = rounds.length > 0 ? describeEvidence(rounds[rounds.length - 1]) : [];

  return (
    <div className={`${styles.container} ${styles.containerNarrow}`}>
      <button type="button" className={styles.ghostButton} onClick={onDone}>
        <ArrowLeftIcon size={18} />
        Done
      </button>

      <section aria-labelledby="summary-title">
        <h2 className={styles.sectionTitle} id="summary-title">
          Session summary
        </h2>
        <p className={styles.sectionLede}>
          You talked for {formatSpokenDuration(state.elapsedMs)} in {rounds.length}{" "}
          {rounds.length === 1 ? "round" : "rounds"}. Everything below comes from what was
          measured in your own audio — there is no overall score, because a single number would
          hide what was and was not measured.
        </p>

        {state.notice ? (
          <p className={styles.callNote} role="status" data-testid="summary-notice">
            {state.notice}
          </p>
        ) : null}

        {rounds.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.stateIcon}>
              <ChartIcon size={26} />
            </div>
            <h3 className={styles.emptyStateTitle}>Nothing was measured in this call</h3>
            <p className={styles.emptyStateText}>
              There was not enough speech in the round to produce a measurement, so there is
              nothing to report. That is the honest answer — it is not a zero.
            </p>
          </div>
        ) : null}

        {rounds.map((round, index) => (
          <article className={styles.panel} key={`round-${index}`} style={{ marginBottom: 16 }}>
            <h3 className={styles.panelTitle}>Round {index + 1}</h3>
            <p className={styles.panelLede}>
              {round.strengths.length > 0
                ? round.strengths.join(" ")
                : "No strength could be measured in this round."}
            </p>
            {round.improvements.length > 0 ? (
              <ul className={styles.metricList}>
                {round.improvements.map((improvement) => (
                  <li className={styles.metricItem} key={improvement}>
                    <span className={styles.metricName}>{improvement}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {describeEvidence(round).length > 0 ? (
              <div className={styles.evidenceRow} style={{ marginTop: 12 }}>
                {describeEvidence(round).map((metric) => (
                  <span
                    className={`${styles.chip} ${
                      metric.status === "available" ? "" : styles.chipInsufficient
                    }`}
                    key={`${index}-${metric.metricKey}`}
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
            ) : null}
          </article>
        ))}

        {comparison.length > 0 ? (
          <section className={styles.section} aria-labelledby="comparison-title">
            <h3 className={styles.panelTitle} id="comparison-title">
              First try and second try
            </h3>
            <p className={styles.panelLede}>
              Only the measurements both attempts share are shown, and a difference is an
              estimate from two measured values — not a promise that you improved.
            </p>
            <div className={styles.stack}>
              {comparison.map((row) => (
                <div className={styles.compareCard} key={row.metricKey}>
                  <span className={styles.metricName}>{row.label}</span>
                  <span className={styles.compareValues}>
                    <span>
                      First try:{" "}
                      {row.first?.status === "available"
                        ? row.first.text
                        : (row.first?.text ?? "not measured")}
                    </span>
                    <span>
                      Second try:{" "}
                      {row.second?.status === "available"
                        ? row.second.text
                        : (row.second?.text ?? "not measured")}
                    </span>
                  </span>
                  {row.differenceText ? (
                    <span className={styles.compareEstimate}>{row.differenceText}</span>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {lastEvidence.length > 0 && rounds.length < 2 ? (
          <section className={styles.section} aria-labelledby="last-measurements">
            <h3 className={styles.panelTitle} id="last-measurements">
              What was measured
            </h3>
            <ul className={styles.metricList}>
              {lastEvidence.map((metric) => (
                <li className={styles.metricItem} key={metric.metricKey}>
                  <span className={styles.metricName}>{metric.label}</span>
                  <span
                    className={`${styles.metricValue} ${
                      metric.status === "available" ? "" : styles.metricValueMuted
                    }`}
                  >
                    {metric.text}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className={styles.section} aria-labelledby="audio-title">
          <h3 className={styles.panelTitle} id="audio-title">
            Your audio
          </h3>
          <p className={styles.panelLede}>
            A recording is only kept if you turned &ldquo;save the recording&rdquo; on and you are
            signed in. Open your progress to replay it — if it was not kept, there is no replay
            button at all.
          </p>
          <button type="button" className={styles.secondaryButton} onClick={onOpenHistory}>
            <PlayIcon size={18} />
            Open my progress
          </button>
        </section>
      </section>
    </div>
  );
}

export default SummaryView;
