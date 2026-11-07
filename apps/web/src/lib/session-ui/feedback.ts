/**
 * Turning measurements into plain words — Phase 04.
 *
 * The rules this module exists to enforce:
 *
 * - **Every metric uses its own status.** `available` shows the number;
 *   `unavailable` and `insufficient_evidence` show plain words and no
 *   number at all. A missing measurement is never `0`.
 * - **Filled pauses are always the insufficient-evidence state.** The
 *   filler capability is unvalidated
 *   (`docs/contracts/capability-states.md`, `prompts/parallel-G1/ADDENDUM.md`
 *   §H), so the reason is always `filler_detection_unvalidated` and there
 *   is never a count.
 * - A **retry comparison** only shows metrics that both attempts measured
 *   with the same definition, and a difference is only computed from two
 *   available values. When it is computed it is labelled as an estimate.
 */

import type {
  EvidenceEntry,
  EvidenceUnit,
  MeasurementStatus,
  MetricKey,
  RoundFeedbackPayload,
} from "../transport/types";

/** The reason code used for the unvalidated filler capability. */
export const FILLER_REASON = "filler_detection_unvalidated";

/** The plain-word label of every metric the contract knows. */
export const METRIC_LABELS: Record<MetricKey, string> = {
  "pause.longest_ms": "Longest pause",
  "pause.count": "Number of pauses",
  "filler.count": "Filled pauses",
  "speech.rate_wpm": "Speaking rate",
  "speech.active_rate_wpm": "Speaking rate while speaking",
  "turn.duration_ms": "Length of your turn",
};

/** The plain-word reason for a metric that could not be measured. */
export function insufficientReason(metricKey: MetricKey): string {
  if (metricKey === "filler.count") {
    return "Counting filled pauses has not been validated, so we do not report a number.";
  }
  return "There was not enough speech in this round to measure this.";
}

/** The plain-word reason for a metric the service did not produce. */
export function unavailableReason(): string {
  return "This was not measured in this round.";
}

/** Format a measured value with its unit. */
export function formatMetricValue(value: number, unit: EvidenceUnit | null): string {
  if (unit === "milliseconds") {
    return `${Math.round(value).toLocaleString("en")} ms`;
  }
  if (unit === "count") {
    return `${Math.round(value).toLocaleString("en")}`;
  }
  if (unit === "words_per_minute") {
    return `${Math.round(value).toLocaleString("en")} words per minute`;
  }
  return `${Math.round(value).toLocaleString("en")}`;
}

export interface MetricView {
  metricKey: MetricKey;
  label: string;
  status: MeasurementStatus;
  /** The line shown to the learner. */
  text: string;
  /** The measured value, only when the status is `available`. */
  value: number | null;
  unit: EvidenceUnit | null;
}

/** Turn one evidence entry into a view the UI can render honestly. */
export function describeMetric(entry: EvidenceEntry): MetricView {
  const label = METRIC_LABELS[entry.metricKey] ?? entry.metricKey;
  if (entry.status === "available" && typeof entry.value === "number") {
    return {
      metricKey: entry.metricKey,
      label,
      status: "available",
      text: formatMetricValue(entry.value, entry.unit ?? null),
      value: entry.value,
      unit: entry.unit ?? null,
    };
  }
  if (entry.status === "unavailable") {
    return {
      metricKey: entry.metricKey,
      label,
      status: "unavailable",
      text: unavailableReason(),
      value: null,
      unit: null,
    };
  }
  return {
    metricKey: entry.metricKey,
    label,
    status: "insufficient_evidence",
    text: insufficientReason(entry.metricKey),
    value: null,
    unit: null,
  };
}

/** The evidence of a round, as views. */
export function describeEvidence(feedback: RoundFeedbackPayload): MetricView[] {
  return (feedback.evidence ?? []).map(describeMetric);
}

/** One row of a retry comparison. */
export interface ComparisonRow {
  metricKey: MetricKey;
  label: string;
  /** The first attempt's value, or null when it was not measured. */
  first: MetricView | null;
  /** The second attempt's value, or null when it was not measured. */
  second: MetricView | null;
  /** The difference, only when both attempts have an available value. */
  difference: number | null;
  /** The difference in plain words, labelled as an estimate. */
  differenceText: string | null;
}

function findEvidence(
  feedback: RoundFeedbackPayload,
  metricKey: MetricKey,
): EvidenceEntry | undefined {
  return (feedback.evidence ?? []).find((entry) => entry.metricKey === metricKey);
}

/**
 * Compare two attempts of the same thing.
 *
 * Only the metrics **both** attempts carry are shown — the metric key is
 * the definition, so two different keys are never compared. A difference is
 * computed only from two available values, and is labelled an estimate.
 */
export function compareAttempts(
  first: RoundFeedbackPayload,
  second: RoundFeedbackPayload,
): ComparisonRow[] {
  const rows: ComparisonRow[] = [];
  const keys = new Set<MetricKey>();
  for (const entry of first.evidence ?? []) {
    keys.add(entry.metricKey);
  }
  for (const entry of second.evidence ?? []) {
    keys.add(entry.metricKey);
  }

  for (const metricKey of keys) {
    const firstEntry = findEvidence(first, metricKey);
    const secondEntry = findEvidence(second, metricKey);
    if (!firstEntry || !secondEntry) {
      // Only the metrics both attempts have are shown.
      continue;
    }
    const firstView = describeMetric(firstEntry);
    const secondView = describeMetric(secondEntry);
    const comparable =
      firstView.status === "available" &&
      secondView.status === "available" &&
      firstView.value !== null &&
      secondView.value !== null;
    const difference = comparable ? (secondView.value as number) - (firstView.value as number) : null;
    rows.push({
      metricKey,
      label: firstView.label,
      first: firstView,
      second: secondView,
      difference,
      differenceText: comparable
        ? `Estimated difference: ${formatSigned(difference as number, secondView.unit)}.`
        : null,
    });
  }
  return rows;
}

function formatSigned(value: number, unit: EvidenceUnit | null): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  const absolute = Math.abs(value);
  if (unit === "milliseconds") {
    return `${sign}${Math.round(absolute).toLocaleString("en")} ms`;
  }
  if (unit === "count") {
    return `${sign}${Math.round(absolute).toLocaleString("en")}`;
  }
  if (unit === "words_per_minute") {
    return `${sign}${Math.round(absolute).toLocaleString("en")} words per minute`;
  }
  return `${sign}${Math.round(absolute).toLocaleString("en")}`;
}

/** Format a duration for the call timer: `mm:ss`. */
export function formatClock(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/** Format a duration in plain words: "2 min 30 s". */
export function formatSpokenDuration(milliseconds: number): string {
  const total = Math.max(0, Math.round(milliseconds / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes === 0) {
    return `${seconds} second${seconds === 1 ? "" : "s"}`;
  }
  if (seconds === 0) {
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  return `${minutes} min ${seconds} s`;
}
