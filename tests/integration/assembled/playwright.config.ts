import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

import { APP_URL, SUPABASE_URL, VOICE_URL } from "./constants";

/**
 * The Phase 07 assembled suite.
 *
 * It boots the **real** voice service (through the launcher, which injects
 * only the provider ports) and the **real** Next.js app, then drives a real
 * Chromium with a deterministic fake microphone. The fake Supabase backend
 * is part of the launcher.
 *
 * Workers are one: the tests share one fake database, and each test resets
 * it. Parallel calls would make the isolation assertions meaningless.
 */
const repoRoot = resolve(__dirname, "../../..");

const webEnv = {
  NEXT_PUBLIC_VOICE_WS_URL: "ws://127.0.0.1:8017/ws/call",
  SUPABASE_URL,
  SUPABASE_PUBLISHABLE_KEY: "assembled-publishable-key",
  SPEAKING_COACH_ENVIRONMENT: "local",
};

export default defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 150_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  use: {
    baseURL: APP_URL,
    trace: "retain-on-failure",
    video: "off",
    screenshot: "only-on-failure",
    permissions: ["microphone"],
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
      ],
    },
  },
  projects: [
    {
      name: "assembled-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "uv run --project services/voice python tests/integration/assembled/launcher.py",
      cwd: repoRoot,
      url: `${VOICE_URL}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run dev --workspace @gnani/web -- --port 3107",
      cwd: repoRoot,
      url: APP_URL,
      env: webEnv,
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
