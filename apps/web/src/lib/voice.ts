/**
 * The browser-visible voice service URL — **frozen in Phase 03 (FIX-1)**.
 *
 * The browser needs to know where our own voice service is. That is the
 * only thing this module carries, and it is **not a secret**: it is the
 * URL of a service the browser is allowed to talk to.
 *
 * Rules that travel with this file:
 *
 * - **No secret may use the `NEXT_PUBLIC_` prefix.** A `NEXT_PUBLIC_`
 *   value is inlined into the JavaScript bundle and is readable by anyone
 *   who opens the page. The Gnani key, the Gemini key and the Supabase
 *   service-role key stay server-side.
 * - The browser talks to **our** voice service, never to a speech
 *   provider directly. A provider credential in the browser would break
 *   the no-credential-in-the-browser rule of the frozen contract
 *   (`docs/contracts/seams.md` §5, rule 5).
 * - The value is inlined at build time by Next.js, so it is a build-time
 *   setting, not a runtime one.
 *
 * The development default is `ws://localhost:8000/ws/call`, the socket of
 * the voice service on the developer machine. The service's own origin
 * allowlist (`SPEAKING_COACH_ALLOWED_ORIGINS`) is what decides whether
 * the browser's origin may open that socket.
 */

/** The development default: the voice service on the developer machine. */
export const VOICE_WS_URL_DEFAULT = "ws://localhost:8000/ws/call";

/**
 * The WebSocket URL of the voice service, as the browser sees it.
 *
 * Set `NEXT_PUBLIC_VOICE_WS_URL` to point the browser at another
 * deployment (for example `wss://voice.example.com/ws/call`). When it is
 * unset, the development default is used.
 */
export const VOICE_WS_URL =
  process.env.NEXT_PUBLIC_VOICE_WS_URL ?? VOICE_WS_URL_DEFAULT;
