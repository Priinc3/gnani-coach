"use client";

/**
 * The call experience — **Phase 04 owns this tree**.
 *
 * The frozen seam is unchanged:
 *
 * - `CallExperience` is a React component;
 * - its only prop is `{ catalog }`, the shared catalog from
 *   `@gnani/contracts/data/catalog.json`;
 * - `apps/web/src/app/page.tsx` renders it and nothing else.
 *
 * What changed in Phase 04: the stub's honest starter notice is replaced by
 * the real browser side of the product — onboarding, the scenario picker,
 * the language and settings screen, the live call, the coaching break, the
 * session summary and the progress list — all built against the frozen
 * seams in `docs/contracts/`.
 *
 * The visual target is the Speakify reference (`prompts/phase-04-call-ui/
 * UI-REFERENCE.md` and `UI.png`): a warm near-white canvas, softly raised
 * white panels, dark pill-shaped primary buttons, mint highlights and bold
 * sans-serif headings. Every colour, radius and type step comes from the
 * frozen tokens in `apps/web/src/app/globals.css`.
 */

import { useCallback, useMemo, useReducer, useRef, useState } from "react";

import catalogData from "@gnani/contracts/data/catalog.json";

import { VOICE_WS_URL } from "@/lib/voice";
import { signOut, useSession } from "@/lib/auth";
import { deriveVoiceHttpUrl, setRecordingRetentionConsent, useCallSession } from "@/lib/session-ui";

import styles from "./app.module.css";
import { HomeIcon, PracticeIcon, ProgressIcon, SparkIcon } from "./components/Icon";
import {
  buildSessionSettings,
  describePlan,
  initialSettings,
  settingsReducer,
  type PracticeCatalog,
} from "./state/settings";
import { CallView } from "./views/CallView";
import { CoachingView } from "./views/CoachingView";
import { FeaturesView } from "./views/FeaturesView";
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

type View =
  | "landing"
  | "features"
  | "scenarios"
  | "settings"
  | "call"
  | "coaching"
  | "summary"
  | "history";

const NAV_ITEMS: { id: View; label: string }[] = [
  { id: "features", label: "Features" },
  { id: "scenarios", label: "Scenarios" },
  { id: "history", label: "Progress" },
];

