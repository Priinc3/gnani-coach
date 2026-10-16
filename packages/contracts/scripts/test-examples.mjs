#!/usr/bin/env node
/**
 * Draft contract example runner — Phase 01, draft v0.1.
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
const EXPECTED_SCENARIO_IDS = ["everyday", "interview", "travel-social", "workplace"];
const EXPECTED_LEVEL_IDS = ["advanced", "beginner", "intermediate"];

/** Fixture files both runtimes must see. Missing any entry fails the run. */
const REQUIRED_FIXTURES = {
  catalog: {
    valid: ["minimal-catalog.json"],
    invalid: ["with-fr-stt-code.json", "with-fr-tts-code.json"],
  },
  "session-settings": {
    valid: ["default-recording-off.json", "recording-on-with-consent.json"],
    invalid: ["language-code-form-invalid.json", "recording-on-without-grant.json"],
  },
  "event-envelope": {
    valid: ["text-event.json", "audio-frame-descriptor.json"],
    invalid: [
      "mismatched-prefixed-turn-id.json",
      "base64-audio-in-text-payload.json",
      "space-separated-emitted-at.json",
      "negative-sequence.json",
    ],
  },
  "analysis-observation": {
    valid: ["measured-zero-fillers.json", "unavailable-pause.json"],
    invalid: [
      "unavailable-with-zero-value.json",
      "available-with-null-value.json",
      "missing-unit-when-available.json",
      "confidence-as-metric.json",
    ],
  },
  "durable-metrics": {
    valid: ["numeric-only.json"],
    invalid: [
      "with-transcript-field.json",
      "with-audio-url-field.json",
      "with-quoted-mistakes-field.json",
      "with-model-text-field.json",
      "with-embedding-field.json",
    ],
  },
  "recording-metadata": {
    valid: ["retained.json", "deleted-with-deleted-at.json"],
    invalid: ["public-url-field.json", "deleted-without-deleted-at.json"],
  },
  "error-shape": {
    valid: ["provider-unavailable-retryable.json", "invalid-request-not-retryable.json"],
    invalid: [
      "with-stack-field.json",
      "with-raw-transcript-field.json",
      "unknown-category.json",
      "retryable-invalid-request.json",
    ],
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

  note("shape-only fixture: session-settings/valid/shape-only-french-id-passes.json documents that a structurally well-formed id is not catalog membership; membership and staleness are runtime checks.");
  note("format fixtures: invalid/space-separated-emitted-at.json proves date-time format checking is active in Ajv.");

  // 7. Report.
  const lines = [];
  lines.push("Contract draft example runner (draft v0.1, JSON Schema 2020-12, Ajv strict + ajv-formats)");
  lines.push(`schemas compiled: ${stems.length} (${stems.join(", ")})`);
  lines.push(`examples checked: ${validCount + invalidCount} (${validCount} valid, ${invalidCount} invalid)`);
  lines.push(`catalog: ${languageIds.length} languages, ${catalog.codeMixedModes.length} code-mixed mode(s), ${scenarioIds.length} scenarios, ${levelIds.length} levels`);
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
