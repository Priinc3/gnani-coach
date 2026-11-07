/**
 * The call flow — Phase 04.
 *
 * These are **fixture tests**: the voice service is the fake one in
 * `apps/web/tests/fakes/`, which speaks the frozen envelope. They prove
 * that the browser side behaves as the contract says; they are not
 * evidence about the real service.
 */

import { expect, test, type Page } from "@playwright/test";

import { installFakeHistoryService } from "../fakes/history-server";
import { installFakeVoiceServer } from "../fakes/voice-server";
import { validateEnvelope } from "../fakes/contracts";

/** Walk from the landing view to the settings view. */
async function openSettings(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Continue to settings" }).click();
  await expect(page.getByRole("heading", { name: "Practice settings" })).toBeVisible();
}

test("the whole flow: onboarding, scenario, settings, call, coaching break, summary", async ({
  page,
}) => {
  const server = await installFakeVoiceServer(page, "happy");

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Speak with/ }),
  ).toBeVisible();

  // The scenario picker.
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await expect(page.getByRole("heading", { name: "Choose what you want to practise" })).toBeVisible();
  await page.getByRole("button", { name: "Workplace conversations", exact: true }).click();
  await page.getByRole("radio", { name: /Team Meeting/ }).check();
  await page.getByRole("button", { name: "Continue to settings" }).click();

  // The settings screen: the languages are separate choices and the
  // recording is off.
  await expect(page.getByRole("heading", { name: "Practice settings" })).toBeVisible();
  await page.getByLabel("Speaking language").selectOption("tamil");
  await expect(page.getByLabel("Coaching language")).toHaveValue("tamil");
  await page.getByLabel("Coaching language").selectOption("english");
  const recording = page.getByRole("checkbox", {
    name: "Save the recording so I can replay it later",
  });
  await expect(recording).not.toBeChecked();
  await recording.check();
  await expect(recording).toBeChecked();
  await expect(page.getByRole("status")).toContainText("recording kept for replay");

  // The call.
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Listening");
  await expect(page.getByRole("button", { name: "End" })).toBeVisible();

  // The client sent the start event first, and it is valid.
  const start = await server.waitFor("start");
  expect(start.direction).toBe("client_to_server");
  expect(validateEnvelope(start)).toBe(true);
  const settings = start.payload.settings as Record<string, unknown>;
  expect(settings.practiceLanguageId).toBe("tamil");
  expect(settings.coachingLanguageId).toBe("english");
  expect(settings.scenarioId).toBe("workplace");
  expect(settings.scenarioPresetId).toBe("workplace-team-meeting");
  expect(settings.recordingRetention).toBe(true);
  expect((settings.consent as Record<string, unknown>).recordingRetentionGranted).toBe(true);

  // The binary frames the client sent are all exactly 1,024 bytes.
  await expect.poll(() => server.binaryFrameSizes.length, { timeout: 5_000 }).toBeGreaterThan(0);
  for (const size of server.binaryFrameSizes) {
    expect(size).toBe(1024);
  }

  // The coaching break arrives with the round feedback.
  await expect(page.getByRole("heading", { name: /Here is a quick look/ })).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText("You opened with the outcome, which is easy to follow.")).toBeVisible();
  await expect(page.getByText("1,180 ms")).toBeVisible();
  // Filled pauses are the insufficient-evidence state: never a number.
  await expect(page.getByText(/Counting filled pauses has not been validated/)).toBeVisible();
  await expect(page.getByText("3", { exact: true })).toBeVisible();

  // The three actions.
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Keep talking" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Skip the feedback" })).toBeVisible();

  // "Keep talking" returns to the call and sends the frozen choice.
  await page.getByRole("button", { name: "Keep talking" }).click();
  await expect(page.getByRole("button", { name: "End" })).toBeVisible();
  const choice = await server.waitFor("coaching_choice");
  expect((choice.payload as Record<string, unknown>).choice).toBe("keep_talking");

  // Ending the call shows the summary (End is confirm-guarded).
  await page.getByRole("button", { name: "End" }).click();
  await page.getByRole("button", { name: "End call now" }).click();
  await expect(page.getByRole("heading", { name: "Session summary" })).toBeVisible();
  await expect(page.getByText("You opened with the outcome, which is easy to follow.")).toBeVisible();
  // No overall score, no confidence, no pronunciation grade.
  const summary = await page.locator("main").innerText();
  expect(summary).not.toMatch(/\b\d+\s*\/\s*100\b/);
  expect(summary.toLowerCase()).not.toContain("confidence");
  expect(summary.toLowerCase()).not.toContain("pronunciation");
});

