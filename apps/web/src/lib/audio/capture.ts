/**
 * Microphone capture — Phase 04.
 *
 * The browser side of the frozen audio format:
 *
 * - `getUserMedia` with the constraints the service expects;
 * - an `AudioWorklet` that resamples to 16 kHz mono `s16le` and emits
 *   **1,024-byte** frames in real time (the worklet source lives beside
 *   this file);
 * - plain-word recovery states when the microphone is denied, missing,
 *   busy or unavailable.
 *
 * Two things this module deliberately does **not** claim:
 *
 * - **Echo cancellation and noise suppression are requested, not
 *   guaranteed.** They are `getUserMedia` constraints: the browser may
 *   ignore them, and the service cannot know whether they were applied.
 * - The microphone is only ever opened from a **user gesture** (the Start
 *   button). Nothing on the page requests it on load.
 */

import {
  CAPTURE_CHANNELS,
  CAPTURE_SAMPLE_RATE_HZ,
  FRAME_BYTE_LENGTH,
} from "./constants";
import { SpeechOnsetDetector } from "./level";

/** The name the capture worklet registers itself under. */
export const CAPTURE_PROCESSOR_NAME = "gnani-capture-processor";

/**
 * The URL of the capture worklet.
 *
 * `new URL(..., import.meta.url)` is the Next.js supported way to reference a
 * static asset that lives next to the code: the bundler emits the file as a
 * hashed asset and hands back its URL (Next.js documents this "Asset
 * Imports" form in
 * <https://nextjs.org/docs/app/api-reference/config/next-config-js/urlImports>,
 * and Turbopack resolves the same pattern — checked 2026-10-20).
 */
const CAPTURE_WORKLET_URL = new URL("./capture-worklet.js", import.meta.url).toString();

/** The kind of microphone failure, so the UI can react differently. */
export type MicErrorKind =
  | "denied"
  | "not_found"
  | "in_use"
  | "insecure_context"
  | "unsupported"
  | "disconnected"
  | "unknown";

export interface MicFailure {
  kind: MicErrorKind;
  /** A plain-word sentence for the learner. */
  message: string;
  /** Whether trying again could plausibly work. */
  canRetry: boolean;
}

/** Plain words for every microphone failure we can recognise. */
export function describeMicFailure(error: unknown): MicFailure {
  const name =
    typeof error === "object" && error !== null && "name" in error
      ? String((error as { name?: unknown }).name)
      : "";

  switch (name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
    case "SecurityError":
      return {
        kind: "denied",
        message:
          "Your browser blocked the microphone. Allow it from the site settings, then start the call again.",
        canRetry: true,
      };
    case "NotFoundError":
    case "DevicesNotFoundError":
    case "OverconstrainedError":
      return {
        kind: "not_found",
        message:
          "We could not find a microphone. Connect one, then start the call again.",
        canRetry: true,
      };
    case "NotReadableError":
    case "TrackStartError":
    case "AbortError":
      return {
        kind: "in_use",
        message:
          "Another app is using your microphone right now. Close it, then start the call again.",
        canRetry: true,
      };
    default:
      break;
  }

  const text = error instanceof Error ? error.message : String(error ?? "");
  if (/secure context|https/i.test(text)) {
    return {
      kind: "insecure_context",
      message:
        "The microphone only works on a secure page (https) or on localhost.",
      canRetry: false,
    };
  }
  return {
    kind: "unknown",
    message:
      "We could not start the microphone. Check your microphone settings, then try again.",
    canRetry: true,
  };
}

/** True when the browser can capture audio for a live call at all. */
export function isCaptureSupported(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  if (!window.isSecureContext) {
    return false;
  }
  return (
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof window.AudioContext === "function" &&
    typeof window.AudioWorkletNode === "function"
  );
}

export interface CaptureOptions {
  /** Called with every complete 1,024-byte frame. */
  onFrame: (frame: Uint8Array) => void;
  /** Called when the learner's own speech starts (used to interrupt). */
  onSpeechStart?: () => void;
  /**
   * Called when the microphone track ends by itself (the device was
   * unplugged, or the operating system took it away). A stopped track
   * never fires ``ended``, so an ordinary stop is not reported here.
   */
  onTrackEnded?: (reason: "ended") => void;
  /** The audio context to run the worklet in. */
  context: AudioContext;
}

export interface CaptureHandle {
  /** Stop sending frames and release the microphone. */
  stop: () => void;
  /** Mute locally: the frames keep their cadence but carry silence. */
  setMuted: (muted: boolean) => void;
  /** The context sample rate the worklet resamples from. */
  readonly inputSampleRate: number;
}

/** The constraints we ask for. They are requests, not guarantees. */
export const CAPTURE_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    channelCount: CAPTURE_CHANNELS,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
  video: false,
};

/**
 * Open the microphone and start the capture worklet.
 *
 * Resolves with a handle, or rejects with the original `getUserMedia` error
 * so the caller can turn it into a plain-word recovery state.
 */
export async function startCapture(options: CaptureOptions): Promise<CaptureHandle> {
  if (typeof window === "undefined" || !window.isSecureContext) {
    const error = new Error("The microphone needs a secure context (https or localhost).");
    error.name = "InsecureContextError";
    throw error;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    const error = new Error("This browser cannot capture audio for a live call.");
    error.name = "NotSupportedError";
    throw error;
  }

  const stream = await navigator.mediaDevices.getUserMedia(CAPTURE_CONSTRAINTS);

  let stopped = false;
  const trackEnded = () => {
    if (!stopped) {
      options.onTrackEnded?.("ended");
    }
  };
  for (const track of stream.getAudioTracks()) {
    track.addEventListener("ended", trackEnded);
  }

  let source: MediaStreamAudioSourceNode;
  let node: AudioWorkletNode;
  try {
    await options.context.audioWorklet.addModule(CAPTURE_WORKLET_URL);
    source = options.context.createMediaStreamSource(stream);
    node = new AudioWorkletNode(options.context, CAPTURE_PROCESSOR_NAME, {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      channelCount: 1,
      channelCountMode: "explicit",
    });
  } catch (error) {
    for (const track of stream.getTracks()) {
      track.stop();
    }
    throw error;
  }

  // The worklet is a source, but the graph only pulls a node that is
  // connected to the destination. A muted sink keeps it running silently.
  const sink = options.context.createGain();
  sink.gain.value = 0;
  source.connect(node);
  node.connect(sink);
  sink.connect(options.context.destination);

  const detector = new SpeechOnsetDetector();

  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    if (stopped) {
      return;
    }
    const frame = new Uint8Array(event.data);
    if (frame.length !== FRAME_BYTE_LENGTH) {
      return;
    }
    options.onFrame(frame);
    if (options.onSpeechStart && detector.push(frame, Date.now())) {
      options.onSpeechStart();
    }
  };

  return {
    inputSampleRate: options.context.sampleRate,
    setMuted: (muted: boolean) => {
      node.port.postMessage({ type: "mute", muted });
      detector.reset();
    },
    stop: () => {
      stopped = true;
      node.port.onmessage = null;
      try {
        source.disconnect();
        node.disconnect();
        sink.disconnect();
      } catch {
        // Already disconnected.
      }
      for (const track of stream.getTracks()) {
        track.removeEventListener("ended", trackEnded);
        track.stop();
      }
    },
  };
}

/** The sample rate the service expects — re-exported for the start payload. */
export const CAPTURE_RATE = CAPTURE_SAMPLE_RATE_HZ;
