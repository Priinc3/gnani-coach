/**
 * Frame packing on the main thread — Phase 04.
 *
 * The wire format is raw PCM: no container header is ever sent mid-stream
 * (`docs/contracts/call-transport.md` §6). The capture worklet already
 * produces exact 1,024-byte frames, so this module is the **guard** rather
 * than the source: it proves that whatever is about to be sent is exactly
 * 1,024 bytes and refuses anything else.
 */

import { FRAME_BYTE_LENGTH } from "./constants";

/** Convert 16-bit samples to little-endian bytes. */
export function toS16LeBytes(samples: Int16Array): Uint8Array {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < samples.length; index += 1) {
    view.setInt16(index * 2, samples[index], true);
  }
  return bytes;
}

/** Convert little-endian bytes back to 16-bit samples. */
export function fromS16LeBytes(bytes: Uint8Array): Int16Array {
  const sampleCount = Math.floor(bytes.length / 2);
  const samples = new Int16Array(sampleCount);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let index = 0; index < sampleCount; index += 1) {
    samples[index] = view.getInt16(index * 2, true);
  }
  return samples;
}

/**
 * A byte-stream packer.
 *
 * It accepts any number of bytes and hands back only whole 1,024-byte
 * frames, keeping the remainder for the next call. The remainder is
 * deliberately never sent: a partial frame is a protocol error, not a
 * smaller message.
 */
export class FramePacker {
  private remainder: Uint8Array = new Uint8Array(0);

  /** Add bytes and return the complete frames they produced. */
  push(bytes: Uint8Array): Uint8Array[] {
    const combined = new Uint8Array(this.remainder.length + bytes.length);
    combined.set(this.remainder, 0);
    combined.set(bytes, this.remainder.length);

    const frameCount = Math.floor(combined.length / FRAME_BYTE_LENGTH);
    const frames: Uint8Array[] = [];
    for (let index = 0; index < frameCount; index += 1) {
      const start = index * FRAME_BYTE_LENGTH;
      frames.push(combined.slice(start, start + FRAME_BYTE_LENGTH));
    }
    this.remainder = combined.slice(frameCount * FRAME_BYTE_LENGTH);
    return frames;
  }

  /** The bytes held back because they do not make a whole frame yet. */
  pendingByteLength(): number {
    return this.remainder.length;
  }

  /** Forget the held-back bytes. */
  reset(): void {
    this.remainder = new Uint8Array(0);
  }
}

/** True when the buffer is exactly one legal wire frame. */
export function isLegalFrame(bytes: Uint8Array): boolean {
  return bytes.length === FRAME_BYTE_LENGTH;
}
