/**
 * D — the response-header contract, checked on the real Next.js server.
 *
 * The CSP is a compatibility check, not decoration: it has to allow the
 * capture AudioWorklet and the voice WebSocket, and deny framing. A typo in
 * either direction is caught here.
 */

import { expect, test } from "@playwright/test";

import { APP_URL } from "./constants";

test("the web app sends the security headers it documents", async ({ page }) => {
  const response = await page.goto(APP_URL);
  expect(response).not.toBeNull();
  const headers = response!.headers();

  const csp = headers["content-security-policy"] ?? "";
  expect(csp).toContain("default-src 'self'");
  expect(csp).toContain("worker-src 'self' blob:");
  expect(csp).toContain("connect-src");
  expect(csp).toContain("ws://127.0.0.1:8017");
  expect(csp).toContain("object-src 'none'");
  expect(csp).toContain("base-uri 'self'");
  expect(csp).toContain("frame-ancestors 'none'");

  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["permissions-policy"]).toContain("microphone=(self)");
  expect(headers["permissions-policy"]).toContain("camera=()");
  expect(headers["cross-origin-opener-policy"]).toBe("same-origin");
  expect(headers["cross-origin-resource-policy"]).toBe("same-origin");
});

test("the history and consent routes never carry the token in a URL", async ({ page }) => {
  // The bearer token is read from the session by the page; nothing in the
  // route shape accepts a token in a query string. This asserts the shape
  // the app requests, not the absence of every possible URL on the machine.
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto(APP_URL);
  await page.waitForTimeout(500);
  for (const url of requests) {
    expect(url).not.toMatch(/[?&](access_token|token|apikey)=/i);
  }
});
