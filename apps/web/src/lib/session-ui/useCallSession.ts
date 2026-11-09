/**
 * The call session hook — Phase 04.
 *
 * It wires the three pieces together:
 *
 * - the **transport** (`CallClient`) — one socket, the frozen envelope;
 * - the **capture** (`startCapture`) — the microphone, as 1,024-byte frames;
 * - the **playback** (`CoachAudioPlayer`) — the coach's TTS chunks.
 *
 * Everything the UI shows comes from the reducer, and the reducer is only
 * fed by real events: a `status` event, a transcript event, a coach text, a
 * round feedback or an error. Nothing is invented here.
 */

"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  CAPTURE_SAMPLE_RATE_HZ,
  CoachAudioPlayer,
  describeMicFailure,
  rmsOfFrame,
  startCapture,
  type CaptureHandle,
} from "../audio";
import {
  CallClient,
  describeLocalError,
  type LocalError,
  type PlainError,
} from "../transport";
import type {
  AudioFrameDescriptorPayload,
  RoundFeedbackPayload,
  ServerEvent,
  SessionSettings,
  StatusPayload,
} from "../transport/types";
import { callReducer, initialCallState, type CallState } from "./callState";
import { subscribeToSignOut } from "./accessToken";

export interface UseCallSessionOptions {
  /** The validated settings for this call. */
  settings: SessionSettings;
  /** The voice service WebSocket URL. */
  wsUrl: string;
  /** Called when the call ends, so the app can show the summary. */
  onEnded?: () => void;
  /** Called when a round feedback arrives, so the app can show the break. */
  onRoundFeedback?: (payload: RoundFeedbackPayload, turnId: string | null) => void;
}

export interface CallSession {
  state: CallState;
  /** Open the socket and the microphone. One call only. */
  start: () => Promise<void>;
  /** End the call. */
  end: () => void;
  /** Clear the state of a finished call, ready for the next one. */
  reset: () => void;
  /** Mute or unmute the microphone. */
  setMuted: (muted: boolean) => void;
  /** Mute or unmute the coach's voice. */
  setSpeaker: (on: boolean) => void;
  /** Show or hide the transient transcript. */
  setTranscriptVisible: (visible: boolean) => void;
  /** Repeat or reframe one answer. */
  retry: (turnId: string, focus?: string) => void;
  /** "Keep talking", "Coach me now" or "Skip feedback". */
  coachingChoice: (choice: "keep_talking" | "coach_now" | "skip_feedback") => void;
}

