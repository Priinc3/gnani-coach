/**
 * The practice settings — Phase 04.
 *
 * The learner's choices, and the conversion into the frozen
 * session-settings shape. The rules that matter:
 *
 * - the speaking language and the coaching language are **separate**
 *   choices; the coaching language follows the speaking language until the
 *   learner changes it;
 * - the custom topic exists **only** for the custom scenario and is never
 *   persisted;
 * - recording retention is **off by default**, and the consent flag and the
 *   retention flag always agree;
 * - the custom topic is transient: it is never written to durable metrics
 *   and never leaves this screen except inside the `start` event.
 */

import type { SessionSettings } from "@/lib/transport";
import { validateSessionSettings } from "@/lib/transport";

export interface CatalogLanguage {
  id: string;
  displayName: string;
  nativeName: string;
  sttCode: string;
  ttsCode: string;
  capabilities: {
    documented: boolean;
    accountEnabled: boolean;
    conversationTested: boolean;
    assessmentValidated: boolean;
  };
  sourceRefs?: string[];
  notes?: string[];
}

export interface CatalogScenario {
  id: string;
  displayName: string;
  description: string;
  presets?: { id: string; displayName: string; description: string }[];
  customTopic?: { required: boolean; maxLength: number; persisted: boolean };
}

export interface CatalogLevel {
  id: string;
  displayName: string;
}

export interface PracticeCatalog {
  languages: CatalogLanguage[];
  codeMixedModes?: CatalogLanguage[];
  scenarios: CatalogScenario[];
  levels: CatalogLevel[];
}

export interface PracticeSettings {
  scenarioId: string;
  scenarioPresetId: string | null;
  /** The transient learner-written topic. Never persisted. */
  customTopic: string;
  practiceLanguageId: string;
  coachingLanguageId: string;
  /** True once the learner has chosen a coaching language themselves. */
  coachingLanguageChosen: boolean;
  levelId: string;
  /** Off by default. */
  recordingRetention: boolean;
  /** When the recording permission was granted, or null. */
  recordingRetentionGrantedAt: string | null;
  /** The transient subtitles. Off by default. */
  subtitles: boolean;
}

export type SettingsAction =
  | { type: "scenario"; scenarioId: string }
  | { type: "preset"; presetId: string | null }
  | { type: "custom_topic"; text: string }
  | { type: "practice_language"; languageId: string }
  | { type: "coaching_language"; languageId: string }
  | { type: "level"; levelId: string }
  | { type: "recording"; enabled: boolean; grantedAt: string | null }
  | { type: "subtitles"; enabled: boolean }
  | { type: "reset" };

export function initialSettings(catalog: PracticeCatalog): PracticeSettings {
  return {
    scenarioId: catalog.scenarios[0]?.id ?? "interview",
    scenarioPresetId: null,
    customTopic: "",
    practiceLanguageId: catalog.languages[0]?.id ?? "english",
    coachingLanguageId: catalog.languages[0]?.id ?? "english",
    coachingLanguageChosen: false,
    levelId: catalog.levels[0]?.id ?? "beginner",
    recordingRetention: false,
    recordingRetentionGrantedAt: null,
    subtitles: false,
  };
}

export function settingsReducer(
  state: PracticeSettings,
  action: SettingsAction,
): PracticeSettings {
  switch (action.type) {
    case "scenario":
      // A preset belongs to its scenario, so choosing another scenario
      // clears it. The custom topic is transient and is cleared too.
      return {
        ...state,
        scenarioId: action.scenarioId,
        scenarioPresetId: null,
        customTopic: "",
      };
    case "preset":
      return { ...state, scenarioPresetId: action.presetId };
    case "custom_topic":
      return { ...state, customTopic: action.text };
    case "practice_language":
      return {
        ...state,
        practiceLanguageId: action.languageId,
        coachingLanguageId: state.coachingLanguageChosen
          ? state.coachingLanguageId
          : action.languageId,
      };
    case "coaching_language":
      return {
        ...state,
        coachingLanguageId: action.languageId,
        coachingLanguageChosen: true,
      };
    case "level":
      return { ...state, levelId: action.levelId };
    case "recording":
      return {
        ...state,
        recordingRetention: action.enabled,
        recordingRetentionGrantedAt: action.enabled ? action.grantedAt : null,
      };
    case "subtitles":
      return { ...state, subtitles: action.enabled };
    case "reset":
      return state;
    default:
      return state;
  }
}

