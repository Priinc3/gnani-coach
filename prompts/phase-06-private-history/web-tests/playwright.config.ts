import { defineConfig, devices } from "@playwright/test";

/**
 * The Playwright configuration of the Phase 06 web tests.
 *
 * **Phase 06 owns this tree.** It is a separate configuration on purpose:
 * the root configurations belong to the foundation and to Phase 04, and
 * this one adds no dependency and touches none of their files.
 *
 * Run it from the repository root:
 *
 * ```bash
 * npx playwright test --config=prompts/phase-06-private-history/web-tests/playwright.config.ts
 * ```
 */

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: ".",
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
  webServer: {
    command: "npm run dev:web",
    // The repository root: the dev script is a workspace script.
    cwd: "../../..",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
