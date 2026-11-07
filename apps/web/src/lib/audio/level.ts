/**
 * Loudness and speech-onset detection — Phase 04.
 *
 * The purpose is narrow: notice that the **learner started speaking** so
 * the coach's audio can be stopped at once (`docs/contracts/call-transport.md`
 * §5, "Stale-turn suppression"). It is not a VAD, not a turn detector and
 * not an assessment — nothing here is ever shown to the learner as a
 * measurement.
 *
 * The rules are deliberately conservative:
 *
 * - a frame counts as loud when its RMS is above `threshold`;
 * - an onset needs `consecutiveLoudFrames` loud frames in a row (so a single
 *   click does not interrupt the coach);
 * - after an onset there is a refractory period, so one utterance does not
 *   fire a dozen interruptions.
 */

import { fromS16LeBytes } from "./frames";

/** Root-mean-square level of a 16-bit little-endian frame, in 0…1. */
export function rmsOfFrame(bytes: Uint8Array): number {
  const samples = fromS16LeBytes(bytes);
  if (samples.length === 0) {
    return 0;
  }
  let sum = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const value = samples[index] / 32768;
    sum += value * value;
  }
  return Math.sqrt(sum / samples.length);
}

export interface SpeechOnsetOptions {
  /** RMS above which a frame counts as loud. */
  threshold?: number;
  /** How many loud frames in a row are needed for an onset. */
  consecutiveLoudFrames?: number;
  /** How long after an onset another onset is ignored, in milliseconds. */
  refractoryMs?: number;
}

export class SpeechOnsetDetector {
  private readonly threshold: number;
  private readonly consecutiveLoudFrames: number;
  private readonly refractoryMs: number;
  private loudRun = 0;
  private lastOnsetAtMs: number | null = null;

  constructor(options: SpeechOnsetOptions = {}) {
    this.threshold = options.threshold ?? 0.02;
    this.consecutiveLoudFrames = options.consecutiveLoudFrames ?? 3;
    this.refractoryMs = options.refractoryMs ?? 1200;
  }

  /**
   * Feed one frame. Returns true exactly on the frame where a new speech
   * onset is detected.
   */
  push(frame: Uint8Array, nowMs: number): boolean {
    const level = rmsOfFrame(frame);
    if (level >= this.threshold) {
      this.loudRun += 1;
    } else {
      this.loudRun = 0;
    }
    if (this.loudRun < this.consecutiveLoudFrames) {
      return false;
    }
    if (
      this.lastOnsetAtMs !== null &&
      nowMs - this.lastOnsetAtMs < this.refractoryMs
    ) {
      return false;
    }
    this.lastOnsetAtMs = nowMs;
    this.loudRun = 0;
    return true;
  }

  /** Forget the current utterance (used when the coach takes the floor). */
  reset(): void {
    this.loudRun = 0;
  }
}
