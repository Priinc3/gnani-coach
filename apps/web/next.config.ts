import type { NextConfig } from "next";

/**
 * Security headers and the production boundary — Phase 07.
 *
 * The CSP is written around the two capabilities the product actually
 * needs beyond a static page:
 *
 * - the capture **AudioWorklet** (`worker-src 'self' blob:`, and the
 *   worklet asset is served by Next from our own origin);
 * - a WebSocket to the voice service, plus the same origin over HTTP for
 *   history and consent (`connect-src`).
 *
 * `'unsafe-inline'` is needed for the styles Next injects and for its
 * hydration bootstrap; `'unsafe-eval'` is development-only (the bundler's
 * eval source maps and React Refresh). A nonce-based CSP would remove the
 * inline-script allowance, but it needs a middleware nonce on every render
 * and is deliberately out of scope for this resilience phase; the
 * limitation is recorded in `docs/operations/RUNBOOK.md`.
 *
 * Sources: Next.js headers documentation
 * (<https://nextjs.org/docs/app/api-reference/config/next-config-js/headers>,
 * checked 2026-10-23), OWASP Secure Headers Project
 * (<https://owasp.org/www-project-secure-headers/>, checked 2026-10-23),
 * and MDN `Permissions-Policy`
 * (<https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy>,
 * checked 2026-10-23).
 */

const VOICE_FALLBACK = "ws://localhost:8000/ws/call";

/** The loopback hosts that are development-only. */
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

function voiceUrl(): URL {
  try {
    return new URL(process.env.NEXT_PUBLIC_VOICE_WS_URL ?? VOICE_FALLBACK);
  } catch {
    return new URL(VOICE_FALLBACK);
  }
}

/**
 * Fail the build (and therefore the deployment) on a production
 * configuration that would put a development value in front of learners.
 */
function assertProductionConfig(): void {
  if ((process.env.SPEAKING_COACH_ENVIRONMENT ?? "local").trim().toLowerCase() !== "production") {
    return;
  }
  const voice = voiceUrl();
  if (voice.protocol !== "wss:" || LOOPBACK_HOSTS.has(voice.hostname)) {
    throw new Error(
      "SPEAKING_COACH_ENVIRONMENT=production requires an explicit wss:// voice URL on a non-loopback host (NEXT_PUBLIC_VOICE_WS_URL).",
    );
  }
  if (process.env.SUPABASE_PUBLISHABLE_KEY && !process.env.SUPABASE_URL) {
    throw new Error(
      "SUPABASE_URL is required when SUPABASE_PUBLISHABLE_KEY is configured.",
    );
  }
}

function contentSecurityPolicy(): string {
  const voice = voiceUrl();
  const httpProtocol = voice.protocol === "wss:" ? "https:" : "http:";
  const voiceHttp = `${httpProtocol}//${voice.host}`;
  const development = process.env.NODE_ENV !== "production";
  const connect = new Set(["'self'", voice.origin, voiceHttp]);
  if (development) {
    // The Next dev server's HMR socket and the local voice service, on
    // whichever port the developer chose.
    connect.add("ws://127.0.0.1:*");
    connect.add("ws://localhost:*");
  }
  const script = ["'self'", "'unsafe-inline'"];
  if (development) {
    script.push("'unsafe-eval'");
  }
  return [
    "default-src 'self'",
    `script-src ${script.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "media-src 'self' blob:",
    "worker-src 'self' blob:",
    `connect-src ${Array.from(connect).join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

assertProductionConfig();

const production = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The assembled suite loads the dev server by IP, not by `localhost`,
  // so the dev-only HMR socket must accept that origin. Production is
  // unaffected: `allowedDevOrigins` is a development option.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async headers() {
    const headers = [
      { key: "Content-Security-Policy", value: contentSecurityPolicy() },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      {
        key: "Permissions-Policy",
        value: "camera=(), microphone=(self), geolocation=(), payment=(), usb=()",
      },
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
      { key: "X-DNS-Prefetch-Control", value: "off" },
      { key: "X-Permitted-Cross-Domain-Policies", value: "none" },
    ];
    if (production) {
      headers.push({
        key: "Strict-Transport-Security",
        value: "max-age=31536000; includeSubDomains",
      });
    }
    return [{ source: "/(.*)", headers }];
  },
};

export default nextConfig;
