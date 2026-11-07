/**
 * The request proxy — **Phase 06 owns this file**.
 *
 * The proxy refreshes the session and keeps the response out of every
 * cache. It follows the Supabase server-side guide
 * (<https://supabase.com/docs/guides/auth/server-side/nextjs>, checked
 * 2026-10-20):
 *
 * 1. the session is refreshed with `supabase.auth.getClaims()`, which
 *    **verifies** the token. `getSession()` is never trusted here;
 * 2. the refreshed cookies are written to the request (so the server
 *    components see the fresh token) and to the response (so the browser
 *    replaces the old one);
 * 3. the response carries no-cache headers, because a response with a
 *    `Set-Cookie` must never be stored by a CDN or served to somebody
 *    else.
 *
 * What the proxy deliberately does **not** do:
 *
 * - it never **guards** a route. A guest may call: the app works
 *   without an account, and the private routes are protected by the
 *   voice service, which verifies the caller's own bearer token. In
 *   particular, `/` is never redirected and never blocked;
 * - it never reads a provider credential and never sees the
 *   service-role key: the publishable key and the project URL are the
 *   only configuration it uses, and both are public by design.
 *
 * Without a Supabase configuration the proxy passes every request
 * through unchanged: an unconfigured deployment is a guest deployment.
 */
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/** The headers that keep a session answer out of every cache. */
const NO_CACHE_HEADERS: Record<string, string> = {
  "Cache-Control": "private, no-store, no-cache, must-revalidate, max-age=0",
  Pragma: "no-cache",
  Expires: "0",
};

export async function proxy(request: NextRequest) {
  const supabaseUrl = process.env.SUPABASE_URL;
  const publishableKey = process.env.SUPABASE_PUBLISHABLE_KEY;

  if (!supabaseUrl || !publishableKey) {
    // No identity provider configured: every request is a guest
    // request, and nothing is refreshed.
    const response = NextResponse.next();
    for (const [name, value] of Object.entries(NO_CACHE_HEADERS)) {
      response.headers.set(name, value);
    }
    return response;
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl, publishableKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // The one call that matters: it verifies the token and refreshes the
  // session when it is close to expiring. A failure is not an error: a
  // caller without a valid session is a guest.
  try {
    await supabase.auth.getClaims();
  } catch {
    // A guest request continues as a guest request.
  }

  for (const [name, value] of Object.entries(NO_CACHE_HEADERS)) {
    response.headers.set(name, value);
  }
  return response;
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\.(?:png|jpg|jpeg|gif|svg|webp|ico)$).*)",
  ],
};
