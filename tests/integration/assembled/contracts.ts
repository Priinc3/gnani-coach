/**
 * Contract validation for the assembled suite.
 *
 * Every string the browser sends and every server envelope it receives is
 * checked against the frozen schemas in `packages/contracts/schemas/`.
 * Ajv and ajv-formats are already workspace dependencies of
 * `@gnani/contracts`; no dependency is added.
 */

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import Ajv2020Import from "ajv/dist/2020.js";
import addFormatsImport from "ajv-formats";

const Ajv2020 = (Ajv2020Import as unknown as { default?: unknown }).default ?? Ajv2020Import;
const addFormats = (addFormatsImport as unknown as { default?: unknown }).default ?? addFormatsImport;

const SCHEMAS_DIR = resolve(__dirname, "../../../packages/contracts/schemas");

export function loadSchema(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(SCHEMAS_DIR, name), "utf8")) as Record<string, unknown>;
}

const ajv = new (Ajv2020 as unknown as typeof import("ajv/dist/2020").default)({
  allErrors: true,
  strict: true,
  allowUnionTypes: true,
});
(addFormats as unknown as (instance: unknown) => void)(ajv);

export const validateEnvelope = ajv.compile(loadSchema("event-envelope.schema.json"));
export const validateSessionSettings = ajv.compile(loadSchema("session-settings.schema.json"));

export function explain(validate: { errors?: unknown }): string {
  return ajv.errorsText(validate.errors as Parameters<typeof ajv.errorsText>[0], {
    separator: " | ",
  });
}

/** Validate one parsed envelope or throw with a readable message. */
export function assertEnvelope(value: unknown, where: string): void {
  if (!validateEnvelope(value)) {
    throw new Error(`${where} is not a valid envelope: ${explain(validateEnvelope)}`);
  }
}
