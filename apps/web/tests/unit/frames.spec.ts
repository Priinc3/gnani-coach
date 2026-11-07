/**
 * The frame packer and the PCM helpers — Phase 04.
 *
 * Pure logic, no browser: the wire format is checked here so that a frame
 * that is not exactly 1,024 bytes can never reach the socket.
 */

import { expect, test } from "@playwright/test";

import {
  FRAME_BYTE_LENGTH,
  FRAME_SAMPLE_COUNT,
  FRAME_INTERVAL_MS,
} from "../../src/lib/audio/constants";
import { FramePacker, fromS16LeBytes, isLegalFrame, toS16LeBytes } from "../../src/lib/audio/frames";

test("the frozen frame is 1,024 bytes of 16 kHz mono s16le (32 ms)", () => {
  expect(FRAME_BYTE_LENGTH).toBe(1024);
  expect(FRAME_SAMPLE_COUNT).toBe(512);
  expect(FRAME_INTERVAL_MS).toBe(32);
});

test("samples are converted to little-endian bytes and back", () => {
  const samples = new Int16Array([0, 1, -1, 32767, -32768, 258]);
  const bytes = toS16LeBytes(samples);
  expect(bytes.length).toBe(samples.length * 2);
  // Little endian: the low byte comes first.
  expect(bytes[0]).toBe(0);
  expect(bytes[1]).toBe(0);
  expect(bytes[2]).toBe(1);
  expect(bytes[3]).toBe(0);
  expect(bytes[4]).toBe(255);
  expect(bytes[5]).toBe(255);
  const back = fromS16LeBytes(bytes);
  expect(Array.from(back)).toEqual(Array.from(samples));
});

test("the packer hands back only whole 1,024-byte frames", () => {
  const packer = new FramePacker();
  const bytes = new Uint8Array(1024 * 2 + 500);
  const frames = packer.push(bytes);
  expect(frames.length).toBe(2);
  for (const frame of frames) {
    expect(frame.length).toBe(FRAME_BYTE_LENGTH);
    expect(isLegalFrame(frame)).toBe(true);
  }
  // The remainder is held back: a partial frame is never sent.
  expect(packer.pendingByteLength()).toBe(500);
  const more = packer.push(new Uint8Array(524));
  expect(more.length).toBe(1);
  expect(more[0].length).toBe(FRAME_BYTE_LENGTH);
  expect(packer.pendingByteLength()).toBe(0);
});

test("the packer never emits a frame that is not exactly 1,024 bytes", () => {
  const packer = new FramePacker();
  const frames = packer.push(new Uint8Array(3000));
  for (const frame of frames) {
    expect(frame.length).toBe(1024);
  }
  expect(isLegalFrame(new Uint8Array(1023))).toBe(false);
  expect(isLegalFrame(new Uint8Array(1025))).toBe(false);
});

test("the packer keeps the bytes in order", () => {
  const packer = new FramePacker();
  const source = new Uint8Array(1024);
  for (let index = 0; index < source.length; index += 1) {
    source[index] = index % 251;
  }
  const frames = packer.push(source);
  expect(frames.length).toBe(1);
  expect(Array.from(frames[0])).toEqual(Array.from(source));
});
