/**
 * Accessibility and responsive checks — Phase 04.
 *
 * These are **fixture tests** for the screens (the voice service is the
 * fake one); the checks themselves are about the interface, not about the
 * service.
 */

import { expect, test, type Page } from "@playwright/test";

import { installFakeVoiceServer } from "../fakes/voice-server";

const VIEWPORTS = [
  { width: 1440, height: 900, name: "1440" },
  { width: 1280, height: 800, name: "1280" },
  { width: 390, height: 844, name: "390" },
  { width: 360, height: 740, name: "360" },
];

/** The horizontal overflow of the document, in pixels. */
async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

test("every button has an accessible name", async ({ page }) => {
  await page.goto("/");
  const unnamed = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll("button"));
    return buttons
      .filter((button) => {
        const label =
          button.getAttribute("aria-label") ?? button.getAttribute("title") ?? button.innerText;
        return !label || label.trim().length === 0;
      })
      .map((button) => button.outerHTML.slice(0, 140));
  });
  expect(unnamed).toEqual([]);
});

test("the flow is complete with the keyboard alone", async ({ page }) => {
  await installFakeVoiceServer(page, "happy");
  await page.goto("/");

  const start = page.getByRole("button", { name: "Start a practice call" });
  await start.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Choose a scenario" })).toBeVisible();

  const call = page.getByRole("button", { name: "Start live practice call" });
  await call.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "End" })).toBeVisible();

  const end = page.getByRole("button", { name: "End" });
  await end.focus();
  await page.keyboard.press("Enter");
  // End is guarded: the learner confirms in the sheet.
  const confirm = page.getByRole("button", { name: "End call now" });
  await expect(confirm).toBeVisible();
  await confirm.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible();
});

test("the focus is visible on the controls", async ({ page }) => {
  await page.goto("/");
  const button = page.getByRole("button", { name: "Start a practice call" });
  await button.focus();
  const outline = await button.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return { width: style.outlineWidth, style: style.outlineStyle };
  });
  expect(outline.style).not.toBe("none");
  expect(Number.parseFloat(outline.width)).toBeGreaterThan(0);
});

test("the status and the feedback are announced", async ({ page }) => {
  await installFakeVoiceServer(page, "happy");
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Start live practice call" }).click();

  // The call status is a live region.
  const liveRegions = await page.locator("[aria-live]").count();
  expect(liveRegions).toBeGreaterThan(0);
  await expect(page.getByTestId("call-status")).toContainText("Listening");
});

test("no screen overflows horizontally", async ({ page }) => {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/");
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);

    await page.getByRole("button", { name: "Start a practice call" }).click();
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);

    await page.getByRole("button", { name: "Settings" }).click();
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);

    await page.getByRole("button", { name: "Back" }).first().click();
    await page.getByRole("button", { name: "Progress" }).first().click();
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
  }
});

test("the reduced-motion preference is honoured", async ({ page }) => {
  await page.goto("/");
  const ring = page.locator("span").filter({ hasNot: page.locator("svg") }).first();
  void ring;
  await page.emulateMedia({ reducedMotion: "reduce" });
  const duration = await page.evaluate(() => {
    const element = document.querySelector("[class*='pulseRing']");
    if (!element) {
      return null;
    }
    return window.getComputedStyle(element).animationDuration;
  });
  // The pulse is decorative; with reduced motion it must not run.
  expect(duration === null || ["0.01ms", "1e-05s", "0s"].includes(duration)).toBe(true);
});

test("the Indic scripts are rendered with their own language", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByText("More", { exact: true }).click();
  const hindi = page.locator("option[lang='hi-IN']");
  const tamil = page.locator("option[lang='ta-IN']");
  await expect(hindi).toHaveText("हिन्दी");
  await expect(tamil).toHaveText("தமிழ்");
});

test("the transcript is not kept after the call ends", async ({ page }) => {
  // The silent scenario keeps the call open, so the transcript control is
  // not replaced by a coaching break while the test runs.
  await installFakeVoiceServer(page, "silent");
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Listening");
  // Turn the transient transcript on.
  await page.getByRole("button", { name: "Transcript" }).click();
  await expect(page.getByLabel("Live transcript")).toBeVisible();
  await page.getByRole("button", { name: "End" }).click();
  await page.getByRole("button", { name: "End call now" }).click();
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible();
  // The transcript is gone: it is transient and is never persisted.
  await expect(page.getByLabel("Live transcript")).toHaveCount(0);
  await expect(page.getByText("I have led teams for six years.")).toHaveCount(0);
});
