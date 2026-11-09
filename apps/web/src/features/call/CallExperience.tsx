"use client";

/**
 * The call experience — Phase 17.
 *
 * The frozen seam is unchanged: `CallExperience` is a React component, its
 * only prop is `{ catalog }`, and `apps/web/src/app/page.tsx` renders it.
 *
 * Phase 17 removes the extra pages and most of the sentences. One obvious
 * thing per screen:
 *
 * - Landing: the illustration and one Start button.
 * - Pick: scenario cards, one language dropdown, one Call button.
 * - Call: one status word, the avatar, Mute and End.
 * - Summary: three short lines and two buttons.
 * - Progress: date, minutes, language.
 * - Settings: language, recording toggle, account actions.
 */

import { useCallback, useMemo, useReducer, useRef, useState } from "react";

import catalogData from "@gnani/contracts/data/catalog.json";

import { VOICE_WS_URL } from "@/lib/voice";
import { signOut, useSession } from "@/lib/auth";
import { deriveVoiceHttpUrl, setRecordingRetentionConsent, useCallSession } from "@/lib/session-ui";

import styles from "./app.module.css";
import { HomeIcon, PracticeIcon, ProgressIcon, SettingsIcon, SparkIcon } from "./components/Icon";
import {
  buildSessionSettings,
  initialSettings,
  settingsReducer,
  type PracticeCatalog,
} from "./state/settings";
import { CallView } from "./views/CallView";
import { CoachingView } from "./views/CoachingView";
import { HistoryView } from "./views/HistoryView";
import { LandingView } from "./views/LandingView";
import { ScenariosView } from "./views/ScenariosView";
import { SettingsView } from "./views/SettingsView";
import { SummaryView } from "./views/SummaryView";

/** The shared catalog, as the app reads it. */
export type CallCatalog = typeof catalogData;

export interface CallExperienceProps {
  catalog: CallCatalog;
}

type View = "landing" | "scenarios" | "settings" | "call" | "coaching" | "summary" | "history";

const NAV_ITEMS: { id: View; label: string }[] = [
  { id: "landing", label: "Home" },
  { id: "scenarios", label: "Practice" },
  { id: "history", label: "Progress" },
];

