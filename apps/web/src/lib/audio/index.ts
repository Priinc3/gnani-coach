/**
 * The audio layer — Phase 04.
 *
 * Capture (microphone → 16 kHz mono s16le → 1,024-byte frames) and playback
 * (the coach's TTS chunks, in order per turn).
 */

export {
  CAPTURE_CHANNELS,
  CAPTURE_SAMPLE_FORMAT,
  CAPTURE_SAMPLE_RATE_HZ,
  FRAME_BYTE_LENGTH,
  FRAME_INTERVAL_MS,
  FRAME_SAMPLE_COUNT,
  MAX_JSON_MESSAGE_BYTES,
} from "./constants";
export {
  CAPTURE_CONSTRAINTS,
  CAPTURE_PROCESSOR_NAME,
  describeMicFailure,
  isCaptureSupported,
  startCapture,
} from "./capture";
export type { CaptureHandle, CaptureOptions, MicFailure, MicErrorKind } from "./capture";
export { FramePacker, fromS16LeBytes, isLegalFrame, toS16LeBytes } from "./frames";
export { rmsOfFrame, SpeechOnsetDetector } from "./level";
export type { SpeechOnsetOptions } from "./level";
export { CoachAudioPlayer } from "./playback";
