"use client";

/**
 * The progress and history view — Phase 04.
 *
 * Mobile screen 7 of the reference flow.
 *
 * The rules:
 *
 * - the list is **real**: it comes from `GET /api/history` and there is no
 *   sample data anywhere;
 * - a **guest** sees &ldquo;Sign in to keep progress&rdquo; — that is a
 *   state, not an error;
 * - a **replay button appears only when the recording exists and the fetch
 *   works**. If the recording is missing or belongs to somebody else, the
 *   route answers `404` and no replay control is shown at all;
 * - deleting a recording asks first.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import styles from "../app.module.css";
import { ArrowLeftIcon, ClockIcon, ProgressIcon, TrashIcon, UsersIcon } from "../components/Icon";
import { SignInEntry } from "../components/SignInEntry";
import {
  deleteRecording,
  fetchHistory,
  fetchRecording,
  getCallAccessToken,
  type HistorySession,
} from "@/lib/session-ui";

export interface HistoryViewProps {
  httpBaseUrl: string;
  languageNames: Record<string, string>;
  scenarioNames: Record<string, string>;
  onBack: () => void;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "guest" }
  | { kind: "error"; message: string; advice: string }
  | { kind: "list"; sessions: HistorySession[] };

type RecordingState =
  | { kind: "available"; url: string }
  | { kind: "unavailable" }
  | { kind: "error" };

interface HistoryData {
  state: LoadState;
  recordings: Record<string, RecordingState>;
  /** The object URLs to release when the view goes away. */
  urls: string[];
}

/**
 * Load the history and check every recording.
 *
 * This is a plain function outside the component, so the effect that calls
 * it never sets state synchronously.
 */
async function loadHistoryData(httpBaseUrl: string): Promise<HistoryData> {
  const token = await getCallAccessToken();
  const result = await fetchHistory(httpBaseUrl, token);
  if (result.kind !== "list") {
    return { state: result, recordings: {}, urls: [] };
  }
  const entries = await Promise.all(
    result.sessions.map(async (session) => {
      if (!session.recordingId) {
        return null;
      }
      const recording = await fetchRecording(httpBaseUrl, token, session.recordingId);
      return [session.sessionId, recording] as const;
    }),
  );
  const recordings: Record<string, RecordingState> = {};
  const urls: string[] = [];
  for (const entry of entries) {
    if (!entry) {
      continue;
    }
    const [sessionId, recording] = entry;
    if (recording.kind === "available") {
      recordings[sessionId] = { kind: "available", url: recording.url };
      urls.push(recording.url);
    } else if (recording.kind === "unavailable") {
      recordings[sessionId] = { kind: "unavailable" };
    } else {
      recordings[sessionId] = { kind: "error" };
    }
  }
  return { state: { kind: "list", sessions: result.sessions }, recordings, urls };
}

