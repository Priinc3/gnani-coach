"use client";

/**
 * The progress view — Phase 17.
 *
 * A list of date, minutes and language. Replay appears only when the
 * recording can actually be fetched; deleting one asks first. A guest sees
 * one sign-in line, not an error.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import styles from "../app.module.css";
import { TrashIcon } from "../components/Icon";
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
  onStart: () => void;
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
  urls: string[];
}

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

function minutesOf(session: HistorySession): number {
  return Math.max(1, Math.round(session.speakingTimeMs / 60000));
}

export function HistoryView({ httpBaseUrl, languageNames, onStart }: HistoryViewProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [recordings, setRecordings] = useState<Record<string, RecordingState>>({});
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const urlsRef = useRef<string[]>([]);

  const apply = useCallback((data: HistoryData) => {
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
    <div className={`${styles.container} ${styles.containerNarrow}`} data-testid="progress-root">
      <h1 className={styles.screenTitle}>Your progress</h1>

      {state.kind === "loading" ? <p className={styles.emptyLine}>Loading…</p> : null}

      {state.kind === "guest" ? (
        <div className={styles.emptyStateSimple}>
          <p className={styles.emptyLine}>Sign in to keep progress</p>
          <SignInEntry />
        </div>
      ) : null}

      {state.kind === "error" ? (
        <div className={styles.emptyStateSimple} role="alert">
          <p className={styles.emptyLine}>We could not load your progress</p>
          <button type="button" className={styles.secondaryButton} onClick={refresh}>
            Try again
          </button>
        </div>
      ) : null}

      {state.kind === "list" && state.sessions.length === 0 ? (
        <div className={styles.emptyStateSimple}>
          <p className={styles.emptyLine}>No sessions yet.</p>
          <button type="button" className={styles.primaryButton} onClick={onStart}>
            Start
          </button>
        </div>
      ) : null}

      {state.kind === "list" && state.sessions.length > 0 ? (
        <ul className={styles.historyList}>
          {state.sessions.map((session) => {
            const recording = recordings[session.sessionId];
            return (
              <li className={styles.historyItemSimple} key={session.sessionId}>
                <span className={styles.historyDate}>
                  {new Date(session.recordedAt).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
                <span className={styles.historyMeta}>
                  {minutesOf(session)} min
                </span>
                <span className={styles.historyMeta}>
                  {languageNames[session.practiceLanguageId] ?? session.practiceLanguageId}
                </span>
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
                        aria-label="Delete the recording"
                        onClick={() => setConfirming(session.sessionId)}
                      >
                        <TrashIcon size={15} />
                      </button>
                    )
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

export default HistoryView;
