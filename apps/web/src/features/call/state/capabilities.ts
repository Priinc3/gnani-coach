/**
 * The capability register — Phase 04.
 *
 * The register (`packages/contracts/data/capabilities.json`) is the honest
 * source for what may be shown. `docs/contracts/capability-states.md` §4
 * says the web app reads it: the `renderedState` decides whether a metric
 * may be shown at all, or whether the "not enough evidence" state is shown
 * instead.
 *
 * Two rules from that file are enforced in the UI:
 *
 * - `filler-localization` is **unvalidated**, so a filler count is never
 *   shown — the app renders the insufficient-evidence state with the reason
 *   `filler_detection_unvalidated`;
 * - no capability claims `validated` in this freeze, so nothing in the
 *   interface may promise a validated measurement.
 */

import register from "../../../../../../packages/contracts/data/capabilities.json";

export type CapabilityState = "unvalidated" | "validated_synthetic_only" | "validated";

export type RenderedState = "available" | "insufficient_evidence";

export interface CapabilityEntry {
  id: string;
  state: CapabilityState;
  renderedState: RenderedState;
  goal: string;
  validatedAt: string | null;
  validatedBy: string | null;
  unavailabilityReason: string;
  notes: string[];
}

const raw = register.capabilities as Record<
  string,
  {
    id: string;
    state: CapabilityState;
    renderedState: RenderedState;
    goal: string;
    validatedAt: string | null;
    validatedBy: string | null;
    unavailabilityReason: string;
    notes: string[];
  }
>;

/** Every capability in the register, in the register's own order. */
export const CAPABILITIES: CapabilityEntry[] = Object.keys(raw).map((key) => raw[key]);

/** The plain-word label of a capability state. */
export function describeCapabilityState(entry: CapabilityEntry): string {
  switch (entry.state) {
    case "unvalidated":
      return "Unvalidated — no check has passed";
    case "validated_synthetic_only":
      return "Checked on generated signals only";
    case "validated":
      return "Validated";
    default:
      return "Unknown";
  }
}

/** The plain-word label of what the app may show for a capability. */
export function describeRenderedState(entry: CapabilityEntry): string {
  return entry.renderedState === "available"
    ? "A measurement can be shown"
    : "Shown as “not enough evidence”, never as a number";
}
