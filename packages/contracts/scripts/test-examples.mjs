#!/usr/bin/env node
/**
 * Frozen contract example runner — Phase 03, contract freeze (v0.1 frozen).
 *
 * Consumes the same schema/example files as the Python parity tests in
 * services/voice/tests/foundation/test_contract_parity.py.
 *
 * Explicit behavior accounted for here:
 * - Draft: every schema must declare `$schema` = JSON Schema 2020-12 (Ajv2020).
 * - Formats: ajv-formats is registered (date, date-time, uri) and format
 *   failures are genuine failures, proven by fixtures such as
 *   examples/event-envelope/invalid/space-separated-emitted-at.json.
 * - No remote fetching: every `$ref` must be local (`#/...`); the runner
 *   fails if any remote or relative reference is found.
 * - Strict: Ajv runs with `strict: true` and `allowUnionTypes: true`
 *   (nullable unions such as type: ["number", "null"] are intentional).
 *
 * Expectation comes from the folder name: examples/<schema-stem>/valid must
 * pass validation, examples/<schema-stem>/invalid must fail. The list of
 * required fixture files is asserted so neither runtime can silently drop
 * coverage.
 *
 * The runner also checks the two shared DATA files the schemas describe:
 * the language/scenario catalog and the capability-state register. The
 * capability register is where a capability's state lives, and the runner
 * asserts the frozen honesty rule: no capability may claim a validated
 * state, and the filler localisation capability is `unvalidated` and is
 * rendered as `insufficient_evidence`.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020Import from "ajv/dist/2020.js";
import addFormatsImport from "ajv-formats";

// Node ESM <-> CJS interop: accept both shapes.
const Ajv2020 = Ajv2020Import.default ?? Ajv2020Import;
const addFormats = addFormatsImport.default ?? addFormatsImport;

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const schemasDir = join(packageRoot, "schemas");
const examplesDir = join(packageRoot, "examples");
const catalogPath = join(packageRoot, "data", "catalog.json");
const capabilitiesPath = join(packageRoot, "data", "capabilities.json");

const DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";

// Compared against the sorted catalog ids.
const EXPECTED_LANGUAGE_IDS = [
  "bengali",
  "english",
  "gujarati",
  "hindi",
  "kannada",
  "malayalam",
  "marathi",
  "punjabi",
  "tamil",
  "telugu",
];
const EXPECTED_SCENARIO_IDS = ["custom", "everyday", "interview", "travel-social", "workplace"];
const EXPECTED_LEVEL_IDS = ["advanced", "beginner", "intermediate"];
// Frozen in Phase 03: the workplace scenario carries two named presets, and
// Custom Topic is a transient scenario whose learner-written text is never
// persisted.
const EXPECTED_WORKPLACE_PRESET_IDS = ["workplace-office-communication", "workplace-team-meeting"];
const CUSTOM_SCENARIO_ID = "custom";

/** Fixture files both runtimes must see. Missing any entry fails the run. */
const REQUIRED_FIXTURES = {
  catalog: {
    valid: ["minimal-catalog.json"],
    invalid: ["with-fr-stt-code.json", "with-fr-tts-code.json"],
  },
  "session-settings": {
    valid: ["default-recording-off.json", "recording-on-with-consent.json", "custom-topic-transient.json"],
    invalid: [
      "language-code-form-invalid.json",
      "recording-on-without-grant.json",
      "custom-topic-persisted.json",
      "custom-topic-without-scenario.json",
      "session-limit-over-ten-minutes.json",
    ],
  },
  "event-envelope": {
    valid: [
      "text-event.json",
      "audio-frame-descriptor.json",
      "client-start-event.json",
      "server-status-event.json",
      "server-error-not-available.json",
    ],
    invalid: [
      "mismatched-prefixed-turn-id.json",
      "base64-audio-in-text-payload.json",
      "space-separated-emitted-at.json",
      "negative-sequence.json",
      "wrong-direction-event.json",
      "unknown-event-type.json",
      "start-with-unknown-payload-key.json",
      "server-event-without-session-id.json",
    ],
  },
  "analysis-observation": {
    valid: [
      "measured-zero-fillers.json",
      "unavailable-pause.json",
      "measured-fractional-rate.json",
      "rate-with-denominator.json",
      "missing-transcription-rate.json",
      "unvalidated-filler.json",
    ],
    invalid: [
      "unavailable-with-zero-value.json",
      "available-with-null-value.json",
      "missing-unit-when-available.json",
      "confidence-as-metric.json",
      "negative-value.json",
      "fractional-count.json",
      "mismatched-unit.json",
      "rate-zero-with-missing-transcription.json",
      "active-rate-with-overall-method.json",
      "rate-with-wrong-denominator.json",
      "unknown-source-classification.json",
      "inferred-with-source-classification.json",
    ],
  },
  "durable-metrics": {
    valid: [
      "numeric-only.json",
      "controlled-provenance.json",
      "missing-transcription-rate.json",
      "split-rate-denominators.json",
    ],
    invalid: [
      "with-transcript-field.json",
      "with-audio-url-field.json",
      "with-quoted-mistakes-field.json",
      "with-model-text-field.json",
      "with-embedding-field.json",
      "method-prose-transcript.json",
      "method-prose-model-feedback.json",
      "negative-count.json",
      "fractional-count.json",
      "mismatched-unit.json",
      "rate-zero-with-missing-transcription.json",
      "active-rate-with-overall-method.json",
      "rate-with-wrong-denominator.json",
      "turn-duration-with-connection-timer.json",
      "unknown-source-classification.json",
      "turn-without-recognition-status.json",
      "pause-with-denominator.json",
    ],
  },
  "recording-metadata": {
    valid: ["retained.json", "deleted-with-deleted-at.json"],
    invalid: ["public-url-field.json", "deleted-without-deleted-at.json"],
  },
  "error-shape": {
    valid: [
      "provider-unavailable-retryable.json",
      "invalid-request-not-retryable.json",
      "not-available-stub.json",
    ],
    invalid: [
      "with-stack-field.json",
      "with-raw-transcript-field.json",
      "unknown-category.json",
      "retryable-invalid-request.json",
      "not-available-retryable.json",
    ],
  },
  "capability-state": {
    valid: ["minimal-register.json"],
    invalid: ["validated-without-evidence.json"],
  },
};

