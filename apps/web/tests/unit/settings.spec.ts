/**
 * The session settings — Phase 04.
 *
 * The settings are checked against the frozen session-settings shape
 * before they ever reach the socket, including its cross-field rules: the
 * recording flag and the consent flag must agree, and the custom topic
 * exists only for the custom scenario and is never persisted.
 */

import { expect, test } from "@playwright/test";

import { validateSessionSettings } from "../../src/lib/transport/envelope";
import type { SessionSettings } from "../../src/lib/transport/types";
import {
  buildSessionSettings,
  initialSettings,
  settingsReducer,
  type PracticeCatalog,
} from "../../src/features/call/state/settings";
import { validateSessionSettings as validateWithSchema } from "../fakes/contracts";

const catalog: PracticeCatalog = {
  languages: [
    {
      id: "english",
      displayName: "English (India)",
      nativeName: "English",
      sttCode: "en-IN",
      ttsCode: "en-IN",
      capabilities: {
        documented: true,
        accountEnabled: false,
        conversationTested: false,
        assessmentValidated: false,
      },
    },
    {
      id: "tamil",
      displayName: "Tamil",
      nativeName: "தமிழ்",
      sttCode: "ta-IN",
      ttsCode: "ta-IN",
      capabilities: {
        documented: true,
        accountEnabled: false,
        conversationTested: false,
        assessmentValidated: false,
      },
    },
  ],
  scenarios: [
    {
      id: "interview",
      displayName: "Interview practice",
      description: "Answers out loud.",
      customTopic: { required: false, maxLength: 200, persisted: false },
    },
    {
      id: "workplace",
      displayName: "Workplace conversations",
      description: "Meetings and colleagues.",
      presets: [
        { id: "workplace-team-meeting", displayName: "Team Meeting", description: "Ideas." },
      ],
      customTopic: { required: false, maxLength: 200, persisted: false },
    },
    {
      id: "custom",
      displayName: "Custom Topic",
      description: "Your own topic.",
      customTopic: { required: true, maxLength: 200, persisted: false },
    },
  ],
  levels: [
    { id: "beginner", displayName: "Beginner" },
    { id: "intermediate", displayName: "Intermediate" },
  ],
};


/** A valid session-settings document, as the transport validator expects. */
function validSettings(): SessionSettings {
  return {
    settingsVersion: "0.1",
    practiceLanguageId: "english",
    coachingLanguageId: "english",
    scenarioId: "interview",
    scenarioPresetId: null,
    level: "beginner",
    coachingRoundTurns: 4,
    sessionLimitSeconds: 600,
    recordingRetention: false,
    consent: {
      consentVersion: "0.1",
      recordingRetentionGranted: false,
      recordingRetentionGrantedAt: null,
    },
  };
}

test("the default settings are valid and recording is off", () => {
  const state = initialSettings(catalog);
  expect(state.recordingRetention).toBe(false);
  expect(state.recordingRetentionGrantedAt).toBeNull();
  const { settings, problems } = buildSessionSettings(state, catalog);
  expect(problems).toEqual([]);
  expect(validateSessionSettings(settings).ok).toBe(true);
  expect(validateWithSchema(settings)).toBe(true);
  expect(settings.recordingRetention).toBe(false);
  expect(settings.consent.recordingRetentionGranted).toBe(false);
  expect(settings.consent.recordingRetentionGrantedAt).toBeNull();
  expect(settings.sessionLimitSeconds).toBe(600);
  expect(settings.coachingRoundTurns).toBe(4);
});

test("the coaching language follows the speaking language until it is chosen", () => {
  let state = initialSettings(catalog);
  state = settingsReducer(state, { type: "practice_language", languageId: "tamil" });
  expect(state.coachingLanguageId).toBe("tamil");
  state = settingsReducer(state, { type: "coaching_language", languageId: "english" });
  state = settingsReducer(state, { type: "practice_language", languageId: "tamil" });
  expect(state.coachingLanguageId).toBe("english");
});

test("a scenario change clears the preset and the custom topic", () => {
  let state = initialSettings(catalog);
  state = settingsReducer(state, { type: "scenario", scenarioId: "workplace" });
  state = settingsReducer(state, { type: "preset", presetId: "workplace-team-meeting" });
  state = settingsReducer(state, { type: "custom_topic", text: "a topic" });
  expect(state.scenarioPresetId).toBe("workplace-team-meeting");
  state = settingsReducer(state, { type: "scenario", scenarioId: "interview" });
  expect(state.scenarioPresetId).toBeNull();
  expect(state.customTopic).toBe("");
});

test("the custom topic is transient and only exists for the custom scenario", () => {
  let state = initialSettings(catalog);
  state = settingsReducer(state, { type: "scenario", scenarioId: "custom" });
  const missing = buildSessionSettings(state, catalog);
  expect(missing.problems.length).toBeGreaterThan(0);

  state = settingsReducer(state, { type: "custom_topic", text: "a job interview" });
  const built = buildSessionSettings(state, catalog);
  expect(built.problems).toEqual([]);
  expect(built.settings.customTopic).toEqual({ text: "a job interview", persisted: false });
  expect(validateWithSchema(built.settings)).toBe(true);

  // The same text on another scenario is not allowed.
  const other = settingsReducer(state, { type: "scenario", scenarioId: "interview" });
  const otherBuilt = buildSessionSettings(other, catalog);
  expect(otherBuilt.settings.customTopic).toBeUndefined();
});

test("keeping a recording needs the consent, and the consent needs a time", () => {
  const base = validSettings();
  const withoutConsent = {
    ...base,
    recordingRetention: true,
  };
  const result = validateSessionSettings(withoutConsent);
  expect(result.ok).toBe(false);
  expect(result.problems.join(" ")).toContain("permission");

  const grantedAt = new Date().toISOString();
  const withConsent = {
    ...base,
    recordingRetention: true,
    consent: {
      consentVersion: "0.1" as const,
      recordingRetentionGranted: true,
      recordingRetentionGrantedAt: grantedAt,
    },
  };
  expect(validateSessionSettings(withConsent).ok).toBe(true);
  expect(validateWithSchema(withConsent)).toBe(true);
});

test("a granted consent always carries the time it was granted", () => {
  const base = validSettings();
  const grantedWithoutTime = {
    ...base,
    consent: {
      consentVersion: "0.1" as const,
      recordingRetentionGranted: true,
      recordingRetentionGrantedAt: null,
    },
  };
  expect(validateSessionSettings(grantedWithoutTime).ok).toBe(false);

  const notGrantedWithTime = {
    ...base,
    consent: {
      consentVersion: "0.1" as const,
      recordingRetentionGranted: false,
      recordingRetentionGrantedAt: new Date().toISOString(),
    },
  };
  expect(validateSessionSettings(notGrantedWithTime).ok).toBe(false);
});

test("the call is capped at ten minutes and a round is at most eight turns", () => {
  const base = validSettings();
  const tooLong = { ...base, sessionLimitSeconds: 601 };
  expect(validateSessionSettings(tooLong).ok).toBe(false);
  const tooManyTurns = { ...base, coachingRoundTurns: 9 };
  expect(validateSessionSettings(tooManyTurns).ok).toBe(false);
});

test("a scenario that is not in the catalog is refused", () => {
  const state = { ...initialSettings(catalog), scenarioId: "not-a-scenario" };
  const built = buildSessionSettings(state, catalog);
  expect(built.problems.join(" ")).toContain("catalog");
});
