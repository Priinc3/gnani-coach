/**
 * The feedback wording and the retry comparison — Phase 04.
 *
 * The rules this file protects:
 *
 * - every metric shows **its own status**, and a missing measurement is
 *   never `0`;
 * - **filled pauses are always the insufficient-evidence state**;
 * - a comparison shows only the metrics both attempts measured, and a
 *   difference is computed only from two available values and is labelled
 *   an estimate.
 */

import { expect, test } from "@playwright/test";

import {
  compareAttempts,
  describeMetric,
  FILLER_REASON,
  formatClock,
  formatSpokenDuration,
} from "../../src/lib/session-ui/feedback";

test("an available metric shows its value and its unit", () => {
  const view = describeMetric({
    metricKey: "pause.longest_ms",
    status: "available",
    value: 1180,
    unit: "milliseconds",
  });
  expect(view.status).toBe("available");
  expect(view.value).toBe(1180);
  expect(view.text).toBe("1,180 ms");
});

test("a metric that was not measured shows plain words and no number", () => {
  const view = describeMetric({
    metricKey: "speech.rate_wpm",
    status: "unavailable",
    value: null,
    unit: null,
  });
  expect(view.status).toBe("unavailable");
  expect(view.value).toBeNull();
  expect(view.text).toBe("This was not measured in this round.");
  expect(view.text).not.toMatch(/\d/);
});

test("filled pauses are always the insufficient-evidence state", () => {
  const view = describeMetric({
    metricKey: "filler.count",
    status: "insufficient_evidence",
    value: null,
    unit: null,
  });
  expect(view.status).toBe("insufficient_evidence");
  expect(view.value).toBeNull();
  expect(view.text).toContain("not been validated");
  expect(view.text).not.toMatch(/\b0\b/);
  expect(FILLER_REASON).toBe("filler_detection_unvalidated");
});

test("a filler count is never shown even when a value arrives", () => {
  const view = describeMetric({
    metricKey: "filler.count",
    status: "insufficient_evidence",
    value: 0,
    unit: "count",
  });
  expect(view.value).toBeNull();
  expect(view.text).not.toContain("0");
});

test("a comparison shows only the metrics both attempts measured", () => {
  const first = {
    strengths: [],
    improvements: [],
    evidence: [
      { metricKey: "pause.longest_ms" as const, status: "available" as const, value: 1000, unit: "milliseconds" as const },
      { metricKey: "speech.rate_wpm" as const, status: "available" as const, value: 100, unit: "words_per_minute" as const },
    ],
  };
  const second = {
    strengths: [],
    improvements: [],
    evidence: [
      { metricKey: "pause.longest_ms" as const, status: "available" as const, value: 1400, unit: "milliseconds" as const },
      { metricKey: "turn.duration_ms" as const, status: "available" as const, value: 9000, unit: "milliseconds" as const },
    ],
  };
  const rows = compareAttempts(first, second);
  expect(rows.length).toBe(1);
  expect(rows[0].metricKey).toBe("pause.longest_ms");
  expect(rows[0].first?.text).toBe("1,000 ms");
  expect(rows[0].second?.text).toBe("1,400 ms");
  expect(rows[0].difference).toBe(400);
  expect(rows[0].differenceText).toContain("Estimated difference");
});

test("a difference is only computed from two available values", () => {
  const first = {
    strengths: [],
    improvements: [],
    evidence: [
      { metricKey: "pause.longest_ms" as const, status: "available" as const, value: 1000, unit: "milliseconds" as const },
    ],
  };
  const second = {
    strengths: [],
    improvements: [],
    evidence: [
      {
        metricKey: "pause.longest_ms" as const,
        status: "insufficient_evidence" as const,
        value: null,
        unit: null,
      },
    ],
  };
  const rows = compareAttempts(first, second);
  expect(rows.length).toBe(1);
  expect(rows[0].difference).toBeNull();
  expect(rows[0].differenceText).toBeNull();
  expect(rows[0].second?.text).toContain("not enough speech");
});

test("the clock and the spoken duration are plain", () => {
  expect(formatClock(0)).toBe("00:00");
  expect(formatClock(65_000)).toBe("01:05");
  expect(formatClock(600_000)).toBe("10:00");
  expect(formatSpokenDuration(45_000)).toBe("45 seconds");
  expect(formatSpokenDuration(60_000)).toBe("1 minute");
  expect(formatSpokenDuration(150_000)).toBe("2 min 30 s");
});
