/**
 * Fixed values shared by the assembled browser suite and the Python fake
 * backend.
 *
 * The JWT secret is a **test fixture** for an in-process fake. It is not a
 * credential and it never leaves the test run.
 */

import { createHmac } from "node:crypto";
import type { BrowserContext } from "@playwright/test";

export const APP_URL = "http://127.0.0.1:3107";
export const VOICE_URL = "http://127.0.0.1:8017";
export const VOICE_WS_URL = "ws://127.0.0.1:8017/ws/call";
export const SUPABASE_URL = "http://127.0.0.1:8018";
export const CONTROL_URL = "http://127.0.0.1:8019";

export const TEST_JWT_SECRET = "phase07-assembled-test-secret";
export const TEST_ISSUER = `${SUPABASE_URL}/auth/v1`;
export const COOKIE_NAME = "sb-127-auth-token";

export const USER_A = "11111111-1111-4111-8111-111111111111";
export const USER_B = "22222222-2222-4222-8222-222222222222";

export const TRANSCRIPT_SENTINEL = "orchid";
export const REPLY_SENTINEL = "That sounds clear. What happened next?";
export const TOPIC_SENTINEL = "garden planning afternoon";

function base64url(value: string | Buffer): string {
  return Buffer.from(value).toString("base64url");
}

/** Mint a test HS256 JWT the fake Auth server will accept. */
export function mintToken(subject: string, nowSeconds = Math.floor(Date.now() / 1000)): string {
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = base64url(
    JSON.stringify({
      sub: subject,
      aud: "authenticated",
      iss: TEST_ISSUER,
      role: "authenticated",
      iat: nowSeconds,
      jti: `${nowSeconds}-${Math.random().toString(16).slice(2)}`,
      exp: nowSeconds + 24 * 60 * 60,
    }),
  );
  const signature = createHmac("sha256", TEST_JWT_SECRET)
    .update(`${header}.${payload}`)
    .digest("base64url");
  return `${header}.${payload}.${signature}`;
}

/** The session JSON `@supabase/ssr` stores, encoded the way it stores it. */
export function sessionCookieValue(token: string, subject: string): string {
  const now = Math.floor(Date.now() / 1000);
  const session = {
    access_token: token,
    token_type: "bearer",
    expires_in: 24 * 60 * 60,
    expires_at: now + 24 * 60 * 60,
    refresh_token: "assembled-refresh-token",
    user: {
      id: subject,
      aud: "authenticated",
      role: "authenticated",
      email: "assembled@example.test",
      app_metadata: {},
      user_metadata: {},
      created_at: "2026-01-01T00:00:00.000Z",
    },
  };
  return `base64-${base64url(JSON.stringify(session))}`;
}

/** Give one browser context a verified session for `subject`. */
export async function signInAs(
  context: BrowserContext,
  subject: string,
): Promise<{ token: string; cookie: string }> {
  const token = mintToken(subject);
  const cookie = sessionCookieValue(token, subject);
  await context.addCookies([
    {
      name: COOKIE_NAME,
      value: cookie,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: false,
      secure: false,
      sameSite: "Lax",
      expires: Math.floor(Date.now() / 1000) + 24 * 60 * 60,
    },
  ]);
  return { token, cookie };
}
