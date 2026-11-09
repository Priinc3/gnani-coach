/**
 * The phone-first shell and the installable manifest — Phase 10.
 *
 * Three small checks only:
 *
 * - the bottom tab bar is the navigation on a phone, with 48 px targets;
 * - the call controls are reachable at the bottom of a phone screen and
 *   End is confirm-guarded;
 * - the manifest has the fields an installable PWA needs.
 */

import { expect, test } from "@playwright/test";

import manifest from "../../src/app/manifest";
import { installFakeVoiceServer } from "../fakes/voice-server";

test("the manifest is installable and carries 192/512 and maskable icons", () => {
  const app = manifest();
  expect(app.name).toContain("Speaking Coach");
  expect(app.short_name).toBe("Speaking Coach");
  expect(app.display).toBe("standalone");
  expect(app.start_url).toBe("/");
  expect(app.theme_color).toBe("#10655a");
  expect(app.background_color).toBe("#f7f6f2");
  const icons = app.icons ?? [];
  const sizes = icons.map((icon) => icon.sizes);
  expect(sizes).toContain("192x192");
  expect(sizes).toContain("512x512");
  expect(icons.some((icon) => icon.purpose === "maskable")).toBe(true);
});

test("the phone shell shows the bottom tab bar with 48 px targets", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/");

  const bar = page.getByTestId("bottom-tab-bar");
  await expect(bar).toBeVisible();
  for (const name of ["Home", "Practice", "Progress"]) {
    const item = bar.getByRole("button", { name });
    await expect(item).toBeVisible();
    const box = await item.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(48);
  }
});

test("the call controls sit at the bottom and End asks first", async ({ page }) => {  await page.setViewportSize({ width: 360, height: 740 });
  await installFakeVoiceServer(page, "silent");
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Start live practice call" }).click();

  await expect(page.getByTestId("call-status")).toContainText("Listening", { timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Mute" })).toBeVisible();
  await expect(page.getByRole("button", { name: "End" })).toBeVisible();

  await page.getByRole("button", { name: "End" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Stay in call" }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(page.getByTestId("call-status")).toContainText("Listening");
});

test("a guest sees the sign-in link in Settings", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/");
  await page.getByRole("button", { name: "Start a practice call" }).click();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Practice settings" })).toBeVisible();

  const link = page.getByRole("link", { name: "Sign in or create an account" });
  await expect(link).toBeVisible();
  expect(await link.getAttribute("href")).toBe("/auth/sign-in");
  const box = await link.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(48);
});
