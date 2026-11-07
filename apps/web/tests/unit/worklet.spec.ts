/**
 * The capture worklet — Phase 04.
 *
 * The worklet runs in the AudioWorkletGlobalScope, so it is tested by
 * loading the file itself with the two globals it needs
 * (`AudioWorkletProcessor` and `registerProcessor`) and then feeding it
 * quanta of 128 samples, the way the browser does.
 *
 * What is proved here:
 *
 * - the output is **16 kHz** (the ratio of input samples to output samples);
 * - every emitted frame is **exactly 1,024 bytes**;
 * - a frame is emitted every **32 ms** of input (12 quanta at 48 kHz);
 * - the samples survive the round trip as signed 16-bit little-endian.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { FRAME_BYTE_LENGTH } from "../../src/lib/audio/constants";

/** A block of samples the worklet can read. */
type SampleBlock = { length: number; [index: number]: number };

interface WorkletPort {
  postMessage: (data: ArrayBuffer) => void;
  onmessage: ((event: { data: unknown }) => void) | null;
}

interface WorkletProcessorInstance {
  process: (inputs: SampleBlock[][]) => boolean;
  port: WorkletPort;
}

type ProcessorConstructor = new () => WorkletProcessorInstance;

const WORKLET_PATH = resolve(__dirname, "../../src/lib/audio/capture-worklet.js");

/**
 * Load the worklet the way the browser does.
 *
 * The worklet runs in the AudioWorkletGlobalScope, so it is evaluated as a
 * script with the two globals it needs. The source is read from the file
 * that ships with the app, so the test exercises the real worklet and not
 * a copy of it.
 */
function loadProcessor(sampleRate: number): ProcessorConstructor {
  const source = readFileSync(WORKLET_PATH, "utf8");
  let registered: ProcessorConstructor | null = null;

  class FakeProcessor {
    port: WorkletPort = {
      postMessage: () => undefined,
      onmessage: null,
    };
  }

  const evaluate = new Function(
    "AudioWorkletProcessor",
    "registerProcessor",
    "sampleRate",
    source,
  ) as (
    processor: new () => { port: WorkletPort },
    register: (name: string, ctor: unknown) => void,
    rate: number,
  ) => void;

  evaluate(
    FakeProcessor,
    (_name: string, ctor: unknown) => {
      registered = ctor as ProcessorConstructor;
    },
    sampleRate,
  );

  if (!registered) {
    throw new Error("the capture worklet did not register itself");
  }
  return registered;
}

/** Feed a constant signal and collect the frames the worklet emits. */
function run(
  processor: WorkletProcessorInstance,
  quanta: number,
  value = 0.5,
): ArrayBuffer[] {
  const frames: ArrayBuffer[] = [];
  const originalPost = processor.port.postMessage;
  processor.port.postMessage = (data: ArrayBuffer) => {
    frames.push(data);
    originalPost(data);
  };
  const quantum = new Float32Array(128);
  quantum.fill(value);
  for (let index = 0; index < quanta; index += 1) {
    processor.process([[quantum]]);
  }
  return frames;
}

test("the worklet emits 1,024-byte frames every 32 ms of input", async () => {
  const processor = new (loadProcessor(48000))();

  // Twelve quanta of 128 samples at 48 kHz are 32 ms of audio.
  const frames = run(processor, 12);
  expect(frames.length).toBe(1);
  expect(frames[0].byteLength).toBe(FRAME_BYTE_LENGTH);

  // Another 12 quanta produce exactly one more frame: the cadence is real
  // time, and the frame size never changes.
  const more = run(processor, 12);
  expect(more.length).toBe(1);
  expect(more[0].byteLength).toBe(FRAME_BYTE_LENGTH);
});

test("the worklet downsamples 48 kHz to 16 kHz", async () => {
  const processor = new (loadProcessor(48000))();
  // 384 quanta of 128 samples are 49,152 input samples at 48 kHz. At
  // 16 kHz that is exactly 16,384 samples, which is 32 whole frames.
  const frames = run(processor, 384);
  expect(frames.length).toBe(32);
  const totalSamples = frames.reduce((sum, frame) => sum + frame.byteLength / 2, 0);
  expect(totalSamples).toBe(16_384);
  for (const frame of frames) {
    expect(frame.byteLength).toBe(FRAME_BYTE_LENGTH);
  }
});

test("the worklet writes signed 16-bit little-endian samples", async () => {
  const processor = new (loadProcessor(16000))();
  const frames = run(processor, 4, 0.5);
  expect(frames.length).toBe(1);
  const view = new DataView(frames[0]);
  // 0.5 in signed 16-bit is 16383 (0.5 x 32767), little endian.
  expect(view.getInt16(0, true)).toBe(16383);
  expect(view.getInt16(2, true)).toBe(16383);
});

test("a muted worklet keeps the cadence and carries silence", async () => {
  const processor = new (loadProcessor(48000))();
  processor.port.onmessage?.({ data: { type: "mute", muted: true } });
  const muted = run(processor, 12, 0.5);
  // The frame still arrives on time, and it carries silence.
  expect(muted.length).toBe(1);
  const view = new DataView(muted[0]);
  expect(view.getInt16(0, true)).toBe(0);
  expect(view.getInt16(1000, true)).toBe(0);
});

test("the worklet keeps the signal level through the resampler", async () => {
  const processor = new (loadProcessor(48000))();
  const frames = run(processor, 12, -0.25);
  expect(frames.length).toBe(1);
  const view = new DataView(frames[0]);
  // -0.25 in signed 16-bit is -8192.
  expect(view.getInt16(0, true)).toBe(-8192);
});
