/**
 * Foundation catalog checks — Phase 01, retained by Phase 03 FIX-2.
 *
 * The Phase 04 app replaced the Phase 01 starter screen, so the
 * stub-specific screen tests are retired: their properties now live in
 * `apps/web/tests/**` (the mapping is recorded under `## FIX-2` in
 * `prompts/phase-03-contract-freeze/REPORT.md`). The two checks here
 * are about the shared catalog's honesty, which did not change, and they
 * still run against the real landing screen.
 */
import { expect, test } from "@playwright/test";

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
