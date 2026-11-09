"use client";

/**
 * The call screen — Phase 17.
 *
 * One obvious thing: the learner talks, and the screen says what is
 * happening. The status is the largest text on the page and is one word
 * from the transport's own vocabulary. The transcript lives in a drawer;
 * the main screen shows at most the last coach line, clamped to two lines.
 *
 * A slow server must never look frozen: after eight seconds without a
 * server message the status becomes "Still working…" and End stays
 * enabled. The pulsing ring follows the microphone level, so the learner
 * can see they are heard before any words arrive.
 */

import { useState, type CSSProperties } from "react";

import styles from "../app.module.css";
import { CoachAvatar } from "../components/CoachAvatar";
import { MicIcon, MicOffIcon, PhoneEndIcon } from "../components/Icon";
import { formatClock } from "@/lib/session-ui";
import type { CallState } from "@/lib/session-ui";

export interface CallViewProps {
  state: CallState;
  onEnd: () => void;
  onMute: (muted: boolean) => void;
  onTranscriptVisible: (visible: boolean) => void;
  /** Start the call again — only offered when the error says it may work. */
  onRetry: () => void;
}

interface StatusLabel {
  text: string;
  tone: "idle" | "live" | "warn" | "error";
}

/**
 * The label for a status.
 *
 * A `status` event is the only thing that may change the transport state.
 * Before the first one arrives the app says it is connecting. If no server
 * message has arrived for eight seconds, the honest label is that the
 * service is still working — never a frozen screen.
 */
export function describeStatus(state: CallState): StatusLabel {
  const hasError = Boolean(state.error || state.localError || state.micFailure);
  if (
    !hasError &&
    state.msSinceEvent >= 8000 &&
    state.phase !== "ended" &&
    state.phase !== "failed"
  ) {
    return { text: "Still working…", tone: "warn" };
  }
  if (state.reconnecting) {
    return { text: "Reconnecting", tone: "warn" };
  }
  switch (state.status) {
    case "ready":
    case "listening":
      return { text: "Listening", tone: "live" };
    case "thinking":
      return { text: "Thinking", tone: "live" };
    case "speaking":
    case "coaching":
      return { text: "Speaking", tone: "live" };
    case "reconnecting":
      return { text: "Reconnecting", tone: "warn" };
    case "ended":
      return { text: "Ended", tone: "idle" };
    case "error":
      return { text: "Error", tone: "error" };
    case "connecting":
    case "heartbeat":
    case null:
    default:
      return { text: "Connecting", tone: "idle" };
  }
}

