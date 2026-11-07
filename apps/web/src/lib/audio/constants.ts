/**
 * The frozen capture format — Phase 04.
 *
 * These numbers are the wire contract with the voice service, and they are
 * not free choices:
 *
 * - 16 kHz, mono, signed 16-bit little-endian PCM (`s16le`);
 * - exactly **1,024 bytes** per binary frame (512 samples, 32 ms of audio).
 *
 * `docs/contracts/call-transport.md` §6 ("Caps") pins the frame size, and
 * `prompts/parallel-G1/ADDENDUM.md` §D pins the sample rate and the frame
 * cadence for G1. The service rejects anything else with an
 * `unsupported_audio_format` error and closes the socket.
 */

/** The sample rate the voice service accepts for learner audio. */
export const CAPTURE_SAMPLE_RATE_HZ = 16000;

/** Signed 16-bit little-endian PCM, mono. */
export const CAPTURE_SAMPLE_FORMAT = "s16le";

/** One channel. */
export const CAPTURE_CHANNELS = 1;

/** Bytes in one binary frame — the documented provider frame size. */
export const FRAME_BYTE_LENGTH = 1024;

/** Samples in one binary frame (1,024 bytes / 2 bytes per sample). */
export const FRAME_SAMPLE_COUNT = FRAME_BYTE_LENGTH / 2;

/** How long one frame lasts at 16 kHz: 512 / 16,000 = 32 ms. */
export const FRAME_INTERVAL_MS = (FRAME_SAMPLE_COUNT / CAPTURE_SAMPLE_RATE_HZ) * 1000;

/** The maximum size of a JSON control message (16 KiB). */
export const MAX_JSON_MESSAGE_BYTES = 16 * 1024;
