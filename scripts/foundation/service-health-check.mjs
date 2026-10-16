#!/usr/bin/env node
/**
 * Foundation health check for the local voice service.
 *
 * Fetches GET /health and asserts the exact truthful contract: process
 * readiness only, no configuration values, and an explicit statement that no
 * live provider connection exists. Used by future batches and CI; requires a
 * running service.
 *
 * Usage:
 *   node scripts/foundation/service-health-check.mjs [full-url]
 * Default origin: SPEAKING_COACH_SERVICE_URL or http://127.0.0.1:8000
 * (the /health path is appended to the origin).
 */

const origin = process.env.SPEAKING_COACH_SERVICE_URL ?? "http://127.0.0.1:8000";
const url = process.argv[2] ?? new URL("/health", origin).href;

const expected = {
  status: "ok",
  service: "gnani-coach-voice",
  version: "0.1.0",
  phase: "foundation",
  liveCallingImplemented: false,
  detail: "Process readiness only. No live provider connection is implemented or verified.",
};

try {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`unexpected HTTP status ${response.status}`);
  }
  const body = await response.json();
  const actualKeys = Object.keys(body).sort();
  const expectedKeys = Object.keys(expected).sort();
  if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
    throw new Error(`unexpected keys: ${actualKeys.join(", ")}`);
  }
  for (const [key, value] of Object.entries(expected)) {
    if (body[key] !== value) {
      throw new Error(`field ${key}: expected ${JSON.stringify(value)}, found ${JSON.stringify(body[key])}`);
    }
  }
  console.log(
    `PASS — ${url} matches the foundation health contract (process readiness only; no live provider claim)`,
  );
} catch (error) {
  console.error(`FAIL — ${url}: ${error.message}`);
  console.error(
    "Start the service first: uv run --project services/voice uvicorn gnani_coach.main:app --host 127.0.0.1 --port 8000",
  );
  process.exitCode = 1;
}