export function CallExperience({ catalog }: CallExperienceProps) {
  const practiceCatalog = catalog as unknown as PracticeCatalog;
  const [view, setView] = useState<View>("landing");
  const [accountNotice, setAccountNotice] = useState<string | null>(null);
  const [settings, dispatchSettings] = useReducer(
    settingsReducer,
    undefined,
    () => initialSettings(practiceCatalog),
  );
  const startingRef = useRef(false);

  const built = useMemo(
    () => buildSessionSettings(settings, practiceCatalog),
    [settings, practiceCatalog],
  );
  const httpBaseUrl = useMemo(() => deriveVoiceHttpUrl(VOICE_WS_URL), []);
  const sessionState = useSession();
  const signedIn = sessionState.status === "authenticated";

  const handleRecording = useCallback((enabled: boolean) => {
    dispatchSettings({
      type: "recording",
      enabled,
      grantedAt: enabled ? new Date().toISOString() : null,
    });
    void setRecordingRetentionConsent(enabled);
  }, []);

  const session = useCallSession({
    settings: built.settings,
    wsUrl: VOICE_WS_URL,
    onEnded: () => setView("summary"),
    onRoundFeedback: () => setView("coaching"),
  });

  const navigate = useCallback((next: View) => {
    setView(next);
    if (next !== "landing") {
      setAccountNotice(null);
    }
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0 });
    }
  }, []);

  const handleStart = useCallback(async () => {
    if (startingRef.current) {
      return;
    }
    startingRef.current = true;
    try {
      session.reset();
      setView("call");
      await session.start();
    } finally {
      startingRef.current = false;
    }
  }, [session]);

  const handleEnd = useCallback(() => {
    session.end();
    setView("summary");
  }, [session]);

  const handleSignOut = useCallback(() => {
    void (async () => {
      try {
        await signOut();
      } finally {
        session.reset();
        setView("landing");
      }
    })();
  }, [session]);

  const handleAccountDeleted = useCallback(() => {
    session.reset();
    setAccountNotice("Account deleted.");
    navigate("landing");
  }, [navigate, session]);

  const handleRetry = useCallback(async () => {
    if (startingRef.current) {
      return;
    }
    startingRef.current = true;
    try {
      session.reset();
      setView("call");
      await session.start();
    } finally {
      startingRef.current = false;
    }
  }, [session]);

  const languageNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const language of practiceCatalog.languages) {
      names[language.id] = language.displayName;
    }
    return names;
  }, [practiceCatalog]);

  const inCall = view === "call" || view === "coaching";

  if (inCall) {
    if (view === "coaching" && session.state.feedback) {
      return (
        <CoachingView
          feedback={session.state.feedback}
          turnId={session.state.feedbackTurnId}
          onRetry={(turnId) => {
            session.retry(turnId);
            setView("call");
          }}
          onKeepTalking={() => {
            session.coachingChoice("keep_talking");
            setView("call");
          }}
          onSkip={() => {
            session.coachingChoice("skip_feedback");
            setView("call");
          }}
        />
      );
    }
    return (
      <CallView
        state={session.state}
        onEnd={handleEnd}
        onMute={session.setMuted}
        onTranscriptVisible={session.setTranscriptVisible}
        onRetry={() => void handleRetry()}
      />
    );
  }

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <button type="button" className={styles.brand} onClick={() => navigate("landing")}>
            <span className={styles.brandMark} aria-hidden="true">
              <SparkIcon size={22} />
            </span>
            Speaking Coach
          </button>
          <nav className={styles.nav} aria-label="Main">
            {NAV_ITEMS.map((item) => (
              <button
                type="button"
                key={item.id}
                className={`${styles.navLink} ${
                  view === item.id ||
                  (item.id === "scenarios" && view === "settings")
                    ? styles.navLinkActive
                    : ""
                }`}
                aria-current={view === item.id ? "page" : undefined}
                onClick={() => navigate(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.iconButton}
              aria-label="Settings"
              title="Settings"
              onClick={() => navigate("settings")}
            >
              <SettingsIcon size={20} />
            </button>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        {view === "landing" ? (
          <LandingView
            onStart={() => navigate("scenarios")}
            signedIn={signedIn}
            notice={accountNotice}
          />
        ) : null}

        {view === "scenarios" ? (
          <ScenariosView
            catalog={practiceCatalog}
            scenarioId={settings.scenarioId}
            presetId={settings.scenarioPresetId}
            customTopic={settings.customTopic}
            practiceLanguageId={settings.practiceLanguageId}
            onScenario={(scenarioId) => dispatchSettings({ type: "scenario", scenarioId })}
            onPreset={(presetId) => dispatchSettings({ type: "preset", presetId })}
            onCustomTopic={(text) => dispatchSettings({ type: "custom_topic", text })}
            onPracticeLanguage={(languageId) =>
              dispatchSettings({ type: "practice_language", languageId })
            }
            onStart={() => void handleStart()}
          />
        ) : null}

        {view === "settings" ? (
          <SettingsView
            catalog={practiceCatalog}
            practiceLanguageId={settings.practiceLanguageId}
            coachingLanguageId={settings.coachingLanguageId}
            levelId={settings.levelId}
            recordingRetention={settings.recordingRetention}
            signedIn={signedIn}
            problems={built.problems}
            onPracticeLanguage={(languageId) =>
              dispatchSettings({ type: "practice_language", languageId })
            }
            onCoachingLanguage={(languageId) =>
              dispatchSettings({ type: "coaching_language", languageId })
            }
            onLevel={(levelId) => dispatchSettings({ type: "level", levelId })}
            onRecording={handleRecording}
            onBack={() => navigate("scenarios")}
            onSignOut={handleSignOut}
            onDeleted={handleAccountDeleted}
          />
        ) : null}

        {view === "summary" ? (
          <SummaryView
            state={session.state}
            onDone={() => navigate("landing")}
            onRetry={() => void handleRetry()}
          />
        ) : null}

        {view === "history" ? (
          <HistoryView
            httpBaseUrl={httpBaseUrl}
            languageNames={languageNames}
            onStart={() => navigate("scenarios")}
          />
        ) : null}
      </main>

      <nav className={styles.bottomNav} aria-label="Main" data-testid="bottom-tab-bar">
        <button
          type="button"
          className={`${styles.bottomNavItem} ${view === "landing" ? styles.bottomNavItemActive : ""}`}
          onClick={() => navigate("landing")}
        >
          <HomeIcon size={20} />
          Home
        </button>
        <button
          type="button"
          className={`${styles.bottomNavItem} ${
            view === "scenarios" || view === "settings" ? styles.bottomNavItemActive : ""
          }`}
          onClick={() => navigate("scenarios")}
        >
          <PracticeIcon size={20} />
          Practice
        </button>
        <button
          type="button"
          className={`${styles.bottomNavItem} ${view === "history" ? styles.bottomNavItemActive : ""}`}
          onClick={() => navigate("history")}
        >
          <ProgressIcon size={20} />
          Progress
        </button>
      </nav>
    </div>
  );
}

export default CallExperience;
