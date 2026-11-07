import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

/**
 * The Phase 04 test configuration.
 *
 * It is **Phase 04's own** configuration, so the root configurations
 * (`playwright.config.ts` and `playwright.integration.config.ts`) are not
 * touched.
 *
 * Three projects:
 *
 * - `unit` — pure logic (the frame packer, the capture worklet, the
 *   fencing, the transport client, the reducers). These tests never ask
 *   for a page, so no browser is started for them;
 * - `flow` — the screens and the flow, against the fake voice server in
 *   `apps/web/tests/fakes/`;
 * - `evidence` — the screenshot captures, written to
 *   `prompts/phase-04-call-ui/evidence/`.
 *
 * The web server is the real Next.js app, so the flow and evidence tests
 * run against the real build.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const repoRoot = resolve(__dirname, "../../..");

/** Chromium with a fake microphone, so the capture path can be exercised. */
const fakeMicrophone = {
  permissions: ["microphone"],
  launchOptions: {
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
    ],
  },
};

export default defineConfig({
  testDir: __dirname,
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "unit",
      testDir: "./unit",
    },
    {
      name: "flow",
      testDir: "./flow",
      use: {
        ...devices["Desktop Chrome"],
        ...fakeMicrophone,
      },
    },
    {
      name: "evidence",
      testDir: "./evidence",
      use: {
        ...devices["Desktop Chrome"],
        ...fakeMicrophone,
      },
    },
  ],
  webServer: {
    command: "npm run dev:web",
    cwd: repoRoot,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
