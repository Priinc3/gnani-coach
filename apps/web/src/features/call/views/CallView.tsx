"use client";

/**
 * The call screen — Phase 04.
 *
 * Mobile screen 4 of the reference flow, and the desktop equivalent.
 *
 * The rules this screen keeps:
 *
 * - the **status comes only from `status` events**. Nothing here guesses
 *   whether the coach is listening, thinking or speaking;
 * - the transcript is **transient** and is cleared when the call ends;
 * - an interruption stops the coach's audio at once, and the app never
 *   claims that the speech request was cancelled — it says the coach
 *   stopped talking;
 * - the timer counts the call, the cap is ten minutes, and the warning
 *   comes at nine.
 */

import styles from "../app.module.css";
import { CoachAvatar } from "../components/CoachAvatar";
import {
  AlertIcon,
  LightbulbIcon,
  MicIcon,
  MicOffIcon,
  PhoneEndIcon,
  SpeakerIcon,
  SpeakerOffIcon,
} from "../components/Icon";
import { formatClock } from "@/lib/session-ui";
import type { CallState } from "@/lib/session-ui";

export interface CallViewProps {
  state: CallState;
  onEnd: () => void;
  onMute: (muted: boolean) => void;
  onSpeaker: (on: boolean) => void;
  onTranscriptVisible: (visible: boolean) => void;
  onCoachNow: () => void;
  /** Start the call again — only offered when the error says it may work. */
  onRetry: () => void;
  /** Whether the learner has a verified session (a sign-out is offered). */
  signedIn?: boolean;
  /** End the session; the call socket is closed by the sign-out handler. */
  onSignOut?: () => void;
}

interface StatusLabel {
  text: string;
  tone: "idle" | "live" | "warn" | "error";
}

/**
 * The label for a status.
 *
 * A `status` event is the only thing that may change this. Before the
 * first one arrives the app is honest about the fact that it is still
 * connecting.
 */
export function describeStatus(state: CallState): StatusLabel {
  const slow = state.status === null || state.status === "connecting";
  if (state.reconnecting) {
    // The client knows the connection was lost and a new one is opening.
    // This is the client's own fact, not a guess about the service.
    return { text: "Reconnecting…", tone: "warn" };
  }
  switch (state.status) {
    case "ready":
      return { text: "Ready when you are", tone: "live" };
    case "listening":
      return { text: "Listening", tone: "live" };
    case "thinking":
      return { text: "Thinking", tone: "live" };
    case "speaking":
      return { text: "Speaking", tone: "live" };
    case "coaching":
      return { text: "Giving you feedback", tone: "live" };
    case "reconnecting":
      return { text: "Reconnecting…", tone: "warn" };
    case "ended":
      return { text: "Call ended", tone: "idle" };
    case "error":
      return { text: "Something went wrong", tone: "error" };
    case "connecting":
      return { text: "Connecting…", tone: "idle" };
    case "heartbeat":
      return { text: "Connected", tone: "live" };
    case null:
    default:
      return slow && state.elapsedMs > 1000
        ? { text: "Still connecting to the coach…", tone: "warn" }
        : { text: "Connecting…", tone: "idle" };
  }
}