const failures = [];
const observations = [];

function fail(message) {
  failures.push(message);
}

function note(message) {
  observations.push(message);
}

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function listJsonFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => entry.name)
    .sort();
}

function schemaStems() {
  return listJsonFiles(schemasDir)
    .filter((name) => name.endsWith(".schema.json"))
    .map((name) => name.replace(/\.schema\.json$/, ""))
    .sort();
}

function walkForRemoteRefs(fileName, node, path = "$") {
  if (Array.isArray(node)) {
    node.forEach((value, index) => walkForRemoteRefs(fileName, value, `${path}[${index}]`));
    return;
  }
  if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      if (key === "$ref" && typeof value === "string" && !value.startsWith("#")) {
        fail(`${fileName}: remote or relative $ref is not allowed (found ${JSON.stringify(value)} at ${path})`);
      }
      walkForRemoteRefs(fileName, value, `${path}.${key}`);
    }
  }
}

function main() {
  const ajv = new Ajv2020({ allErrors: true, strict: true, allowUnionTypes: true });
  addFormats(ajv);

  // 1. Compile schemas, assert draft declaration and local refs only.
  const stems = schemaStems();
  if (stems.length === 0) fail("no *.schema.json files found");
  const validators = new Map();
  for (const stem of stems) {
    const fileName = `${stem}.schema.json`;
    const filePath = join(schemasDir, fileName);
    const schema = readJson(filePath);
    if (schema.$schema !== DRAFT_2020_12) {
      fail(`${fileName}: $schema must be ${DRAFT_2020_12} (found ${JSON.stringify(schema.$schema)})`);
    }
    if (typeof schema.$id !== "string" || !schema.$id.endsWith("/0.1.0")) {
      fail(`${fileName}: $id must end with /0.1.0 (draft v0.1)`);
    }
    walkForRemoteRefs(fileName, schema);
    try {
      validators.set(stem, ajv.compile(schema));
    } catch (error) {
      fail(`${fileName}: Ajv strict compile failed: ${error.message}`);
    }
  }

  // 2. Required coverage: every schema stem has valid and invalid examples.
  for (const stem of stems) {
    for (const folder of ["valid", "invalid"]) {
      const files = listJsonFiles(join(examplesDir, stem, folder));
      if (files.length === 0) fail(`examples/${stem}/${folder}: no fixture files found`);
    }
  }

  // 3. Required fixture names (shared contract with the Python parity tests).
  for (const [stem, required] of Object.entries(REQUIRED_FIXTURES)) {
    if (!validators.has(stem)) {
      fail(`required fixture stem has no schema: ${stem}`);
      continue;
    }
    for (const folder of ["valid", "invalid"]) {
      for (const name of required[folder]) {
        const filePath = join(examplesDir, stem, folder, name);
        if (!existsSync(filePath)) {
          fail(`missing required fixture: examples/${stem}/${folder}/${name}`);
        }
      }
    }
  }

  // 4. No stray example directories without a schema.
  if (existsSync(examplesDir)) {
    for (const entry of readdirSync(examplesDir, { withFileTypes: true })) {
      if (entry.isDirectory() && !validators.has(entry.name)) {
        fail(`examples/${entry.name}: example directory has no matching schema`);
      }
    }
  }

  // 5. Run the fixtures: valid must pass, invalid must fail.
  let validCount = 0;
  let invalidCount = 0;
  for (const stem of stems) {
    const validate = validators.get(stem);
    if (!validate) continue;
    for (const name of listJsonFiles(join(examplesDir, stem, "valid"))) {
      validCount += 1;
      const doc = readJson(join(examplesDir, stem, "valid", name));
      if (!validate(doc)) {
        fail(`examples/${stem}/valid/${name}: expected valid but was rejected: ${ajv.errorsText(validate.errors, { separator: " | " })}`);
      }
    }
    for (const name of listJsonFiles(join(examplesDir, stem, "invalid"))) {
      invalidCount += 1;
      const doc = readJson(join(examplesDir, stem, "invalid", name));
      if (validate(doc)) {
        fail(`examples/${stem}/invalid/${name}: expected rejection but validated`);
      }
    }
  }

  // 6. The shared catalog: schema-valid plus explicit draft invariants.
  const catalog = readJson(catalogPath);
  const catalogValidate = validators.get("catalog");
  if (!catalogValidate) {
    fail("catalog schema was not compiled");
  } else if (!catalogValidate(catalog)) {
    fail(`data/catalog.json rejected: ${ajv.errorsText(catalogValidate.errors, { separator: " | " })}`);
  }

  const languageIds = catalog.languages.map((language) => language.id).sort();
  if (languageIds.length !== EXPECTED_LANGUAGE_IDS.length) {
    fail(`data/catalog.json: expected ${EXPECTED_LANGUAGE_IDS.length} languages, found ${languageIds.length}`);
  }
  if (JSON.stringify(languageIds) !== JSON.stringify(EXPECTED_LANGUAGE_IDS)) {
    fail(`data/catalog.json: language ids differ from the documented ten (found ${languageIds.join(", ")})`);
  }
  if (new Set(languageIds).size !== languageIds.length) {
    fail("data/catalog.json: duplicate language ids");
  }
  const rawCatalogText = readFileSync(catalogPath, "utf8");
  if (rawCatalogText.includes("fr-FR") || languageIds.includes("french")) {
    fail("data/catalog.json: French must not appear as a working option");
  }
  for (const language of [...catalog.languages, ...catalog.codeMixedModes]) {
    const flags = language.capabilities;
    if (flags.documented !== true) {
      fail(`data/catalog.json: ${language.id}: documented must be true`);
    }
    for (const flag of ["accountEnabled", "conversationTested", "assessmentValidated"]) {
      if (flags[flag] !== false) {
        fail(`data/catalog.json: ${language.id}: ${flag} must stay false in draft 0.1`);
      }
    }
  }
  const hinglish = catalog.codeMixedModes.find((mode) => mode.id === "hinglish");
  if (!hinglish) {
    fail("data/catalog.json: hinglish code-mixed mode is missing");
  } else {
    if (hinglish.sttCode !== "en-IN") fail(`data/catalog.json: hinglish.sttCode must be en-IN (found ${hinglish.sttCode})`);
    if (hinglish.ttsCode !== "hi-en") fail(`data/catalog.json: hinglish.ttsCode must be hi-en (found ${hinglish.ttsCode})`);
  }
  const scenarioIds = catalog.scenarios.map((scenario) => scenario.id).sort();
  if (JSON.stringify(scenarioIds) !== JSON.stringify(EXPECTED_SCENARIO_IDS)) {
    fail(`data/catalog.json: scenario ids differ (found ${scenarioIds.join(", ")})`);
  }
  const levelIds = catalog.levels.map((level) => level.id).sort();
  if (JSON.stringify(levelIds) !== JSON.stringify(EXPECTED_LEVEL_IDS)) {
    fail(`data/catalog.json: level ids differ (found ${levelIds.join(", ")})`);
  }

  // 6b. Frozen scenario seam: the workplace presets and the transient
  // Custom Topic scenario. A preset id must be unique across the catalog.
  const presetIds = [];
  for (const scenario of catalog.scenarios) {
    for (const preset of scenario.presets ?? []) {
      presetIds.push(preset.id);
    }
  }
  if (new Set(presetIds).size !== presetIds.length) {
    fail("data/catalog.json: duplicate scenario preset ids");
  }
  const workplace = catalog.scenarios.find((scenario) => scenario.id === "workplace");
  if (!workplace) {
    fail("data/catalog.json: the workplace scenario is missing");
  } else {
    const found = (workplace.presets ?? []).map((preset) => preset.id).sort();
    if (JSON.stringify(found) !== JSON.stringify(EXPECTED_WORKPLACE_PRESET_IDS)) {
      fail(
        `data/catalog.json: workplace preset ids differ (found ${found.join(", ")})`,
      );
    }
  }
  const custom = catalog.scenarios.find((scenario) => scenario.id === CUSTOM_SCENARIO_ID);
  if (!custom) {
    fail("data/catalog.json: the custom scenario is missing");
  } else if (custom.customTopic?.required !== true) {
    fail("data/catalog.json: the custom scenario must require a transient custom topic");
  } else if (custom.customTopic?.persisted !== false) {
    fail("data/catalog.json: the custom topic must never be persisted");
  }
  for (const scenario of catalog.scenarios) {
    if (scenario.customTopic && scenario.customTopic.persisted !== false) {
      fail(`data/catalog.json: ${scenario.id}: a custom topic must never be persisted`);
    }
  }

  // 6c. The capability-state register: the shape is frozen, the data may
  // change later. The frozen honesty rules are checked here.
  const capabilities = readJson(capabilitiesPath);
  const capabilityValidate = validators.get("capability-state");
  if (!capabilityValidate) {
    fail("the capability-state schema was not compiled");
  } else if (!capabilityValidate(capabilities)) {
    fail(
      `data/capabilities.json rejected: ${ajv.errorsText(capabilityValidate.errors, { separator: " | " })}`,
    );
  }
  const filler = capabilities?.capabilities?.["filler-localization"];
  if (!filler) {
    fail("data/capabilities.json: the filler-localization capability is missing");
  } else {
    if (filler.state !== "unvalidated") {
      fail(
        `data/capabilities.json: filler-localization.state must stay "unvalidated" (found ${JSON.stringify(filler.state)})`,
      );
    }
    if (filler.renderedState !== "insufficient_evidence") {
      fail(
        `data/capabilities.json: filler-localization must be rendered as insufficient_evidence (found ${JSON.stringify(filler.renderedState)})`,
      );
    }
    if (filler.goalPreserved !== true || filler.scopeChangeApproved !== false) {
      fail(
        "data/capabilities.json: the filler goal is preserved and not narrowed; a scope change needs the owner's approval",
      );
    }
  }
  for (const [id, capability] of Object.entries(capabilities?.capabilities ?? {})) {
    if (capability.state === "validated") {
      fail(
        `data/capabilities.json: ${id} may not claim a validated state in this freeze`,
      );
    }
    if (capability.state === "unvalidated" && capability.renderedState !== "insufficient_evidence") {
      fail(
        `data/capabilities.json: ${id} is unvalidated and must be rendered as insufficient_evidence`,
      );
    }
  }

  // 6d. No durable example may write a filler count as a measured value:
  // the filler capability is unvalidated, so a missing or unvalidated filler
  // is insufficient_evidence, never 0.
  for (const name of listJsonFiles(join(examplesDir, "durable-metrics", "valid"))) {
    const document = readJson(join(examplesDir, "durable-metrics", "valid", name));
    for (const turn of document.turns ?? []) {
      for (const observation of turn.observations ?? []) {
        if (observation.metricKey === "filler.count" && observation.status === "available") {
          fail(
            `examples/durable-metrics/valid/${name}: the filler capability is unvalidated, so a filler count may not be written as available`,
          );
        }
      }
    }
  }

  note("shape-only fixture: session-settings/valid/shape-only-french-id-passes.json documents that a structurally well-formed id is not catalog membership; membership and staleness are runtime checks.");
  note("format fixtures: invalid/space-separated-emitted-at.json proves date-time format checking is active in Ajv.");

  // 7. Report.
  const lines = [];
  lines.push("Contract example runner (frozen v0.1, JSON Schema 2020-12, Ajv strict + ajv-formats)");
  lines.push(`schemas compiled: ${stems.length} (${stems.join(", ")})`);
  lines.push(`examples checked: ${validCount + invalidCount} (${validCount} valid, ${invalidCount} invalid)`);
  lines.push(`catalog: ${languageIds.length} languages, ${catalog.codeMixedModes.length} code-mixed mode(s), ${scenarioIds.length} scenarios, ${levelIds.length} levels`);
  lines.push(
    `capabilities: ${Object.keys(capabilities?.capabilities ?? {}).length} registered; filler localisation is ${filler?.state} and rendered as ${filler?.renderedState}`,
  );
  for (const observation of observations) lines.push(`note: ${observation}`);
  if (failures.length > 0) {
    lines.push(`FAILED — ${failures.length} problem(s):`);
    for (const failure of failures) lines.push(`  - ${failure}`);
    console.log(lines.join("\n"));
    process.exitCode = 1;
    return;
  }
  lines.push("PASS — all contract examples and catalog invariants hold");
  console.log(lines.join("\n"));
}

try {
  main();
} catch (error) {
  console.error("Contract draft example runner crashed:");
  console.error(error);
  process.exitCode = 1;
}