export interface SettingsBuild {
  settings: SessionSettings;
  /** Everything that is wrong with the choices, in plain words. */
  problems: string[];
}

/**
 * Turn the learner's choices into the frozen session-settings shape, and
 * check both the shape and the catalog membership.
 */
export function buildSessionSettings(
  state: PracticeSettings,
  catalog: PracticeCatalog,
): SettingsBuild {
  const problems: string[] = [];

  const scenario = catalog.scenarios.find((entry) => entry.id === state.scenarioId);
  if (!scenario) {
    problems.push("That scenario is not in the catalog.");
  }
  const practiceLanguage = catalog.languages.find(
    (entry) => entry.id === state.practiceLanguageId,
  );
  if (!practiceLanguage) {
    problems.push("That speaking language is not in the catalog.");
  }
  const coachingLanguage = catalog.languages.find(
    (entry) => entry.id === state.coachingLanguageId,
  );
  if (!coachingLanguage) {
    problems.push("That coaching language is not in the catalog.");
  }
  if (!catalog.levels.some((entry) => entry.id === state.levelId)) {
    problems.push("That level is not in the catalog.");
  }
  if (state.scenarioPresetId) {
    const presets = scenario?.presets ?? [];
    if (!presets.some((entry) => entry.id === state.scenarioPresetId)) {
      problems.push("That preset does not belong to the chosen scenario.");
    }
  }

  const settings: SessionSettings = {
    settingsVersion: "0.1",
    practiceLanguageId: state.practiceLanguageId,
    coachingLanguageId: state.coachingLanguageId,
    scenarioId: state.scenarioId,
    scenarioPresetId: state.scenarioPresetId,
    level: state.levelId as SessionSettings["level"],
    coachingRoundTurns: 4,
    sessionLimitSeconds: 600,
    recordingRetention: state.recordingRetention,
    consent: {
      consentVersion: "0.1",
      recordingRetentionGranted: state.recordingRetention,
      recordingRetentionGrantedAt: state.recordingRetentionGrantedAt,
    },
  };

  if (state.scenarioId === "custom") {
    const maxLength = scenario?.customTopic?.maxLength ?? 200;
    const text = state.customTopic.trim();
    if (text.length === 0) {
      problems.push("Write a topic so the coach knows what to talk about.");
    }
    settings.customTopic = {
      text: text.slice(0, maxLength),
      persisted: false,
    };
  }

  const validation = validateSessionSettings(settings);
  problems.push(...validation.problems);

  return { settings, problems };
}

/** The plain-word summary of the plan, shown in the settings screen. */
export function describePlan(
  state: PracticeSettings,
  catalog: PracticeCatalog,
): string {
  const scenario = catalog.scenarios.find((entry) => entry.id === state.scenarioId);
  const preset = scenario?.presets?.find((entry) => entry.id === state.scenarioPresetId);
  const practice = catalog.languages.find((entry) => entry.id === state.practiceLanguageId);
  const coaching = catalog.languages.find((entry) => entry.id === state.coachingLanguageId);
  const level = catalog.levels.find((entry) => entry.id === state.levelId);
  const parts = [
    scenario?.displayName ?? "a scenario",
    preset ? `· ${preset.displayName}` : "",
    `· practising ${practice?.displayName ?? "a language"}`,
    `· coach explains in ${coaching?.displayName ?? "a language"}`,
    `· ${level?.displayName.toLowerCase() ?? "a level"} level`,
    "· 4 turns per coaching round",
    "· up to 10 minutes",
    state.recordingRetention
      ? "· recording kept for replay (audio only; transcripts stay transient)"
      : "· recording not saved",
  ];
  return parts.filter(Boolean).join(" ");
}
