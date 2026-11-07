import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { expect, test } from "@playwright/test";

/**
 * The web checks of Phase 06.
 *
 * **Phase 06 owns this tree.** Two kinds of check:
 *
 * - **in the browser**: the guest experience, the session endpoint, the
 *   sign-in and the sign-out pages;
 * - **on the source**: the frozen exports, the shape of `useSession()`,
 *   the sign-out hook name, the proxy behaviour and the rule that the
 *   service-role key never reaches the web app.
 *
 * There is no Supabase project in this environment, so the checks that
 * need one prove the *unconfigured* behaviour: an unconfigured
 * deployment is a guest deployment, and it says so.
 */

const REPO_ROOT = resolve(process.cwd());
const WEB_ROOT = join(REPO_ROOT, "apps", "web");
const AUTH_SOURCE = join(WEB_ROOT, "src", "lib", "auth", "index.ts");
const BROWSER_SOURCE = join(WEB_ROOT, "src", "lib", "auth", "browser.ts");
const TYPES_SOURCE = join(WEB_ROOT, "src", "lib", "auth", "types.ts");
const PROXY_SOURCE = join(WEB_ROOT, "src", "proxy.ts");

function read(file: string): string {
  return readFileSync(file, "utf8");
}

function walk(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory)) {
    if (entry === "node_modules" || entry === ".next") {
      continue;
    }
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      found.push(...walk(path));
    } else {
      found.push(path);
    }
  }
  return found;
}

test.describe("the guest experience", () => {
  test("the root page is never guarded: a guest may call", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.status()).toBe(200);
    await expect(page.locator("body")).toBeVisible();
  });

  test("the session endpoint answers a guest", async ({ request }) => {
    const response = await request.get("/auth/session");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe("guest");
    expect(body.userId).toBeNull();
    expect(body.accessToken).toBeNull();
    expect(response.headers()["cache-control"]).toContain("no-store");
  });

  test("the sign-in page renders the session state", async ({ page }) => {
    await page.goto("/auth/sign-in");
    await expect(page.getByTestId("session-status")).toHaveText("guest");
    await expect(page.getByTestId("session-user-id")).toHaveText("");
    await expect(page.getByTestId("session-recording-retention")).toHaveText(
      "false",
    );
  });

  test("the sign-out page ends the session and says so", async ({ page }) => {
    await page.goto("/auth/sign-out");
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByTestId("sign-out-state")).toHaveText(
      "You are signed out.",
    );
  });
});

test.describe("the frozen seam", () => {
  test("the exports are there and the names did not change", () => {
    const source = read(AUTH_SOURCE);
    expect(source).toContain("export function useSession(");
    expect(source).toContain("export async function signOut(");
    // The additive export of ADDENDUM section C.
    expect(source).toContain("export async function getAccessToken(");
    // The sign-out registry hook Phase 04 subscribes to.
    expect(source).toContain("export function onSignOut(");
  });

  test("useSession keeps its shape", () => {
    const types = read(TYPES_SOURCE);
    expect(types).toContain('status: SessionStatus');
    expect(types).toContain("userId: string | null");
    expect(types).toContain("recordingRetention: boolean");
    const source = read(AUTH_SOURCE);
    expect(source).toContain("export function useSession(): SessionState");
    expect(source).toContain(
      "useSyncExternalStore(\n    subscribeSession,\n    getSessionSnapshot,\n    getServerSessionSnapshot,\n  )",
    );
  });

  test("the sign-out runs the handlers even when the sign-out fails", () => {
    const source = read(BROWSER_SOURCE);
    expect(source).toContain("export function onSignOut(");
    expect(source).toContain("runSignOutHandlers");
    // The handlers run in a `finally`, so a failing sign-out still
    // closes the live call connection.
    expect(source).toMatch(/finally\s*\{[\s\S]*runSignOutHandlers\(\)/);
  });

  test("the guest state is a supported state, not an error", () => {
    const types = read(TYPES_SOURCE);
    expect(types).toContain('"loading" | "guest" | "authenticated"');
  });
});

test.describe("the proxy", () => {
  test("it refreshes the session with getClaims", () => {
    const source = read(PROXY_SOURCE);
    expect(source).toContain("supabase.auth.getClaims()");
    expect(source).not.toContain("auth.getSession()");
  });

  test("it sets no-cache headers", () => {
    const source = read(PROXY_SOURCE);
    expect(source).toContain("no-store");
    expect(source).toContain("Pragma");
  });

  test("it never guards a route", () => {
    const source = read(PROXY_SOURCE);
    // No redirect and no refusal: a guest may call.
    expect(source).not.toContain("NextResponse.redirect");
    expect(source).not.toContain("NextResponse.rewrite");
    expect(source).not.toContain("new Response(");
  });
});

test.describe("the credentials", () => {
  test("the service-role key never reaches the web app", () => {
    for (const file of walk(WEB_ROOT)) {
      if (!/\.(ts|tsx|js|jsx|mjs|cjs|json)$/.test(file)) {
        continue;
      }
      expect(read(file)).not.toContain("SUPABASE_SERVICE_ROLE_KEY");
    }
  });

  test("no public Supabase variable exists", () => {
    for (const file of walk(WEB_ROOT)) {
      if (!/\.(ts|tsx|js|jsx|mjs|cjs|json)$/.test(file)) {
        continue;
      }
      expect(read(file)).not.toContain("NEXT_PUBLIC_SUPABASE");
    }
  });

  test("the server reads the publishable key and the URL", () => {
    const source = read(join(WEB_ROOT, "src", "lib", "auth", "server.ts"));
    expect(source).toContain("process.env.SUPABASE_URL");
    expect(source).toContain("process.env.SUPABASE_PUBLISHABLE_KEY");
  });
});
