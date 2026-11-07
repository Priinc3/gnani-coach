/* global AudioWorkletProcessor, registerProcessor, sampleRate */

/**
 * The capture worklet — 16 kHz mono `s16le`, 1,024-byte frames.
 *
 * This file runs in the **AudioWorkletGlobalScope**, which is a separate
 * realm from the page: it cannot import application modules, and it has no
 * DOM. It is therefore deliberately self-contained — the resampler and the
 * frame packer live here, and `apps/web/src/lib/audio/frames.ts` mirrors the
 * same constants for the main thread.
 *
 * What it does, in order:
 *
 * 1. reads the microphone quantum (128 frames at the context sample rate);
 * 2. resamples it to **16 kHz** with linear interpolation, keeping the
 *    fractional read position across quanta so no sample is dropped or
 *    repeated at the seam;
 * 3. packs the result into **1,024-byte** frames (512 samples = 32 ms) and
 *    posts each frame to the main thread as a transferable buffer.
 *
 * The cadence is real time by construction: the audio graph calls
 * `process()` once per 128-frame quantum in real time, so 512 output
 * samples — one frame — are produced every 32 ms of wall clock.
 *
 * When the learner mutes, the worklet keeps the cadence but emits silence,
 * so the connection is never idle (the service closes a connection that has
 * received no client frame for 90 seconds).
 *
 * Source for the API: the AudioWorklet documentation —
 * <https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet> (checked
 * 2026-10-20).
 */

/** The output sample rate the voice service accepts. */
var TARGET_SAMPLE_RATE = 16000;

/** Samples in one frame (512 samples = 1,024 bytes). */
var FRAME_SAMPLE_COUNT = 512;

/** Bytes in one frame. */
var FRAME_BYTE_LENGTH = 1024;

function toInt16(value) {
  var clamped = value < -1 ? -1 : value > 1 ? 1 : value;
  return clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
}

class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    /** Input samples per output sample (e.g. 3 for 48 kHz -> 16 kHz). */
    this.ratio = sampleRate / TARGET_SAMPLE_RATE;
    /**
     * When the ratio is a whole number the resampler averages each group
     * of input samples (a box filter, which also keeps the highest
     * high-frequency content out of the result). Otherwise it interpolates
     * linearly between the two neighbouring samples.
     */
    this.integerRatio = Math.abs(this.ratio - Math.round(this.ratio)) < 1e-9;
    this.groupSize = Math.round(this.ratio);
    /** Input samples that have not been consumed yet. */
    this.pending = [];
    /** How many samples of `pending` the box filter has already used. */
    this.groupStart = 0;
    /** Fractional read position inside `pending` for the next output sample. */
    this.position = 0;
    /** The frame being filled. */
    this.frame = new Int16Array(FRAME_SAMPLE_COUNT);
    /** How many samples of `frame` are filled. */
    this.filled = 0;
    /** When true the frame carries silence instead of the microphone. */
    this.muted = false;
    /** Frames emitted so far, so the main thread can spot gaps. */
    this.framesSent = 0;
    this.port.onmessage = function (event) {
      var data = event.data;
      if (data && data.type === "mute") {
        this.muted = Boolean(data.muted);
      }
    }.bind(this);
  }

  /**
   * Append the quantum to the pending buffer, resample everything that can
   * be resampled, and flush complete frames.
   */
  process(inputs) {
    var channel = inputs[0] && inputs[0][0];
    var count = channel ? channel.length : 0;
    var i;
    for (i = 0; i < count; i += 1) {
      this.pending.push(channel[i]);
    }

    if (this.integerRatio) {
      this.processByAveraging();
    } else {
      this.processByInterpolation();
    }

    // Keep the processor alive: the microphone is the source of truth.
    return true;
  }

  /** Box filter: one output sample per group of `groupSize` input samples. */
  processByAveraging() {
    while (this.groupStart + this.groupSize <= this.pending.length) {
      var sum = 0;
      var i;
      for (i = 0; i < this.groupSize; i += 1) {
        sum += this.pending[this.groupStart + i];
      }
      this.pushSample(sum / this.groupSize);
      this.groupStart += this.groupSize;
    }
    if (this.groupStart > 0) {
      this.pending.splice(0, this.groupStart);
      this.groupStart = 0;
    }
  }

  /** Linear interpolation: one output sample per `ratio` input samples. */
  processByInterpolation() {
    // Resample while there is a sample *after* the read position, so the
    // interpolation always has its right-hand neighbour.
    while (this.position + 1 < this.pending.length) {
      var left = Math.floor(this.position);
      var fraction = this.position - left;
      var a = this.pending[left];
      var b = this.pending[left + 1];
      this.pushSample(a + (b - a) * fraction);
      this.position += this.ratio;
    }

    // Drop the input samples that have been consumed. The read position is
    // kept relative to what is left, so the next quantum continues exactly
    // where this one stopped.
    var drop = Math.floor(this.position);
    if (drop > this.pending.length) {
      drop = this.pending.length;
    }
    if (drop > 0) {
      this.pending.splice(0, drop);
      this.position -= drop;
    }
  }

  /** Add one output sample to the frame, flushing it when it is complete. */
  pushSample(value) {
    this.frame[this.filled] = toInt16(this.muted ? 0 : value);
    this.filled += 1;
    if (this.filled === FRAME_SAMPLE_COUNT) {
      this.flush();
    }
  }

  /** Post one 1,024-byte frame to the main thread. */
  flush() {
    var bytes = new Uint8Array(FRAME_BYTE_LENGTH);
    var view = new DataView(bytes.buffer);
    var i;
    for (i = 0; i < FRAME_SAMPLE_COUNT; i += 1) {
      view.setInt16(i * 2, this.frame[i], true);
    }
    this.filled = 0;
    this.framesSent += 1;
    this.port.postMessage(bytes.buffer, [bytes.buffer]);
  }
}

registerProcessor("gnani-capture-processor", CaptureProcessor);
