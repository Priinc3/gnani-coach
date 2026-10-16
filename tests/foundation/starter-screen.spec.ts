/**
 * Foundation starter-screen checks — Phase 01.
 *
 * These tests assert the screen is truthful: no microphone access, no live
 * calling, no fake data, ten catalog languages with honest badges, keyboard
 * operability, and no overflow at 360px.
 *
 * Note: assertions that count controls are scoped to `main` because the Next
 * dev-tools indicator renders its own portal outside `main`.
 */
import { expect, test } from "@playwright/test";

test("shows the honest headline and no fake data visuals", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Practice speaking, not just studying." }),
  ).toBeVisible();
  await expect(page.getByText("Foundation build", { exact: false }).first()).toBeVisible();
  expect(await page.locator("main canvas, main progress, main meter").count()).toBe(0);
});

test("lists all ten catalog languages with honest verification badges", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Not yet verified")).toHaveCount(10);
  const list = page.locator(".language-list");
  for (const name of [
    "English",
    "हिन्दी",
    "বাংলা",
    "ગુજરાતી",
    "ಕನ್ನಡ",
    "മലയാളം",
    "मराठी",
    "ਪੰਜਾਬੀ",
    "தமிழ்",
    "తెలుగు",
  ]) {
    await expect(list.getByText(name, { exact: false }).first()).toBeVisible();
  }
});

test("does not offer French or any french language code", async ({ page }) => {
  await page.goto("/");
  const content = await page.content();
  expect(content).not.toContain("French");
  expect(content).not.toContain("fr-FR");
});

test("start call is visibly unavailable with a plain reason", async ({ page }) => {
  await page.goto("/");
  const start = page.getByRole("button", { name: "Start live practice call" });
  await expect(start).toBeDisabled();
  await expect(start).toHaveAttribute("aria-describedby", "start-reason");
  await expect(
    page.getByText("Live calling will be enabled after speech-provider setup."),
  ).toBeVisible();
  expect(await page.locator("main button").count()).toBe(1);
  expect(await page.locator("main a").count()).toBe(0);
});

test("requests no microphone access on load, even after interaction", async ({ page }) => {
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
  await page.goto("/");
  // Exercise the interactive screen to prove hydration happened without any
  // microphone request.
  await page.getByLabel("What language do you want to practise?").selectOption("hindi");
  await expect(page.getByRole("status")).toContainText("practising Hindi");
  const requests = await page.evaluate(
    () => (window as unknown as { __micRequests: number }).__micRequests,
  );
  expect(requests).toBe(0);
});

test("recording retention is off by default, explained, and keyboard-toggleable", async ({
  page,
}) => {
  await page.goto("/");
  const checkbox = page.getByRole("checkbox", { name: "Save the session recording for replay" });
  await expect(checkbox).not.toBeChecked();
  const status = page.getByRole("status");
  await expect(status).toContainText("recording not saved");
  await expect(page.getByText("Off by default.", { exact: false })).toBeVisible();
  await checkbox.focus();
  await page.keyboard.press("Space");
  await expect(checkbox).toBeChecked();
  await expect(status).toContainText("recording would be kept for replay");
});

test("practice language select is focusable, labeled, and updates the plan", async ({ page }) => {
  await page.goto("/");
  const practice = page.getByLabel("What language do you want to practise?");
  const coaching = page.getByLabel("What language should the coach explain in?");
  // Headless Chromium cannot open the native select popup, so keyboard
  // operability is asserted as focusability plus the real change behavior.
  await practice.focus();
  expect(await practice.evaluate((element) => element === document.activeElement)).toBe(true);
  await practice.selectOption("hindi");
  await expect(coaching).toHaveValue("hindi");
  await expect(page.getByRole("status")).toContainText("practising Hindi");
});

test("coaching language follows practice until changed manually", async ({ page }) => {
  await page.goto("/");
  const practice = page.getByLabel("What language do you want to practise?");
  const coaching = page.getByLabel("What language should the coach explain in?");
  await practice.selectOption("tamil");
  await expect(coaching).toHaveValue("tamil");
  await coaching.selectOption("english");
  await practice.selectOption("bengali");
  await expect(coaching).toHaveValue("english");
  await expect(page.getByRole("status")).toContainText("coach explains in English");
});

test("scenario radios are keyboard operable", async ({ page }) => {
  await page.goto("/");
  const firstScenario = page.getByRole("radio", { name: /Interview practice/ });
  await firstScenario.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("radio", { name: /Workplace conversations/ })).toBeChecked();
  await expect(page.getByRole("status")).toContainText("Workplace conversations");
});

test("sample preview is optional and clearly labeled", async ({ page }) => {
  await page.goto("/");
  const label = page.getByText("sample preview — no live AI or recording");
  await expect(label).not.toBeVisible();
  await page.getByText("Optional: see a sample coaching break").click();
  await expect(label).toBeVisible();
});

test("layout does not overflow a 360px-wide screen", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Practice speaking, not just studying." }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("honours reduced-motion preference", async ({ page }) => {
  await page.goto("/");
  const card = page.locator(".scenario-option").first();
  const normal = await card.evaluate((element) => getComputedStyle(element).transitionDuration);
  expect(normal).toBe("0.12s");
  await page.emulateMedia({ reducedMotion: "reduce" });
  const reduced = await card.evaluate((element) => getComputedStyle(element).transitionDuration);
  expect(["0.01ms", "1e-05s"]).toContain(reduced);
});