test("a double click on Start opens only one connection", async ({ page }) => {
  const server = await installFakeVoiceServer(page, "silent");
  await openSettings(page);

  // Two clicks in the same task: the second one must not open a second
  // socket.
  await page.evaluate(() => {
    const button = Array.from(document.querySelectorAll("button")).find((entry) =>
      (entry.textContent ?? "").includes("Start live practice call"),
    );
    button?.click();
    button?.click();
  });

  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });
  await page.waitForTimeout(500);
  expect(server.ofType("start").length).toBe(1);
});

test("a server error is shown in plain words, with the retry rule of the shape", async ({
  page,
}) => {
  await installFakeVoiceServer(page, "server-error");
  await openSettings(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByText("The speech service is having trouble.")).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText("Try again in a moment. Nothing was saved.")).toBeVisible();
  // The shape says retryable, so a retry is offered.
  await expect(page.getByTestId("call-retry")).toBeVisible();
});

test("try again opens a new connection and the call works", async ({ page }) => {
  const server = await installFakeVoiceServer(page, "recoverable");
  await openSettings(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByText("The speech service is having trouble.")).toBeVisible({
    timeout: 10_000,
  });

  await page.getByTestId("call-retry").click();

  // The retry opened a second connection with its own `start` event, and the
  // old error is gone.
  await expect.poll(() => server.ofType("start").length, { timeout: 10_000 }).toBe(2);
  await expect(page.getByText("The speech service is having trouble.")).toHaveCount(0);
  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });
});

test("a disconnected call is reported and does not hang", async ({ page }) => {
  await installFakeVoiceServer(page, "disconnect");
  await openSettings(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  // The client reconnects on its own; the learner sees that state.
  await expect(page.getByText(/Reconnecting|Still connecting/)).toBeVisible({ timeout: 10_000 });
  // The client knows it lost the connection, so it says so plainly.
  await expect(page.getByTestId("call-status")).toContainText("Reconnecting", {
    timeout: 10_000,
  });
});

test("a duplicate event is applied once", async ({ page }) => {
  await installFakeVoiceServer(page, "duplicate");
  await openSettings(page);
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByText("That is a strong opening.")).toBeVisible({ timeout: 10_000 });
  // The duplicated coach text is applied once, not twice.
  await expect(page.getByText("That is a strong opening.")).toHaveCount(1);
});

test("the history is empty for a learner with no sessions", async ({ page }) => {
  await installFakeHistoryService(page, "empty");
  await page.goto("/");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByRole("heading", { name: "Your progress" })).toBeVisible();
  await expect(page.getByText("No sessions yet")).toBeVisible();
});

test("a guest sees the sign-in state, not an error", async ({ page }) => {
  await installFakeHistoryService(page, "guest");
  await page.goto("/");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByText("Sign in to keep progress")).toBeVisible();
  await expect(page.getByText("We could not load your progress")).toHaveCount(0);
});

test("a broken history service shows a plain error state", async ({ page }) => {
  await installFakeHistoryService(page, "error");
  await page.goto("/");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByText("We could not load your progress")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("a replay control appears only when the recording can be fetched", async ({ page }) => {
  const service = await installFakeHistoryService(page, "list-with-recording");
  await page.goto("/");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByRole("heading", { name: "Your progress" })).toBeVisible();
  await expect(page.getByLabel("Recording of this session")).toBeVisible();
  expect(service.requests.some((entry) => entry.includes("/api/recordings/"))).toBe(true);
});

test("there is no replay control when the recording is missing", async ({ page }) => {
  await installFakeHistoryService(page, "list-with-missing-recording");
  await page.goto("/");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByRole("heading", { name: "Your progress" })).toBeVisible();
  await expect(page.getByLabel("Recording of this session")).toHaveCount(0);
  // The delete control is still there: the recording id was sent.
  await expect(page.getByRole("button", { name: "Delete the recording" })).toBeVisible();
});

test("deleting a recording asks first", async ({ page }) => {
  const service = await installFakeHistoryService(page, "list-with-recording");
  await page.goto("/");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByRole("button", { name: "Delete the recording" })).toBeVisible();
  await page.getByRole("button", { name: "Delete the recording" }).click();
  await expect(page.getByText("Delete this recording? It cannot be undone.")).toBeVisible();
  await page.getByRole("button", { name: "Yes, delete it" }).click();
  await expect.poll(() => service.deleted.length, { timeout: 5_000 }).toBe(1);
  expect(service.deleted[0]).toBe("rec_fake0000000001");
});
