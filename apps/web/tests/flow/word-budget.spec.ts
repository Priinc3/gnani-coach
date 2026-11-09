/**
 * The word budget — Phase 17.
 *
 * The learner asked for fewer words. These tests count the visible words on
 * each screen at 390×844 and fail if a screen grows past its budget. The
 * count excludes the user's own transcript (it is never on the main call
 * screen) and option text that is not visible until the dropdown opens.
 *
 * These tests are written here but not run in this box: `next build` and
 * Playwright are not allowed on the 2 GB machine.
 */

import { expect, test, type Page } from "@playwright/test";

import { installFakeHistoryService } from "../fakes/history-server";
import { installFakeVoiceServer } from "../fakes/voice-server";

const BUDGET = {
  landing: 25,
  pick: 40,
  call: 12,
  summary: 40,
  progress: 25,
  settings: 40,
} as const;

/**
 * Count the words a learner can actually see. `OPTION` text is skipped
 * because a closed dropdown shows only the selected value; hidden elements
 * and decorative `aria-hidden` subtrees are skipped too.
 */
async function visibleWords(page: Page): Promise<number> {
  return page.evaluate(() => {
    const skip = new Set(["SCRIPT", "STYLE", "OPTION", "NOSCRIPT", "TEMPLATE"]);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let text = "";
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const element = node.parentElement;
      if (!element || skip.has(element.tagName)) {
        continue;
      }
      if (element.closest("[hidden], [aria-hidden='true']")) {
        continue;
      }
      const style = window.getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
        continue;
      }
      // Ancestor display:none (the desktop nav on a phone, closed details)
      // hides the text too.
      if (typeof element.checkVisibility === "function" && !element.checkVisibility()) {
        continue;
      }
      text += ` ${node.textContent ?? ""}`;
    }
    return text
      .trim()
      .split(/\s+/)
      .filter((token) => /[\p{L}\p{N}]/u.test(token)).length;
  });
}

async function expectBudget(page: Page, screen: keyof typeof BUDGET) {
  const words = await visibleWords(page);
  expect(words, `${screen} must stay within ${BUDGET[screen]} words`).toBeLessThanOrEqual(
    BUDGET[screen],
  );
}

test.use({ viewport: { width: 390, height: 844 } });

test("landing: title, one Start, a small Sign in link", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Speak with confidence" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start a practice call" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await expectBudget(page, "landing");
});

test("pick: scenario cards, one language, one Call", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await expect(page.getByRole("heading", { name: "Choose a scenario" })).toBeVisible();
  await expect(page.getByLabel("Speaking language")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start live practice call" })).toBeVisible();
  await expect(
    page.getByText("Your voice is sent to our speech partners to reply."),
  ).toBeVisible();
  await expectBudget(page, "pick");
});

test("call: one status word, the avatar, Mute and End", async ({ page }) => {
  await installFakeVoiceServer(page, "silent");
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Mute" })).toBeVisible();
  await expect(page.getByRole("button", { name: "End" })).toBeVisible();
  await expectBudget(page, "call");
});

test("summary: three short lines, Try again and Done", async ({ page }) => {
  await installFakeVoiceServer(page, "silent");
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });
  await page.getByRole("button", { name: "End" }).click();
  await page.getByRole("button", { name: "End call now" }).click();
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Done" })).toBeVisible();
  await expectBudget(page, "summary");
});

test("progress: an empty line and Start", async ({ page }) => {
  await installFakeHistoryService(page, "empty");
  await page.goto("/");
  await page.getByRole("button", { name: "Progress" }).first().click();
  await expect(page.getByText("No sessions yet.")).toBeVisible();
  await expectBudget(page, "progress");
});

test("settings: language, recording toggle, account actions", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Practice settings" })).toBeVisible();
  await expect(page.getByLabel("Speaking language")).toBeVisible();
  await expect(page.getByLabel("Save the recording so I can replay it later")).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in or create an account" })).toBeVisible();
  await expectBudget(page, "settings");
});
