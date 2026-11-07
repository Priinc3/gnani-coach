"use client";

/**
 * The language and settings screen — Phase 04.
 *
 * Mobile screen 3 of the reference flow, and the desktop equivalent.
 *
 * The rules this screen exists to keep:
 *
 * - the **speaking language** and the **coaching language** are separate
 *   choices, and the coaching language follows the speaking language until
 *   the learner picks one themselves;
 * - every language carries an honest capability badge;
 * - the custom topic is transient: it is used for this call only;
 * - **recording retention is off by default**, and the difference between
 *   live processing and keeping the audio is spelled out in plain words;
 * - the subtitles are transient too.
 */

import styles from "../app.module.css";
import { ArrowLeftIcon, CheckIcon, MicIcon } from "../components/Icon";
import { MicCheck } from "../components/MicCheck";
import type { PracticeCatalog } from "../state/settings";

export interface SettingsViewProps {
  catalog: PracticeCatalog;
  practiceLanguageId: string;
  coachingLanguageId: string;
  levelId: string;
  recordingRetention: boolean;
  subtitles: boolean;
  signedIn: boolean;
  customTopic: string;
  scenarioId: string;
  presetId: string | null;
  planSummary: string;
  problems: string[];
  onPracticeLanguage: (languageId: string) => void;
  onCoachingLanguage: (languageId: string) => void;
  onLevel: (levelId: string) => void;
  onRecording: (enabled: boolean) => void;
  onSubtitles: (enabled: boolean) => void;
  onCustomTopic: (text: string) => void;
  onStart: () => void;
  onBack: () => void;
}

export function SettingsView({
  catalog,
  practiceLanguageId,
  coachingLanguageId,
  levelId,
  recordingRetention,
  subtitles,
  signedIn,
  customTopic,
  scenarioId,
  presetId,
  planSummary,
  problems,
  onPracticeLanguage,
  onCoachingLanguage,
  onLevel,
  onRecording,
  onSubtitles,
  onCustomTopic,
  onStart,
  onBack,
}: SettingsViewProps) {
  const scenario = catalog.scenarios.find((entry) => entry.id === scenarioId);
  const preset = scenario?.presets?.find((entry) => entry.id === presetId);
  const practiceLanguage = catalog.languages.find((entry) => entry.id === practiceLanguageId);
  const needsCustomTopic = scenario?.customTopic?.required === true;
  const maxLength = scenario?.customTopic?.maxLength ?? 200;

  return (
    <div className={`${styles.container} ${styles.containerNarrow}`}>
      <button type="button" className={styles.ghostButton} onClick={onBack}>
        <ArrowLeftIcon size={18} />
        Back
      </button>

      <section aria-labelledby="settings-title">
        <h2 className={styles.sectionTitle} id="settings-title">
          Practice settings
        </h2>
        <p className={styles.sectionLede}>
          {scenario?.displayName ?? "Your scenario"}
          {preset ? ` · ${preset.displayName}` : ""} — the coach will stay in this situation and
          wait for you to talk.
        </p>

        <div className={styles.settingsStack}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="practice-language">
              Speaking language
            </label>
            <select
              id="practice-language"
              className={styles.select}
              value={practiceLanguageId}
              onChange={(event) => onPracticeLanguage(event.target.value)}
              aria-describedby="practice-language-help"
            >
              {catalog.languages.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.displayName} — {entry.nativeName}
                </option>
              ))}
            </select>
            <p className={styles.fieldHelp} id="practice-language-help">
              The language you speak in. The coach listens in this language.
            </p>
            <p>
              <span className={styles.capabilityBadge}>
                {practiceLanguage?.capabilities.conversationTested
                  ? "Tested in this app"
                  : "Not yet verified"}
              </span>
            </p>
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="coaching-language">
              Coaching language
            </label>
            <select
              id="coaching-language"
              className={styles.select}
              value={coachingLanguageId}
              onChange={(event) => onCoachingLanguage(event.target.value)}
              aria-describedby="coaching-language-help"
            >
              {catalog.languages.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.displayName} — {entry.nativeName}
                </option>
              ))}
            </select>
            <p className={styles.fieldHelp} id="coaching-language-help">
              The language the coach explains in. It follows your speaking language until you
              choose otherwise. No cross-language coaching pair has been tested yet.
            </p>
          </div>

          <fieldset className={styles.field}>
            <legend className={styles.fieldLabel}>How comfortable are you right now?</legend>
            <div className={styles.levelList}>
              {catalog.levels.map((level) => (
                <label className={styles.levelOption} key={level.id}>
                  <input
                    type="radio"
                    name="level"
                    value={level.id}
                    checked={levelId === level.id}
                    onChange={() => onLevel(level.id)}
                  />
                  <span>{level.displayName}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {needsCustomTopic ? (
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="custom-topic-settings">
                Your topic (used for this call only)
              </label>
              <input
                type="text"
                id="custom-topic-settings"
                className={styles.textInput}
                maxLength={maxLength}
                value={customTopic}
                onChange={(event) => onCustomTopic(event.target.value)}
                aria-describedby="custom-topic-settings-help"
              />
              <p className={styles.fieldHelp} id="custom-topic-settings-help">
                Transient: it is never saved, never stored with your history and never written to
                your metrics.
              </p>
            </div>
          ) : null}

          <div className={styles.toggleRow}>
            <input
              type="checkbox"
              id="recording-retention"
              checked={recordingRetention}
              onChange={(event) => onRecording(event.target.checked)}
              aria-describedby="recording-retention-help"
            />
            <div>
              <label className={styles.fieldLabel} htmlFor="recording-retention">
                Save the recording so I can replay it later
              </label>
              <p className={styles.fieldHelp} id="recording-retention-help">
                Off by default, and it is worth knowing the difference. While you are on the call,
                your voice is processed live so the coach can answer — that always happens. Turning
                this on additionally <strong>keeps the call audio</strong> so you can replay it in
                your history. Either way, transcripts and coaching notes stay transient: they are
                cleared when the call ends and are never saved.
                {!signedIn
                  ? " You are not signed in, so nothing is kept for now — a guest has no saved audio."
                  : ""}
              </p>
            </div>
          </div>

          <div className={styles.toggleRow}>
            <input
              type="checkbox"
              id="subtitles"
              checked={subtitles}
              onChange={(event) => onSubtitles(event.target.checked)}
              aria-describedby="subtitles-help"
            />
            <div>
              <label className={styles.fieldLabel} htmlFor="subtitles">
                Show the transcript while we talk
              </label>
              <p className={styles.fieldHelp} id="subtitles-help">
                Transient: the words appear while the call is running and are cleared when it ends.
                They are never stored, and this is not permission to keep them.
              </p>
            </div>
          </div>

          <MicCheck />

          <p className={styles.planSummary} role="status">
            Plan: {planSummary}
          </p>

          {problems.length > 0 ? (
            <div className={styles.callError} role="alert">
              <p className={styles.callErrorTitle}>Check this before you start</p>
              <ul className={styles.stack}>
                {problems.map((problem) => (
                  <li className={styles.callErrorText} key={problem}>
                    {problem}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className={styles.stickyAction}>
            <div className={styles.row}>
              <button
                type="button"
                className={`${styles.primaryButton} ${styles.stickyActionButton}`}
                onClick={onStart}
                disabled={problems.length > 0}
              >
                <MicIcon size={18} />
                Start live practice call
              </button>
            </div>
            <p className={styles.fieldHelp}>
              <CheckIcon size={14} /> Your microphone is only asked for when you press start, and it
              is released as soon as the call ends.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

export default SettingsView;
