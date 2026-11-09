"use client";

/**
 * The pick screen — Phase 17.
 *
 * Scenario cards with an icon and a short name, one language dropdown, and
 * one Call button. Presets are rare, so they sit behind a single More
 * disclosure. The two honest lines stay: where the voice goes, and that
 * recording is off unless the learner turns it on.
 */

import styles from "../app.module.css";
import {
  GlobeIcon,
  MicIcon,
  PlusIcon,
  SparkIcon,
  UsersIcon,
} from "../components/Icon";
import type { PracticeCatalog } from "../state/settings";

export interface ScenariosViewProps {
  catalog: PracticeCatalog;
  scenarioId: string;
  presetId: string | null;
  customTopic: string;
  practiceLanguageId: string;
  onScenario: (scenarioId: string) => void;
  onPreset: (presetId: string | null) => void;
  onCustomTopic: (text: string) => void;
  onPracticeLanguage: (languageId: string) => void;
  onStart: () => void;
}

function ScenarioIcon({ id }: { id: string }) {
  switch (id) {
    case "workplace":
      return <UsersIcon size={22} />;
    case "travel-social":
      return <GlobeIcon size={22} />;
    case "everyday":
      return <SparkIcon size={22} />;
    case "custom":
      return <PlusIcon size={22} />;
    default:
      return <MicIcon size={22} />;
  }
}

export function ScenariosView({
  catalog,
  scenarioId,
  presetId,
  customTopic,
  practiceLanguageId,
  onScenario,
  onPreset,
  onCustomTopic,
  onPracticeLanguage,
  onStart,
}: ScenariosViewProps) {
  const scenario = catalog.scenarios.find((entry) => entry.id === scenarioId);
  const presets = scenario?.presets ?? [];
  const needsCustomTopic = scenario?.customTopic?.required === true;
  const maxLength = scenario?.customTopic?.maxLength ?? 200;
  const language = catalog.languages.find((entry) => entry.id === practiceLanguageId);

  return (
    <div className={styles.container} data-testid="pick-root">
      <h1 className={styles.screenTitle}>Choose a scenario</h1>

      <div className={styles.scenarioGridSimple} role="group" aria-label="Scenarios">
        {catalog.scenarios.map((entry) => {
          const active = entry.id === scenarioId;
          return (
            <button
              type="button"
              key={entry.id}
              className={`${styles.scenarioCard} ${styles.scenarioCardSimple} ${
                active ? styles.scenarioCardActive : ""
              }`}
              aria-pressed={active}
              onClick={() => onScenario(entry.id)}
            >
              <span className={styles.scenarioIcon} aria-hidden="true">
                <ScenarioIcon id={entry.id} />
              </span>
              <span className={styles.scenarioName}>{entry.displayName}</span>
            </button>
          );
        })}
      </div>

      {presets.length > 0 ? (
        <details className={styles.moreBlock}>
          <summary className={styles.moreSummary}>More</summary>
          <div className={styles.presetList}>
            {presets.map((preset) => (
              <label className={styles.presetOption} key={preset.id}>
                <input
                  type="radio"
                  name="scenario-preset"
                  value={preset.id}
                  checked={presetId === preset.id}
                  onChange={() => onPreset(preset.id)}
                />
                <span className={styles.presetName}>{preset.displayName}</span>
              </label>
            ))}
          </div>
        </details>
      ) : null}

      {needsCustomTopic ? (
        <input
          type="text"
          className={styles.textInput}
          aria-label="Topic"
          maxLength={maxLength}
          value={customTopic}
          onChange={(event) => onCustomTopic(event.target.value)}
        />
      ) : null}

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

      <p className={styles.honestyLine}>Your voice is sent to our speech partners to reply.</p>
      <p className={styles.honestyLine}>Recording off unless enabled.</p>

      <button
        type="button"
        className={`${styles.primaryButton} ${styles.startBig}`}
        onClick={onStart}
        aria-label="Start live practice call"
      >
        Call
      </button>
    </div>
  );
}

export default ScenariosView;