export function CallView({
  state,
  onEnd,
  onMute,
  onSpeaker,
  onTranscriptVisible,
  onCoachNow,
  onRetry,
  signedIn = false,
  onSignOut,
}: CallViewProps) {
  const status = describeStatus(state);
  const speaking = state.status === "speaking" || state.status === "coaching";
  const thinking = state.status === "thinking";
  const showTranscript = state.transcriptVisible;
  // "Try again" is offered only when the shape says retrying could work.
  const canRetry = state.error?.retryable === true || state.localError?.retryable === true;

  return (
    <div className={styles.callScreen}>
      <div className={styles.callTop}>
        <span
          className={styles.timer}
          data-testid="call-timer"
          aria-label={`Call time ${formatClock(state.elapsedMs)}`}
        >
          {formatClock(state.elapsedMs)}
        </span>
        <button type="button" className={styles.endButton} onClick={onEnd}>
          <PhoneEndIcon size={18} />
          End
        </button>
        {signedIn && onSignOut ? (
          <button
            type="button"
            className={styles.smallButton}
            onClick={onSignOut}
            data-testid="call-sign-out"
          >
            Sign out
          </button>
        ) : null}
      </div>

      <div className={styles.callBody}>
        {state.warning ? (
          <p className={styles.warningBanner} role="status">
            <AlertIcon size={16} /> {state.warning}
          </p>
        ) : null}

        {state.notice ? (
          <p className={styles.callNote} role="status" data-testid="call-notice">
            {state.notice}
          </p>
        ) : null}

        {state.error ? (
          <div className={styles.callError} role="alert">
            <p className={styles.callErrorTitle}>{state.error.title}</p>
            <p className={styles.callErrorText}>{state.error.message}</p>
            <p className={styles.callErrorText}>{state.error.advice}</p>
          </div>
        ) : null}

        {state.localError ? (
          <div className={styles.callError} role="alert">
            <p className={styles.callErrorTitle}>{state.localError.title}</p>
            <p className={styles.callErrorText}>{state.localError.message}</p>
            <p className={styles.callErrorText}>{state.localError.advice}</p>
          </div>
        ) : null}

        {state.micFailure ? (
          <div className={styles.callError} role="alert">
            <p className={styles.callErrorTitle}>We could not use your microphone</p>
            <p className={styles.callErrorText}>{state.micFailure.message}</p>
            <p className={styles.callErrorText}>
              {state.micFailure.canRetry
                ? "You can start the call again once it is ready."
                : "This will not change on this device."}
            </p>
          </div>
        ) : null}

        {canRetry || state.micFailure?.canRetry ? (
          <div className={styles.giveMeAMoment}>
            <button
              type="button"
              className={styles.ghostButton}
              onClick={onRetry}
              data-testid="call-retry"
            >
              Try again
            </button>
          </div>
        ) : null}

        <div className={styles.avatarStage}>
          <span
            className={`${styles.pulseRing} ${
              speaking ? styles.pulseRingSpeaking : thinking ? styles.pulseRingThinking : ""
            }`}
            aria-hidden="true"
          />
          <div className={styles.avatarCircle}>
            <CoachAvatar size={200} />
          </div>
        </div>

        <p className={styles.statusPill} role="status" aria-live="polite" data-testid="call-status">
          <span
            className={`${styles.statusDot} ${
              status.tone === "live"
                ? styles.statusDotLive
                : status.tone === "warn"
                  ? styles.statusDotWarn
                  : status.tone === "error"
                    ? styles.statusDotError
                    : ""
            }`}
            aria-hidden="true"
          />
          {status.text}
        </p>

        <div className={styles.coachBubble} aria-live="polite">
          {state.coachText ? (
            <p>{state.coachText}</p>
          ) : (
            <p className={styles.muted}>
              {state.interrupted
                ? "The coach stopped talking so you could continue."
                : "The coach is listening."}
            </p>
          )}
        </div>

        {state.interrupted ? (
          <p className={styles.callNote} role="status">
            You spoke over the coach, so the coach stopped. The request was not cancelled — it
            may still finish on the service.
          </p>
        ) : null}

        {showTranscript ? (
          <div className={styles.transcriptBox} aria-label="Live transcript">
            {state.transcript.length === 0 && !state.partialTranscript ? (
              <p className={styles.transcriptLine}>Nothing has been said yet.</p>
            ) : null}
            {state.transcript.map((line, index) => (
              <p className={styles.transcriptLine} key={`${index}-${line.slice(0, 12)}`}>
                {line}
              </p>
            ))}
            {state.partialTranscript ? (
              <p className={styles.transcriptPartial}>{state.partialTranscript}</p>
            ) : null}
          </div>
        ) : null}

        <div className={styles.controlRow}>
          <button
            type="button"
            className={`${styles.controlButton} ${state.muted ? styles.controlButtonActive : ""}`}
            onClick={() => onMute(!state.muted)}
            aria-pressed={state.muted}
          >
            <span className={styles.controlButtonIcon} aria-hidden="true">
              {state.muted ? <MicOffIcon size={22} /> : <MicIcon size={22} />}
            </span>
            {state.muted ? "Microphone off" : "Mute"}
          </button>

          <button
            type="button"
            className={`${styles.controlButton} ${state.speakerOn ? "" : styles.controlButtonActive}`}
            onClick={() => onSpeaker(!state.speakerOn)}
            aria-pressed={!state.speakerOn}
          >
            <span className={styles.controlButtonIcon} aria-hidden="true">
              {state.speakerOn ? <SpeakerIcon size={22} /> : <SpeakerOffIcon size={22} />}
            </span>
            {state.speakerOn ? "Speaker on" : "Speaker off"}
          </button>

          <button
            type="button"
            className={`${styles.controlButton} ${state.muted ? styles.controlButtonActive : ""}`}
            onClick={() => onMute(!state.muted)}
          >
            <span className={styles.controlButtonIcon} aria-hidden="true">
              <LightbulbIcon size={22} />
            </span>
            Give me a moment
          </button>
        </div>

        <div className={styles.giveMeAMoment}>
          <p className={styles.fieldHelp}>
            &ldquo;Give me a moment&rdquo; turns your microphone off, so the coach cannot hear you
            while you think. It is the same pause the mute control uses.
          </p>
        </div>

        <div className={styles.giveMeAMoment}>
          <button type="button" className={styles.ghostButton} onClick={onCoachNow}>
            Coach me now
          </button>
        </div>

        <div className={styles.giveMeAMoment}>
          <button
            type="button"
            className={styles.ghostButton}
            onClick={() => onTranscriptVisible(!showTranscript)}
            aria-pressed={showTranscript}
          >
            {showTranscript ? "Hide the transcript" : "Show the transcript"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default CallView;
