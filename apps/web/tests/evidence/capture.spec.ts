/**
 * The evidence captures — Phase 04.
 *
 * Every capture in `prompts/phase-04-call-ui/evidence/` is produced here.
 *
 * **These are fixture captures.** The voice service is the fake one in
 * `apps/web/tests/fakes/`, which speaks the frozen envelope, and the
 * microphone is Chromium's fake device. A fixture capture proves what the
 * interface does with a known event sequence; it is **not** evidence that
 * the real service behaves that way.
 *
 * The file names say which state each capture shows, and the README in
 * the evidence folder lists them.
 */

import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { installFakeHistoryService } from "../fakes/history-server";
import { installFakeVoiceServer } from "../fakes/voice-server";

const EVIDENCE_DIR = resolve(__dirname, "../../../../prompts/phase-04-call-ui/evidence");

const VIEWPORTS = [
  { width: 1440, height: 960, name: "1440" },
  { width: 1280, height: 800, name: "1280" },
  { width: 390, height: 844, name: "390" },
  { width: 360, height: 740, name: "360" },
];

/** Take one capture and check that the screen does not overflow. */
async function capture(page: Page, name: string): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, `${name} must not overflow horizontally`).toBeLessThanOrEqual(1);
  // The capture always starts at the top of the screen.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: resolve(EVIDENCE_DIR, `${name}.png`), fullPage: false });
}

async function startCall(page: Page) {
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Continue to settings" }).click();
  await expect(page.getByRole("heading", { name: "Practice settings" })).toBeVisible();
}

test.beforeAll(async () => {
  await mkdir(EVIDENCE_DIR, { recursive: true });
});

for (const viewport of VIEWPORTS) {
  test(`captures at ${viewport.name}px`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    // 1. The landing view.
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Speak with/ })).toBeVisible();
    await capture(page, `landing-${viewport.name}`);

    // 2. The scenario browser.
    await page.getByRole("button", { name: "Start a practice call" }).click();
    await expect(
      page.getByRole("heading", { name: "Choose what you want to practise" }),
    ).toBeVisible();
    await capture(page, `scenarios-${viewport.name}`);

    // 3. The settings screen, with the recording off and then on.
    await page.getByRole("button", { name: "Continue to settings" }).click();
    await expect(page.getByRole("heading", { name: "Practice settings" })).toBeVisible();
    await capture(page, `settings-recording-off-${viewport.name}`);
    const recording = page.getByRole("checkbox", {
      name: "Save the recording so I can replay it later",
    });
    await recording.check();
    await expect(recording).toBeChecked();
    await capture(page, `settings-recording-on-${viewport.name}`);
    await recording.uncheck();

    // 4. The call screen, listening.
    const server = await installFakeVoiceServer(page, "silent");
    await page.getByRole("button", { name: "Start live practice call" }).click();
    await expect(page.getByTestId("call-status")).toContainText("Listening", {
      timeout: 10_000,
    });
    await capture(page, `call-listening-${viewport.name}`);
    void server;

    // 5. The call screen, the coach speaking.
    await page.getByRole("button", { name: "End" }).click();
    await expect(page.getByRole("heading", { name: "Session summary" })).toBeVisible();
    await capture(page, `summary-${viewport.name}`);
  });
}

test("captures the coaching break, the states and the history", async ({ page }) => {
  // The coaching break at every width, with the insufficient-evidence
  // filler chip.
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await installFakeVoiceServer(page, "happy");
    await page.goto("/");
    await startCall(page);
    await page.getByRole("button", { name: "Start live practice call" }).click();
    await expect(page.getByRole("heading", { name: /Here is a quick look/ })).toBeVisible({
      timeout: 10_000,
    });
    await capture(page, `coaching-break-${viewport.name}`);
    await expect(page.getByText(/Counting filled pauses has not been validated/)).toBeVisible();
  }

  // The call screen while the coach is speaking.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await installFakeVoiceServer(page, "speaking");
  await startCall(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Speaking", {
    timeout: 10_000,
  });
  await capture(page, "call-coach-speaking-1280");

  // The same screen on a phone.
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, "call-coach-speaking-390");
  await page.setViewportSize({ width: 1280, height: 800 });

  // The call screen after the learner spoke over the coach.
  await page.goto("/");
  await installFakeVoiceServer(page, "interrupted");
  await startCall(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(
    page.getByText("You spoke over the coach, so the coach stopped."),
  ).toBeVisible({ timeout: 10_000 });
  await capture(page, "call-interrupted-1280");

  // The connecting state, and the "still connecting" notice.
  await page.goto("/");
  await installFakeVoiceServer(page, "hanging");
  await startCall(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Still connecting", {
    timeout: 10_000,
  });
  await capture(page, "call-still-connecting-1280");

  // The reconnecting state, after the service dropped the connection.
  await page.goto("/");
  await installFakeVoiceServer(page, "disconnect");
  await startCall(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText(/Reconnecting/, {
    timeout: 10_000,
  });
  await capture(page, "call-reconnecting-1280");

  // The error state, in plain words.
  await page.goto("/");
  await installFakeVoiceServer(page, "server-error");
  await startCall(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByText("The speech service is having trouble.")).toBeVisible({
    timeout: 10_000,
  });
  await capture(page, "call-error-1280");

  // The microphone was denied.
  await page.addInitScript(() => {
    const scope = navigator.mediaDevices as unknown as {
      getUserMedia: () => Promise<MediaStream>;
    };
    scope.getUserMedia = () => {
      const error = new Error("Permission denied");
      error.name = "NotAllowedError";
      return Promise.reject(error);
    };
  });
  await page.goto("/");
  await installFakeVoiceServer(page, "silent");
  await startCall(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByText("We could not use your microphone")).toBeVisible({
    timeout: 10_000,
  });
  await capture(page, "call-mic-denied-1280");

  // The empty history, at every width.
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/");
    await installFakeHistoryService(page, "empty");
    await page.getByRole("button", { name: "Progress" }).first().click();
    await expect(page.getByText("No sessions yet")).toBeVisible();
    await capture(page, `history-empty-${viewport.name}`);
  }

  // A history with a session in it.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await installFakeHistoryService(page, "list-with-recording");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByRole("heading", { name: "Your progress" })).toBeVisible();
  await capture(page, "history-list-1280");

  // The guest state.
  await page.goto("/");
  await installFakeHistoryService(page, "guest");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByText("Sign in to keep progress")).toBeVisible();
  await capture(page, "history-guest-1280");

  // The plain error state of the history.
  await page.goto("/");
  await installFakeHistoryService(page, "error");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByText("We could not load your progress")).toBeVisible();
  await capture(page, "history-error-1280");
});
