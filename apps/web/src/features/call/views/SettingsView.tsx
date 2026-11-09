"use client";

/**
 * The settings screen — Phase 17.
 *
 * Language, one recording toggle, and the account actions. Coaching
 * language and level are rare, so they sit behind a single More
 * disclosure. Recording is off unless the learner turns it on.
 */

import styles from "../app.module.css";
import { AccountSection } from "../components/AccountSection";
import { ArrowLeftIcon } from "../components/Icon";
import type { PracticeCatalog } from "../state/settings";

export interface SettingsViewProps {
  catalog: PracticeCatalog;
  practiceLanguageId: string;
  coachingLanguageId: string;
  levelId: string;
  recordingRetention: boolean;
  signedIn: boolean;
  problems: string[];
  onPracticeLanguage: (languageId: string) => void;
  onCoachingLanguage: (languageId: string) => void;
  onLevel: (levelId: string) => void;
  onRecording: (enabled: boolean) => void;
  onBack: () => void;
  /** The same sign-out handler the live call screen uses. */
  onSignOut: () => void;
  /** Called after the account and its data were deleted. */
  onDeleted: () => void;
}

export function SettingsView({
  catalog,
  practiceLanguageId,
  coachingLanguageId,
  levelId,
  recordingRetention,
  signedIn,
  problems,
  onPracticeLanguage,
  onCoachingLanguage,
  onLevel,
  onRecording,
  onBack,
  onSignOut,
  onDeleted,
}: SettingsViewProps) {
  const language = catalog.languages.find((entry) => entry.id === practiceLanguageId);

  return (
    <div className={`${styles.container} ${styles.containerNarrow}`} data-testid="settings-root">
      <button type="button" className={styles.ghostButton} onClick={onBack} aria-label="Back">
        <ArrowLeftIcon size={18} />
      </button>

      <h1 className={styles.screenTitle}>Practice settings</h1>

      <div className={styles.languageRow}>
        <select
          className={styles.select}
          aria-label="Speaking language"
          value={practiceLanguageId}
          onChange={(event) => onPracticeLanguage(event.target.value)}
        >
          {catalog.languages.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.displayName}
            </option>
          ))}
        </select>
        {language && !language.capabilities.conversationTested ? (
          <span className={styles.capabilityBadge}>Not yet checked</span>
        ) : null}
      </div>

      <details className={styles.moreBlock}>
        <summary className={styles.moreSummary}>More</summary>
        <div className={styles.settingsStack}>
          <select
            className={styles.select}
            aria-label="Coaching language"
            value={coachingLanguageId}
            onChange={(event) => onCoachingLanguage(event.target.value)}
          >
            {catalog.languages.map((entry) => (
              <option key={entry.id} value={entry.id} lang={entry.sttCode}>
                {entry.nativeName}
              </option>
            ))}
          </select>
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
        </div>
      </details>

      <div className={styles.toggleRow}>
        <input
          type="checkbox"
          id="recording-retention"
          checked={recordingRetention}
          onChange={(event) => onRecording(event.target.checked)}
          aria-label="Save the recording so I can replay it later"
        />
        <div>
          <label className={styles.fieldLabel} htmlFor="recording-retention">
            Save my recordings
          </label>
          <p className={styles.fieldHelp}>Off unless you turn it on.</p>
        </div>
      </div>

      {problems.length > 0 ? (
        <p className={styles.callErrorText} role="alert">
          {problems[0]}
        </p>
      ) : null}

      <AccountSection signedIn={signedIn} onSignOut={onSignOut} onDeleted={onDeleted} />
    </div>
  );
}

export default SettingsView;
