"use client";

/**
 * The pre-call microphone check — Phase 10.
 *
 * It does two jobs in plain words:
 *
 * - it explains the browser permission prompt **before** the learner sees
 *   it, so the prompt is not a surprise;
 * - it asks for the microphone once, on a button press, and shows a clear
 *   next step when the answer is "no" (allow it in the site settings, or
 *   in Android's app permissions inside the APK WebView, then try again).
 *
 * It never opens the microphone on page load, and it stops the test track
 * immediately after a successful check, so the call is still the only
 * thing that holds the microphone during practice.
 */

import { useCallback, useEffect, useState } from "react";

import styles from "../app.module.css";
import { CheckIcon, MicIcon, MicOffIcon } from "./Icon";

type CheckState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "ok" }
  | { kind: "denied" }
  | { kind: "unavailable"; message: string };

/** The state the browser already knows, without prompting. */
async function readPermission(): Promise<PermissionState | "unknown"> {
  if (typeof navigator === "undefined" || !navigator.permissions?.query) {
    return "unknown";
  }
  try {
    const status = await navigator.permissions.query({
      name: "microphone" as PermissionName,
    });
    return status.state;
  } catch {
    return "unknown";
  }
}

function plainReason(error: unknown): CheckState {
  const name =
    typeof error === "object" && error !== null && "name" in error
      ? String((error as { name?: unknown }).name)
      : "";
  switch (name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
    case "SecurityError":
      return { kind: "denied" };
    case "NotFoundError":
    case "DevicesNotFoundError":
    case "OverconstrainedError":
      return {
        kind: "unavailable",
        message: "No microphone was found. Connect one, then try the check again.",
      };
    case "NotReadableError":
    case "TrackStartError":
      return {
        kind: "unavailable",
        message:
          "Another app is using the microphone. Close it, then try the check again.",
      };
    default:
      break;
  }
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return {
      kind: "unavailable",
      message:
        "The microphone only works on an https page (or on localhost). Open the https address and try again.",
    };
  }
  return {
    kind: "unavailable",
    message:
      "The microphone could not be opened. Check the device settings, then try the check again.",
  };
}

export function MicCheck() {
  const [state, setState] = useState<CheckState>({ kind: "idle" });

  useEffect(() => {
    let cancelled = false;
    void readPermission().then((permission) => {
      if (cancelled || permission !== "denied") {
        return;
      }
      // The browser has already remembered "block" for this site. Saying so
      // now is more useful than asking again and failing silently.
      setState({ kind: "denied" });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const check = useCallback(async () => {
    setState({ kind: "checking" });
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState({
        kind: "unavailable",
        message:
          "This browser cannot open a microphone. Try a current Chrome, Edge, Firefox or Safari.",
      });
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      for (const track of stream.getTracks()) {
        track.stop();
      }
      setState({ kind: "ok" });
    } catch (error) {
      setState(plainReason(error));
    }
  }, []);

  return (
    <section className={styles.micCheck} aria-labelledby="mic-check-title">
      <div className={styles.micCheckHead}>
        <span className={styles.micCheckIcon} aria-hidden="true">
          <MicIcon size={20} />
        </span>
        <div>
          <h3 className={styles.micCheckTitle} id="mic-check-title">
            Check your microphone first
          </h3>
          <p className={styles.fieldHelp}>
            When you start the call, the browser asks &ldquo;Allow this site to use your
            microphone?&rdquo;. Choose Allow — the call needs it to hear you, and it is released as
            soon as the call ends. Inside the Android app, Android asks for the Microphone
            permission once instead.
          </p>
        </div>
      </div>

      {state.kind === "ok" ? (
        <p className={styles.micCheckOk} role="status">
          <CheckIcon size={16} /> Your microphone works. You are ready to start.
        </p>
      ) : null}

      {state.kind === "denied" ? (
        <div className={styles.micCheckProblem} role="alert">
          <p className={styles.micCheckProblemTitle}>
            <MicOffIcon size={16} /> The microphone is blocked for this page.
          </p>
          <p className={styles.fieldHelp}>
            In a browser, open this site&rsquo;s settings from the padlock or the menu next to the
            address, set <strong>Microphone</strong> to <strong>Allow</strong>, then try again. In
            the Android app, open <strong>Settings → Apps → Speaking Coach → Permissions</strong>{" "}
            and allow <strong>Microphone</strong>.
          </p>
        </div>
      ) : null}

      {state.kind === "unavailable" ? (
        <div className={styles.micCheckProblem} role="alert">
          <p className={styles.micCheckProblemTitle}>
            <MicOffIcon size={16} /> The microphone could not be checked.
          </p>
          <p className={styles.fieldHelp}>{state.message}</p>
        </div>
      ) : null}

      <div className={styles.micCheckActions}>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={() => void check()}
          disabled={state.kind === "checking"}
          data-testid="mic-check"
        >
          <MicIcon size={18} />
          {state.kind === "checking"
            ? "Checking…"
            : state.kind === "idle"
              ? "Check my microphone"
              : "Try the check again"}
        </button>
      </div>
    </section>
  );
}

export default MicCheck;
