"use client";

/**
 * The scenario browser — Phase 04.
 *
 * Desktop area 3 of the Speakify reference (filter pills and scenario
 * cards) and mobile screen 2 of the same flow. The scenarios and their
 * presets come from the shared catalog; nothing is invented, and the
 * custom topic is transient — it is used for this call only and is never
 * saved.
 */

import styles from "../app.module.css";
import { ArrowLeftIcon, PlusIcon } from "../components/Icon";
import type { PracticeCatalog } from "../state/settings";

export interface ScenariosViewProps {
  catalog: PracticeCatalog;
  scenarioId: string;
  presetId: string | null;
  customTopic: string;
  onScenario: (scenarioId: string) => void;
  onPreset: (presetId: string | null) => void;
  onCustomTopic: (text: string) => void;
  onContinue: () => void;
  onBack: () => void;
}

export function ScenariosView({
  catalog,
  scenarioId,
  presetId,
  customTopic,
  onScenario,
  onPreset,
  onCustomTopic,
  onContinue,
  onBack,
}: ScenariosViewProps) {
  const scenario = catalog.scenarios.find((entry) => entry.id === scenarioId);
  const presets = scenario?.presets ?? [];
  const needsCustomTopic = scenario?.customTopic?.required === true;
  const maxLength = scenario?.customTopic?.maxLength ?? 200;

  return (
    <div className={styles.container}>
      <button type="button" className={styles.ghostButton} onClick={onBack}>
        <ArrowLeftIcon size={18} />
        Back
      </button>

      <section aria-labelledby="scenarios-title">
        <h2 className={styles.sectionTitle} id="scenarios-title">
          Choose what you want to practise
        </h2>
        <p className={styles.sectionLede}>
          Real-world situations, designed for practical learning. Your choice carries into the
          settings and into the call.
        </p>

        <div className={styles.filterRow} role="group" aria-label="Filter scenarios">
          <button
            type="button"
            className={`${styles.filterPill} ${styles.filterPillActive}`}
            aria-pressed="true"
          >
            All
          </button>
          {catalog.scenarios.map((entry) => (
            <button
              type="button"
              key={entry.id}
              className={styles.filterPill}
              aria-pressed={entry.id === scenarioId}
              onClick={() => onScenario(entry.id)}
            >
              {entry.displayName}
            </button>
          ))}
        </div>

        <div className={styles.scenarioGrid}>
          {catalog.scenarios.map((entry) => {
            const active = entry.id === scenarioId;
            return (
              <button
                type="button"
                key={entry.id}
                className={`${styles.scenarioCard} ${active ? styles.scenarioCardActive : ""}`}
                aria-pressed={active}
                onClick={() => onScenario(entry.id)}
              >
                <span className={styles.scenarioCardTitle}>
                  {entry.id === "custom" ? <PlusIcon size={18} /> : null}
                  {entry.displayName}
                </span>
                <p className={styles.scenarioCardText}>{entry.description}</p>
              </button>
            );
          })}
        </div>
      </section>

      {presets.length > 0 ? (
        <section className={styles.section} aria-labelledby="presets-title">
          <h3 className={styles.panelTitle} id="presets-title">
            Which one?
          </h3>
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
                <span>
                  <span className={styles.presetName}>{preset.displayName}</span>
                  <span className={styles.presetDescription}>{preset.description}</span>
                </span>
              </label>
            ))}
          </div>
        </section>
      ) : null}

      {needsCustomTopic ? (
        <section className={styles.section} aria-labelledby="custom-topic-title">
          <h3 className={styles.panelTitle} id="custom-topic-title">
            What do you want to talk about?
          </h3>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="custom-topic">
              Your topic
            </label>
            <input
              type="text"
              id="custom-topic"
              className={styles.textInput}
              maxLength={maxLength}
              value={customTopic}
              onChange={(event) => onCustomTopic(event.target.value)}
              aria-describedby="custom-topic-help"
            />
            <p className={styles.fieldHelp} id="custom-topic-help">
              Used for this call only. What you type is never saved, never stored with your history
              and never shown to anyone else.
            </p>
          </div>
        </section>
      ) : null}

      <div className={styles.row} style={{ marginTop: 26 }}>
        <button type="button" className={styles.primaryButton} onClick={onContinue}>
          Continue to settings
        </button>
      </div>
    </div>
  );
}

export default ScenariosView;
