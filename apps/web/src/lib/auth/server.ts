/**
 * The server-side Supabase helpers.
 *
 * **Phase 06 owns this tree.** This module is **server-only**: it reads
 * the environment and it talks to the Auth server. Nothing here may be
 * imported by a client component.
 *
 * The rules it keeps:
 *
 * - the **publishable key** and the project **URL** are read on the
 *   server. The browser client receives them as props, so neither is
 *   inlined into the JavaScript bundle (ADDENDUM §E);
 * - the **service-role key** is never read here, never sent to the
 *   browser and never logged. It belongs to the Python service only;
 * - the identity of a caller is decided by `getClaims()`, which
 *   verifies the token. `getSession()` is used only to read the raw
 *   access token that has to be forwarded to our own voice service, and
 *   that service verifies it again.
 */

import { createServerClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

export interface SupabaseConfig {
  readonly url: string;
  readonly publishableKey: string;
}

/** One cookie of a request. */
export interface CookiePair {
  name: string;
  value: string;
}

/** One cookie to write back, with the options the library asked for. */
export interface CookieToSet {
  name: string;
  value: string;
  options: Record<string, unknown>;
}

/**
 * The adapter between the Supabase client and the cookies of a request.
 *
 * The proxy and the route handler both provide one; the difference is
 * only where the cookies are read from and written to.
 */
export interface CookieAdapter {
  getAll(): CookiePair[];
  setAll(cookiesToSet: CookieToSet[]): void;
}

/**
 * The Supabase configuration of this deployment, or `null`.
 *
 * `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are read from the
 * server environment. They are the names documented in
 * `supabase/README.md`.
 */
export function supabaseConfig(): SupabaseConfig | null {
  const url = process.env.SUPABASE_URL;
  const publishableKey = process.env.SUPABASE_PUBLISHABLE_KEY;
  if (!url || !publishableKey) {
    return null;
  }
  return { url, publishableKey };
}

/**
 * A server client bound to the cookies of one request.
 *
 * A new client is created for every request: the client carries the
 * request's cookies, and a shared client would carry one caller's
 * session into another caller's request.
 */
export function createServerSupabase(
  config: SupabaseConfig,
  adapter: CookieAdapter,
): SupabaseClient {
  return createServerClient(config.url, config.publishableKey, {
    cookies: {
      getAll: () => adapter.getAll(),
      setAll: (cookiesToSet) => {
        adapter.setAll(
          cookiesToSet.map((cookie) => ({
            name: cookie.name,
            value: cookie.value,
            options: cookie.options as Record<string, unknown>,
          })),
        );
      },
    },
  });
}

/**
 * The answer of the session endpoint: the state and, for a signed-in
 * learner, the access token to forward to our own voice service.
 */
export interface SessionAnswer {
  status: "guest" | "authenticated";
  userId: string | null;
  accessToken: string | null;
}

/** The guest answer. */
export const GUEST_ANSWER: SessionAnswer = {
  status: "guest",
  userId: null,
  accessToken: null,
};