export function CallView({
  state,
  onEnd,
  onMute,
  onTranscriptVisible,
  onRetry,
}: CallViewProps) {
  const status = describeStatus(state);
  const showTranscript = state.transcriptVisible;
  const [confirmingEnd, setConfirmingEnd] = useState(false);
  const canRetry = state.error?.retryable === true || state.localError?.retryable === true;
  // One error at a time, so the learner always gets one obvious action.
  const activeError = state.micFailure ? null : (state.localError ?? state.error);

  return (
    <div className={styles.callScreen} data-testid="call-root">
      <header className={styles.callTop}>
        <span
          className={styles.timer}
          data-testid="call-timer"
          aria-label={`Call time ${formatClock(state.elapsedMs)}`}
        >
          {formatClock(state.elapsedMs)}
        </span>
        <p
          className={`${styles.callStatus} ${styles[`callStatus${status.tone}`] ?? ""}`}
          role="status"
          aria-live="polite"
          data-testid="call-status"
        >
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
        <button
          type="button"
          className={styles.smallButton}
          onClick={() => onTranscriptVisible(!showTranscript)}
          aria-pressed={showTranscript}
          aria-expanded={showTranscript}
          aria-controls="live-transcript"
        >
          Transcript
        </button>
      </header>

      <div className={styles.callBody}>
        {state.warning ? (
          <p className={styles.warningBanner} role="status">
            {state.warning}
          </p>
        ) : null}

        {state.notice ? (
          <p className={styles.callNote} role="status" data-testid="call-notice">
            {state.notice}
          </p>
        ) : null}

        {activeError ? (
          <div className={styles.callError} role="alert">
            <p className={styles.callErrorTitle}>{activeError.title}</p>
            <p className={styles.callErrorText}>{activeError.advice}</p>
            {canRetry ? (
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={onRetry}
                data-testid="call-retry"
              >
                Try again
              </button>
            ) : null}
          </div>
        ) : null}

        {state.micFailure ? (
          <div className={styles.callError} role="alert">
            <p className={styles.callErrorTitle}>We could not use your microphone</p>
            <p className={styles.callErrorText}>{state.micFailure.message}</p>
            {state.micFailure.canRetry ? (
              <button type="button" className={styles.secondaryButton} onClick={onRetry}>
                Allow microphone
              </button>
            ) : null}
          </div>
        ) : null}

        <div
          className={styles.avatarStage}
          style={{ "--mic-level": String(state.micLevel) } as CSSProperties}
        >
          <span
            className={`${styles.pulseRing} ${
              state.status === "speaking" || state.status === "coaching"
                ? styles.pulseRingSpeaking
                : state.status === "thinking"
                  ? styles.pulseRingThinking
                  : ""
            }`}
            aria-hidden="true"
          />
          <span
            className={`${styles.micRing} ${state.muted ? styles.micRingMuted : ""}`}
            aria-hidden="true"
          />
          <div className={styles.avatarCircle}>
            <CoachAvatar size={200} />
          </div>
        </div>

        {state.coachText ? (
          <div className={styles.coachBubble} aria-live="polite">
            <p className={styles.coachLine}>{state.coachText}</p>
          </div>
        ) : null}

        {state.interrupted ? (
          <p className={styles.callNote} role="status">
            You spoke over the coach, so the coach stopped.
          </p>
        ) : null}
      </div>

      <div className={styles.callControls} aria-label="Call controls">
        <button
          type="button"
          className={`${styles.callControl} ${state.muted ? styles.callControlActive : ""}`}
          onClick={() => onMute(!state.muted)}
          aria-pressed={state.muted}
        >
          <span className={styles.callControlIcon} aria-hidden="true">
            {state.muted ? <MicOffIcon size={22} /> : <MicIcon size={22} />}
          </span>
          {state.muted ? "Unmute" : "Mute"}
        </button>

        <button
          type="button"
          className={`${styles.callControl} ${styles.callControlEnd}`}
          onClick={() => setConfirmingEnd(true)}
        >
          <span className={styles.callControlIcon} aria-hidden="true">
            <PhoneEndIcon size={22} />
          </span>
          End
        </button>
      </div>

      {showTranscript ? (
        <aside className={styles.transcriptDrawer} id="live-transcript" aria-label="Live transcript">
          <span className={styles.transcriptHandle} aria-hidden="true" />
          <div className={styles.transcriptScroll}>
            {state.transcript.length === 0 && !state.partialTranscript ? (
              <p className={styles.transcriptLine}>Nothing said yet.</p>
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
          <button
            type="button"
            className={styles.ghostButton}
            onClick={() => onTranscriptVisible(false)}
          >
            Close
          </button>
        </aside>
      ) : null}

      {confirmingEnd ? (
        <div className={styles.confirmOverlay}>
          <div
            className={styles.confirmSheet}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="end-call-title"
          >
            <h2 className={styles.confirmTitle} id="end-call-title">
              End this call?
            </h2>
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.secondaryButton}
                aria-label="Stay in call"
                onClick={() => setConfirmingEnd(false)}
              >
                Stay
              </button>
              <button
                type="button"
                className={styles.endButton}
                aria-label="End call now"
                onClick={() => {
                  setConfirmingEnd(false);
                  onEnd();
                }}
              >
                <PhoneEndIcon size={18} />
                End
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default CallView;