export function CallExperience({ catalog }: CallExperienceProps) {
  const practiceCatalog = catalog as unknown as PracticeCatalog;
  const [view, setView] = useState<View>("landing");
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
  const planSummary = useMemo(
    () => describePlan(settings, practiceCatalog),
    [settings, practiceCatalog],
  );
  const httpBaseUrl = useMemo(() => deriveVoiceHttpUrl(VOICE_WS_URL), []);
  const sessionState = useSession();
  const signedIn = sessionState.status === "authenticated";

  const handleRecording = useCallback(
    (enabled: boolean) => {
      dispatchSettings({
        type: "recording",
        enabled,
        grantedAt: enabled ? new Date().toISOString() : null,
      });
      // The decision is also recorded on the service. The flag travels in the
      // `start` event as well, and the service re-checks it when it writes,
      // so a failure here never silently keeps an audio file.
      void setRecordingRetentionConsent(enabled);
    },
    [],
  );

  const session = useCallSession({
    settings: built.settings,
    wsUrl: VOICE_WS_URL,
    onEnded: () => setView("summary"),
    onRoundFeedback: () => setView("coaching"),
  });

  const navigate = useCallback((next: View) => {
    setView(next);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0 });
    }
  }, []);

  // The "Languages" navigation entry scrolls to the language list on the
  // landing view, so the destination is never a dead link.
  const scrollToLanguages = useCallback(() => {
    setView("landing");
    if (typeof document === "undefined") {
      return;
    }
    const node = document.getElementById("languages");
    if (node) {
      node.scrollIntoView({ block: "start" });
    }
  }, []);

  const handleStart = useCallback(async () => {
    if (startingRef.current) {
      // A second click on Start must never open a second connection.
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

  /**
   * Sign out from a live call.
   *
   * `signOut()` ends the session and runs the sign-out handlers, one of
   * which tears down the call socket and the microphone. The reset is
   * belt-and-braces: even a failed sign-out must not leave a live socket
   * behind. The app returns to the landing view as a guest.
   */
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

  /**
   * "Try again" — a fresh connection.
   *
   * The old socket is closed and the microphone is released before the new
   * call starts, so a retry never leaves two connections or two open
   * microphones behind.
   */
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

  const scenarioNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const scenario of practiceCatalog.scenarios) {
      names[scenario.id] = scenario.displayName;
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
        onSpeaker={session.setSpeaker}
        onTranscriptVisible={session.setTranscriptVisible}
        onCoachNow={() => session.coachingChoice("coach_now")}
        onRetry={() => void handleRetry()}
        signedIn={signedIn}
        onSignOut={handleSignOut}
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
                key={item.label}
                className={`${styles.navLink} ${view === item.id ? styles.navLinkActive : ""}`}
                aria-current={view === item.id ? "page" : undefined}
                onClick={() => navigate(item.id)}
              >
                {item.label}
              </button>
            ))}
            <button type="button" className={styles.navLink} onClick={scrollToLanguages}>
              Languages
            </button>
          </nav>
          <div className={styles.headerActions}>
            <button
              type="button"
              className={`${styles.primaryButton} ${styles.headerCta}`}
              onClick={() => navigate("scenarios")}
            >
              Get started
            </button>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        {view === "landing" ? (
          <LandingView
            catalog={practiceCatalog}
            onStart={() => navigate("scenarios")}
            onSeeFeatures={() => navigate("features")}
          />
        ) : null}

        {view === "features" ? (
          <FeaturesView catalog={practiceCatalog} onBack={() => navigate("landing")} />
        ) : null}

        {view === "scenarios" ? (
          <ScenariosView
            catalog={practiceCatalog}
            scenarioId={settings.scenarioId}
            presetId={settings.scenarioPresetId}
            customTopic={settings.customTopic}
            onScenario={(scenarioId) => dispatchSettings({ type: "scenario", scenarioId })}
            onPreset={(presetId) => dispatchSettings({ type: "preset", presetId })}
            onCustomTopic={(text) => dispatchSettings({ type: "custom_topic", text })}
            onContinue={() => navigate("settings")}
            onBack={() => navigate("landing")}
          />
        ) : null}

        {view === "settings" ? (
          <SettingsView
            catalog={practiceCatalog}
            practiceLanguageId={settings.practiceLanguageId}
            coachingLanguageId={settings.coachingLanguageId}
            levelId={settings.levelId}
            recordingRetention={settings.recordingRetention}
            subtitles={settings.subtitles}
            signedIn={signedIn}
            customTopic={settings.customTopic}
            scenarioId={settings.scenarioId}
            presetId={settings.scenarioPresetId}
            planSummary={planSummary}
            problems={built.problems}
            onPracticeLanguage={(languageId) =>
              dispatchSettings({ type: "practice_language", languageId })
            }
            onCoachingLanguage={(languageId) =>
              dispatchSettings({ type: "coaching_language", languageId })
            }
            onLevel={(levelId) => dispatchSettings({ type: "level", levelId })}
            onRecording={handleRecording}
            onSubtitles={(enabled) => dispatchSettings({ type: "subtitles", enabled })}
            onCustomTopic={(text) => dispatchSettings({ type: "custom_topic", text })}
            onStart={() => void handleStart()}
            onBack={() => navigate("scenarios")}
          />
        ) : null}

        {view === "summary" ? (
          <SummaryView
            state={session.state}
            onDone={() => navigate("landing")}
            onOpenHistory={() => navigate("history")}
          />
        ) : null}

        {view === "history" ? (
          <HistoryView
            httpBaseUrl={httpBaseUrl}
            languageNames={languageNames}
            scenarioNames={scenarioNames}
            onBack={() => navigate("landing")}
          />
        ) : null}
      </main>

      <nav className={styles.bottomNav} aria-label="Main" data-testid="bottom-tab-bar">
        <button
          type="button"
          className={`${styles.bottomNavItem} ${
            view === "landing" || view === "features" ? styles.bottomNavItemActive : ""
          }`}
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
          className={`${styles.bottomNavItem} ${
            view === "history" ? styles.bottomNavItemActive : ""
          }`}
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
