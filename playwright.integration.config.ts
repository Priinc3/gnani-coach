import { defineConfig, devices } from "@playwright/test";

/**
 * The integration test configuration — Phase 03.
 *
 * It boots **both** real processes: the Next.js app and the FastAPI voice
 * service, and points the tests at them. The foundation suite
 * (`playwright.config.ts`) is untouched and keeps its own single web
 * server, so the Phase 01 checks stay independent of the service.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const serviceURL = process.env.SPEAKING_COACH_SERVICE_URL ?? "http://127.0.0.1:8000";

/**
 * The origin the browser will send in the `Origin` header of the
 * WebSocket handshake. The voice service refuses a handshake from an
 * origin that is not on its allowlist (`SPEAKING_COACH_ALLOWED_ORIGINS`,
 * frozen in `docs/contracts/seams.md` §8), so the integration run tells
 * the service which origin to expect — the page it is about to load.
 */
const webOrigin = new URL(baseURL).origin;

export default defineConfig({
  testDir: "./tests/integration",
  // The Phase 07 assembled suite lives under this directory but has its own
  // config and its own ports (3107/8017/8018). It must not be collected here:
  // its `@playwright/test` imports would run against the wrong servers.
  testIgnore: ["assembled/**"],
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "npm run dev:web",
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command:
        "uv run --project services/voice python -m uvicorn gnani_coach.main:app --host 127.0.0.1 --port 8000",
      url: `${serviceURL}/health`,
      env: {
        SPEAKING_COACH_ALLOWED_ORIGINS: JSON.stringify([webOrigin]),
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
