/**
 * The contract validators for the Phase 04 tests.
 *
 * The frozen schemas live in `packages/contracts/schemas/` and are
 * read-only. Ajv and ajv-formats are already installed in the workspace
 * (they are the `@gnani/contracts` dependencies), so no new dependency is
 * added here.
 *
 * Every message the client sends and every fixture the fake voice server
 * feeds is checked against the frozen shape with these validators.
 */

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import Ajv2020Import from "ajv/dist/2020.js";
import addFormatsImport from "ajv-formats";

// Node ESM <-> CJS interop: accept both shapes.
const Ajv2020 = (
  Ajv2020Import as unknown as { default?: unknown }
).default ?? Ajv2020Import;
const addFormats = (
  addFormatsImport as unknown as { default?: unknown }
).default ?? addFormatsImport;

const SCHEMAS_DIR = resolve(__dirname, "../../../../packages/contracts/schemas");

/** Read one frozen schema. */
export function loadSchema(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(SCHEMAS_DIR, name), "utf8")) as Record<string, unknown>;
}

const ajv = new (Ajv2020 as unknown as typeof import("ajv/dist/2020").default)({
  allErrors: true,
  strict: true,
  allowUnionTypes: true,
});
(addFormats as unknown as (instance: unknown) => void)(ajv);

/** Validate a client or server event envelope. */
export const validateEnvelope = ajv.compile(loadSchema("event-envelope.schema.json"));
/** Validate the session settings inside a `start` event. */
export const validateSessionSettings = ajv.compile(loadSchema("session-settings.schema.json"));
/** Validate an error payload on its own. */
export const validateErrorShape = ajv.compile(loadSchema("error-shape.schema.json"));

/** A readable failure message for a rejected document. */
export function explain(validate: { errors?: unknown }): string {
  return ajv.errorsText(
    validate.errors as Parameters<typeof ajv.errorsText>[0],
    { separator: " | " },
  );
}