export function useCallSession(options: UseCallSessionOptions): CallSession {
  const [state, dispatch] = useReducer(callReducer, initialCallState);

  const clientRef = useRef<CallClient | null>(null);
  const captureRef = useRef<CaptureHandle | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const playerRef = useRef<CoachAudioPlayer | null>(null);
  const startedRef = useRef(false);
  //: True between "the learner pressed End" and the service's `ended`.
  const endingRef = useRef(false);
  //: True when the microphone track ended by itself. The capture promise
  //: can still reject because teardown closed its context; that rejection
  //: must not replace the disconnected message with a generic one.
  const micEndedRef = useRef(false);
  const startedAtRef = useRef(0);
  //: When the last server message arrived, for the "Still working…" state.
  const lastEventAtRef = useRef(0);
  //: Throttle the microphone level so the ring does not re-render every frame.
  const lastLevelAtRef = useRef(0);
  //: True while the current frame carries the learner's voice. A spoken
  //: reaction is dropped rather than queued while this is true.
  const learnerSpeakingRef = useRef(false);
  const sampleRateRef = useRef(CAPTURE_SAMPLE_RATE_HZ);
  const stateRef = useRef(state);
  const optionsRef = useRef(options);

  // The refs are updated after the render, never during it.
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const teardown = useCallback(() => {
    captureRef.current?.stop();
    captureRef.current = null;
    clientRef.current?.close();
    clientRef.current = null;
    playerRef.current?.dispose();
    playerRef.current = null;
    if (contextRef.current) {
      void contextRef.current.close().catch(() => undefined);
      contextRef.current = null;
    }
  }, []);

  // Everything is released on unmount, so no microphone track and no socket
  // outlives the page.
  useEffect(() => {
    return () => {
      teardown();
    };
  }, [teardown]);

  // A signed-out learner must not keep a live call connection open
  // (`prompts/parallel-G1/COMM.md` entry 05).
  useEffect(() => {
    let unsubscribe: (() => void) | null = null;
    let cancelled = false;
    void subscribeToSignOut(() => {
      endingRef.current = false;
      teardown();
    }).then((off) => {
      if (cancelled) {
        off();
        return;
      }
      unsubscribe = off;
    });
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [teardown]);

  // The call timer.
  useEffect(() => {
    if (state.phase !== "live" && state.phase !== "starting") {
      return;
    }
    const handle = setInterval(() => {
      dispatch({
        type: "tick",
        elapsedMs: Date.now() - startedAtRef.current,
        msSinceEvent: Date.now() - lastEventAtRef.current,
      });
    }, 500);
    return () => clearInterval(handle);
  }, [state.phase]);

  const startCaptureRef = useCallback(async () => {
    const context = contextRef.current;
    if (!context) {
      return;
    }
    try {
      const handle = await startCapture({
        context,
        onFrame: (frame) => {
          clientRef.current?.sendFrame(frame);
          const level = rmsOfFrame(frame);
          // The same cheap level the ring uses: a frame above the speech
          // threshold means the learner is talking now, so a low-priority
          // backchannel arriving this instant is dropped.
          learnerSpeakingRef.current = level >= 0.02;
          const now = Date.now();
          if (now - lastLevelAtRef.current >= 100) {
            lastLevelAtRef.current = now;
            // A little gain, so quiet speech still moves the ring. This is a
            // decorative level, never a measurement shown to the learner.
            dispatch({
              type: "mic_level",
              level: Math.min(1, level * 5),
            });
          }
        },
        onTrackEnded: () => {
          // The device was unplugged, or the operating system took the
          // microphone away. The call cannot continue: release everything
          // and tell the learner in plain words, with a retry offered.
          micEndedRef.current = true;
          endingRef.current = false;
          teardown();
          dispatch({
            type: "mic_failed",
            failure: {
              kind: "disconnected",
              message:
                "Your microphone was disconnected. Reconnect it, then start the call again.",
              canRetry: true,
            },
          });
        },
        onSpeechStart: () => {
          learnerSpeakingRef.current = true;
          const clientNow = clientRef.current;
          if (!clientNow) {
            return;
          }
          // A spoken reaction stops without any message; only the real
          // coach turn produces the "You spoke over the coach" note.
          playerRef.current?.stopBackchannels();
          const status = clientNow.currentStatus();
          if (status === "speaking" || status === "coaching") {
            // The learner spoke over the coach: stop the audio at once and
            // tell the server. The turn is fenced, so late audio for it is
            // dropped.
            clientNow.interrupt();
            playerRef.current?.stopAll();
            dispatch({ type: "interrupted" });
          }
        },
      });
      if (micEndedRef.current) {
        // The track ended while the worklet was still starting; teardown
        // already closed this context. Do not keep a handle for it.
        handle.stop();
        return;
      }
      captureRef.current = handle;
    } catch (error) {
      if (!micEndedRef.current) {
        dispatch({ type: "mic_failed", failure: describeMicFailure(error) });
      }
    }
  }, [teardown]);

  /**
   * Complete a learner-initiated end once the service has answered.
   *
   * The summary is already on screen (the caller navigated there at once),
   * but the state is not torn down until the `status ended` arrives, so
   * the not-saved notice is part of the summary instead of being lost with
   * the socket. The fallback in `end()` completes the same path if the
   * answer never comes.
   */
  const finishEnd = useCallback(() => {
    if (!endingRef.current) {
      return;
    }
    endingRef.current = false;
    teardown();
    dispatch({ type: "ended" });
    optionsRef.current.onEnded?.();
  }, [teardown]);

  const handleServerEvent = useCallback(
    (event: ServerEvent) => {
      lastEventAtRef.current = Date.now();
      switch (event.type) {
        case "status": {
          const payload = event.payload as StatusPayload;
          dispatch({ type: "status", payload });
          if (payload.state === "ready" || payload.state === "listening") {
            if (!captureRef.current) {
              void startCaptureRef();
            }
          }
          if (payload.state === "ended") {
            if (endingRef.current) {
              finishEnd();
            } else {
              // The service ended the call (the cap, or the idle timeout).
              teardown();
              optionsRef.current.onEnded?.();
            }
          }
          break;
        }
        case "transcript_partial":
        case "transcript_final": {
          // The service heard the learner: if the coach is talking, the
          // playback stops at once and the turn is fenced.
          const status = clientRef.current?.currentStatus();
          if (status === "speaking" || status === "coaching") {
            clientRef.current?.interrupt();
            playerRef.current?.stopAll();
          }
          const text = event.payload.text;
          dispatch({
            type:
              event.type === "transcript_partial" ? "transcript_partial" : "transcript_final",
            text,
          });
          break;
        }
        case "coach_text":
          dispatch({ type: "coach_text", text: event.payload.text });
          break;
        case "round_feedback":
          dispatch({
            type: "round_feedback",
            payload: event.payload,
            turnId: event.turnId ?? null,
          });
          optionsRef.current.onRoundFeedback?.(event.payload, event.turnId ?? null);
          break;
        case "audio.frame.descriptor": {
          const payload = event.payload as AudioFrameDescriptorPayload;
          sampleRateRef.current = payload.sampleRateHz;
          break;
        }
        default:
          break;
      }
    },
    [finishEnd, startCaptureRef, teardown],
  );

  const start = useCallback(async () => {
    if (startedRef.current) {
      // A second click on Start must never open a second connection.
      return;
    }
    startedRef.current = true;
    micEndedRef.current = false;
    lastEventAtRef.current = Date.now();
    dispatch({ type: "start_requested" });

    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      dispatch({ type: "local_error", error: describeLocalError("offline") });
      startedRef.current = false;
      return;
    }
    if (
      typeof window === "undefined" ||
      !window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia
    ) {
      dispatch({ type: "local_error", error: describeLocalError("unsupported_browser") });
      startedRef.current = false;
      return;
    }

    let context: AudioContext;
    try {
      context = new AudioContext();
      await context.resume();
    } catch {
      dispatch({ type: "local_error", error: describeLocalError("unsupported_browser") });
      startedRef.current = false;
      return;
    }
    contextRef.current = context;
    playerRef.current = new CoachAudioPlayer(context);
    startedAtRef.current = Date.now();

    const client = new CallClient({
      url: optionsRef.current.wsUrl,
      settings: optionsRef.current.settings,
      sampleRateHz: CAPTURE_SAMPLE_RATE_HZ,
      getToken: async () => {
        const { getCallAccessToken } = await import("./accessToken");
        return getCallAccessToken();
      },
      onEvent: (event: ServerEvent) => {
        handleServerEvent(event);
      },
      onBinary: (data, turnId, kind) => {
        playerRef.current?.appendChunk(
          turnId,
          new Uint8Array(data),
          sampleRateRef.current,
          kind,
          learnerSpeakingRef.current,
        );
      },
      onConnectionState: (connectionState) => {
        lastEventAtRef.current = Date.now();
        if (connectionState === "reconnecting") {
          dispatch({ type: "reconnecting", reconnecting: true });
        }
        if (connectionState === "failed" || connectionState === "closed") {
          dispatch({ type: "reconnecting", reconnecting: false });
        }
      },
      onLocalError: (error: LocalError) => {
        lastEventAtRef.current = Date.now();
        dispatch({ type: "local_error", error });
      },
      onServerError: (error: PlainError) => {
        lastEventAtRef.current = Date.now();
        dispatch({ type: "server_error", error });
      },
      onInterrupt: (turnId) => {
        lastEventAtRef.current = Date.now();
        playerRef.current?.stopTurn(turnId);
        dispatch({ type: "interrupted" });
      },
      onWarning: (message) => {
        lastEventAtRef.current = Date.now();
        dispatch({ type: "warning", message });
      },
      onLimitReached: () => {
        teardown();
        optionsRef.current.onEnded?.();
      },
    });
    clientRef.current = client;
    client.start();
  }, [handleServerEvent, teardown]);

  const end = useCallback(() => {
    const client = clientRef.current;
    if (!client) {
      endingRef.current = false;
      teardown();
      dispatch({ type: "ended" });
      optionsRef.current.onEnded?.();
      return;
    }
    if (endingRef.current) {
      return;
    }
    endingRef.current = true;
    // Keep the socket open until the service has answered, so the summary
    // can show the "not saved" notice. The summary itself is shown by the
    // caller at once; only the teardown waits.
    client.requestEnd();
    window.setTimeout(() => {
      if (endingRef.current) {
        finishEnd();
      }
    }, 2_300);
  }, [finishEnd, teardown]);

  const reset = useCallback(() => {
    endingRef.current = false;
    teardown();
    startedRef.current = false;
    dispatch({ type: "reset" });
  }, [teardown]);

  const setMuted = useCallback((muted: boolean) => {
    dispatch({ type: "set_muted", muted });
    captureRef.current?.setMuted(muted);
    clientRef.current?.setMuted(muted);
  }, []);

  const setSpeaker = useCallback((on: boolean) => {
    dispatch({ type: "set_speaker", on });
    playerRef.current?.setOutputEnabled(on);
  }, []);

  const setTranscriptVisible = useCallback((visible: boolean) => {
    dispatch({ type: "set_transcript_visible", visible });
  }, []);

  const retry = useCallback((turnId: string, focus?: string) => {
    clientRef.current?.retry(turnId, focus);
  }, []);

  const coachingChoice = useCallback(
    (choice: "keep_talking" | "coach_now" | "skip_feedback") => {
      clientRef.current?.coachingChoice(choice);
    },
    [],
  );

  return {
    state,
    start,
    end,
    reset,
    setMuted,
    setSpeaker,
    setTranscriptVisible,
    retry,
    coachingChoice,
  };
}