export function HistoryView({ httpBaseUrl, languageNames, scenarioNames, onBack }: HistoryViewProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [recordings, setRecordings] = useState<Record<string, RecordingState>>({});
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The loaded object URLs, so they can be released when the view goes away.
  const urlsRef = useRef<string[]>([]);

  const apply = useCallback((data: HistoryData) => {
    // Release the previous object URLs before replacing them.
    for (const url of urlsRef.current) {
      URL.revokeObjectURL(url);
    }
    urlsRef.current = data.urls;
    setState(data.state);
    setRecordings(data.recordings);
  }, []);

  const refresh = useCallback(() => {
    void loadHistoryData(httpBaseUrl).then(apply);
  }, [apply, httpBaseUrl]);

  useEffect(() => {
    let cancelled = false;
    void loadHistoryData(httpBaseUrl).then((data) => {
      if (cancelled) {
        return;
      }
      apply(data);
    });
    return () => {
      cancelled = true;
      // Release the object URLs of any recording that was loaded.
      for (const url of urlsRef.current) {
        URL.revokeObjectURL(url);
      }
      urlsRef.current = [];
    };
  }, [apply, httpBaseUrl]);

  async function handleDelete(session: HistorySession) {
    if (!session.recordingId) {
      return;
    }
    setBusy(true);
    const token = await getCallAccessToken();
    const result = await deleteRecording(httpBaseUrl, token, session.recordingId);
    setBusy(false);
    setConfirming(null);
    if (result.kind === "deleted" || result.kind === "missing") {
      setRecordings((current) => {
        const next = { ...current };
        const existing = next[session.sessionId];
        if (existing?.kind === "available") {
          URL.revokeObjectURL(existing.url);
        }
        next[session.sessionId] = { kind: "unavailable" };
        return next;
      });
      refresh();
      return;
    }
    setState({
      kind: "error",
      message: result.message,
      advice: "Try again in a moment.",
    });
  }

  return (
    <div className={`${styles.container} ${styles.containerNarrow}`}>
      <button type="button" className={styles.ghostButton} onClick={onBack}>
        <ArrowLeftIcon size={18} />
        Back
      </button>

      <section aria-labelledby="history-title">
        <h2 className={styles.sectionTitle} id="history-title">
          Your progress
        </h2>
        <p className={styles.sectionLede}>
          Your finished practice sessions, newest first. Nothing is here that you did not ask us to
          keep.
        </p>

        {state.kind === "loading" ? (
          <div className={styles.emptyState}>
            <p className={styles.emptyStateText}>Loading your sessions…</p>
          </div>
        ) : null}

        {state.kind === "guest" ? (
          <div className={styles.guestState}>
            <div className={styles.stateIcon}>
              <UsersIcon size={26} />
            </div>
            <h3 className={styles.guestStateTitle}>Sign in to keep progress</h3>
            <p className={styles.guestStateText}>
              You can practise as a guest — the call works exactly the same. A guest has no saved
              history and no retained audio, so nothing is kept until you sign in.
            </p>
            <SignInEntry />
          </div>
        ) : null}

        {state.kind === "error" ? (
          <div className={styles.errorState} role="alert">
            <div className={styles.stateIcon}>
              <ProgressIcon size={26} />
            </div>
            <h3 className={styles.errorStateTitle}>We could not load your progress</h3>
            <p className={styles.errorStateText}>{state.message}</p>
            <p className={styles.errorStateText}>{state.advice}</p>
            <button type="button" className={styles.secondaryButton} onClick={refresh}>
              Try again
            </button>
          </div>
        ) : null}

        {state.kind === "list" && state.sessions.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.stateIcon}>
              <ProgressIcon size={26} />
            </div>
            <h3 className={styles.emptyStateTitle}>No sessions yet</h3>
            <p className={styles.emptyStateText}>
              When you finish a practice call it will appear here, with what was measured in it.
            </p>
          </div>
        ) : null}

        {state.kind === "list" && state.sessions.length > 0 ? (
          <ul className={styles.historyList}>
            {state.sessions.map((session) => {
              const recording = recordings[session.sessionId];
              return (
                <li className={styles.historyItem} key={session.sessionId}>
                  <div className={styles.historyTop}>
                    <h3 className={styles.historyTitle}>
                      {scenarioNames[session.scenarioId] ?? session.scenarioId}
                    </h3>
                    <span className={styles.pill}>
                      <ClockIcon size={13} />
                      {new Date(session.recordedAt).toLocaleString("en-GB", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </span>
                  </div>
                  <p className={styles.historyMeta}>
                    {languageNames[session.practiceLanguageId] ?? session.practiceLanguageId} ·{" "}
                    {session.turnCount} learner turns ·{" "}
                    {Math.round(session.speakingTimeMs / 1000)} s of speech
                  </p>
                  <div className={styles.historyActions}>
                    {recording?.kind === "available" ? (
                      <audio
                        className={styles.audioPlayer}
                        controls
                        preload="metadata"
                        src={recording.url}
                        aria-label="Recording of this session"
                      />
                    ) : null}
                    {session.recordingId ? (
                      confirming === session.sessionId ? (
                        <span className={styles.confirmRow}>
                          Delete this recording? It cannot be undone.
                          <button
                            type="button"
                            className={styles.dangerButton}
                            disabled={busy}
                            onClick={() => void handleDelete(session)}
                          >
                            Yes, delete it
                          </button>
                          <button
                            type="button"
                            className={styles.smallButton}
                            onClick={() => setConfirming(null)}
                          >
                            Keep it
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className={styles.smallButton}
                          onClick={() => setConfirming(session.sessionId)}
                        >
                          <TrashIcon size={15} />
                          Delete the recording
                        </button>
                      )
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </section>
    </div>
  );
}

export default HistoryView;
