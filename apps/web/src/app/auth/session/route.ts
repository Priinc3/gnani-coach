import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  GUEST_ANSWER,
  createServerSupabase,
  supabaseConfig,
  type SessionAnswer,
} from "@/lib/auth/server";

/**
 * The session endpoint.
 *
 * **Phase 06 owns this tree.** It answers one question: *who is the
 * caller?* It is the answer the browser cannot work out on its own when
 * the browser Supabase client is not configured.
 *
 * How it decides:
 *
 * - the session cookie is read on the server and the token is verified
 *   with `getClaims()`, which checks the signature. `getSession()` is
 *   used **only** to read the raw access token that has to be forwarded
 *   to our own voice service; that service verifies the token again, so
 *   nothing here decides an authorisation on an unverified token;
 * - a request without a verified session is a **guest**, and the answer
 *   says so. It is not an error;
 * - the answer is never cached: a cached session answer could be served
 *   to somebody else.
 */

export const dynamic = "force-dynamic";

const NO_STORE = {
  "Cache-Control": "private, no-store, no-cache, must-revalidate, max-age=0",
  Pragma: "no-cache",
  Expires: "0",
} as const;

function answer(body: SessionAnswer): NextResponse {
  return NextResponse.json(body, { headers: { ...NO_STORE } });
}

/** The current session of the caller. */
export async function GET(): Promise<NextResponse> {
  const config = supabaseConfig();
  if (!config) {
    return answer(GUEST_ANSWER);
  }

  const cookieStore = await cookies();
  const supabase = createServerSupabase(config, {
    getAll: () => cookieStore.getAll(),
    setAll: (cookiesToSet) => {
      try {
        for (const cookie of cookiesToSet) {
          cookieStore.set(cookie.name, cookie.value, cookie.options as never);
        }
      } catch {
        // A route handler may write cookies; if it may not, the proxy
        // refreshes the session instead.
      }
    },
  });

  const { data, error } = await supabase.auth.getClaims();
  const subject = data?.claims?.sub;
  if (error || typeof subject !== "string" || subject.length === 0) {
    return answer(GUEST_ANSWER);
  }

  let accessToken: string | null = null;
  try {
    const { data: session } = await supabase.auth.getSession();
    const token = session.session?.access_token;
    accessToken = typeof token === "string" && token.length > 0 ? token : null;
  } catch {
    accessToken = null;
  }

  return answer({ status: "authenticated", userId: subject, accessToken });
}

/** End the session of the caller. */
export async function DELETE(): Promise<NextResponse> {
  const config = supabaseConfig();
  if (!config) {
    return answer(GUEST_ANSWER);
  }

  const cookieStore = await cookies();
  const supabase = createServerSupabase(config, {
    getAll: () => cookieStore.getAll(),
    setAll: (cookiesToSet) => {
      try {
        for (const cookie of cookiesToSet) {
          cookieStore.set(cookie.name, cookie.value, cookie.options as never);
        }
      } catch {
        // As above.
      }
    },
  });

  try {
    await supabase.auth.signOut();
  } catch {
    // The cookies are cleared below either way.
  }

  return answer(GUEST_ANSWER);
}
