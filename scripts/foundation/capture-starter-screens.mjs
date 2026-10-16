#!/usr/bin/env node
/**
 * Captures starter-screen screenshots as Phase 01 evidence. Requires
 * Playwright's Chromium and a running dev server.
 *
 * Usage: node scripts/foundation/capture-starter-screens.mjs [baseURL] [outDir]
 * Defaults: http://localhost:3000 and prompts/phase-01-foundation/evidence
 */
import { mkdirSync } from "node:fs";

import { chromium } from "@playwright/test";

const baseURL = process.argv[2] ?? "http://localhost:3000";
const outDir = process.argv[3] ?? "prompts/phase-01-foundation/evidence";

mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();

await page.goto(baseURL);
await page.getByRole("heading", { name: "Practice speaking, not just studying." }).waitFor();
await page.screenshot({ path: `${outDir}/12-starter-desktop.png`, fullPage: true });

await page.setViewportSize({ width: 360, height: 740 });
await page.waitForTimeout(150);
await page.screenshot({ path: `${outDir}/13-starter-360.png`, fullPage: true });

await page.setViewportSize({ width: 1280, height: 900 });
await page.waitForTimeout(150);
await page.getByText("Optional: see a sample coaching break").click();
await page.screenshot({ path: `${outDir}/14-starter-preview-open.png`, fullPage: true });

await browser.close();
console.log(`screenshots written to ${outDir}`);
