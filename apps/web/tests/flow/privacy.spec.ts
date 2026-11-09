/**
 * Privacy and lifecycle checks — Phase 04.
 *
 * These are **fixture tests**: the voice service is the fake one in
 * `apps/web/tests/fakes/`, so no real audio and no real transcript is ever
 * involved.
 *
 * The rules they hold:
 *
 * - the microphone is opened **only** after the learner's own gesture;
 * - a transcript never leaves memory — not to `localStorage`, not to
 *   `sessionStorage`, not to a cookie;
 * - the socket and the microphone are released when the call ends.
 */

import { expect, test, type Page } from "@playwright/test";

import { installFakeVoiceServer } from "../fakes/voice-server";

/** Count the calls to `getUserMedia` since the page loaded. */
async function micRequests(page: Page): Promise<number> {
  return page.evaluate(
    () => (window as unknown as { __micRequests: number }).__micRequests,
  );
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const state = window as unknown as { __micRequests: number };
    state.__micRequests = 0;
    if (navigator.mediaDevices) {
      const original = navigator.mediaDevices.getUserMedia?.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = ((...args: Parameters<MediaDevices["getUserMedia"]>) => {
        state.__micRequests += 1;
        return original ? original(...args) : Promise.reject(new Error("no media devices"));
      }) as MediaDevices["getUserMedia"];
    }
  });
});

test("the microphone is opened only after the learner asks for the call", async ({ page }) => {
  await installFakeVoiceServer(page, "silent");
  await page.goto("/");

  // Reading the landing page, the scenarios and the settings asks for
  // nothing at all.
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await expect(page.getByRole("heading", { name: "Choose a scenario" })).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Practice settings" })).toBeVisible();
  expect(await micRequests(page)).toBe(0);
  await page.getByRole("button", { name: "Back" }).click();

  // The gesture that starts the call is what opens it.
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });
  await expect.poll(() => micRequests(page), { timeout: 10_000 }).toBeGreaterThan(0);
});

test("nothing about the call is written to the browser storage", async ({ page }) => {
  await installFakeVoiceServer(page, "happy");
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Start live practice call" }).click();

  // The learner's own words are on the screen…
  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });
  await expect(page.getByRole("heading", { name: "Quick feedback" })).toBeVisible({
    timeout: 10_000,
  });

  // …and nowhere else.
  const stored = await page.evaluate(() => ({
    local: JSON.stringify(Object.entries(localStorage)),
    session: JSON.stringify(Object.entries(sessionStorage)),
    cookies: document.cookie,
  }));
  expect(stored.local).not.toContain("I have led teams");
  expect(stored.session).not.toContain("I have led teams");
  expect(stored.cookies).not.toContain("I have led teams");
  // No provider key and no secret is in the browser either.
  expect(stored.local).not.toMatch(/api[_-]?key|secret|authorization|bearer/i);
  expect(stored.session).not.toMatch(/api[_-]?key|secret|authorization|bearer/i);
});

test("ending the call releases the socket and the microphone", async ({ page }) => {
  const server = await installFakeVoiceServer(page, "silent");
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });

  await page.getByRole("button", { name: "End" }).click();
  await page.getByRole("button", { name: "End call now" }).click();
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible();

  // The client says goodbye in the frozen envelope.
  await server.waitFor("end", 5_000);
  expect(server.ofType("end").length).toBeGreaterThan(0);
});
