/**
 * The voice service's HTTP base URL — Phase 04.
 *
 * `prompts/parallel-G1/ADDENDUM.md` §B: the browser derives `VOICE_HTTP_URL`
 * from `VOICE_WS_URL` in its own lib, without editing `lib/voice.ts`:
 * `ws` becomes `http`, `wss` becomes `https`, and the path is stripped.
 *
 * The result is the base of the four history routes:
 * `GET /api/history`, `POST /api/consent`, `GET /api/recordings/{id}` and
 * `DELETE /api/recordings/{id}`.
 */

/** Derive the HTTP base URL from the WebSocket URL. */
export function deriveVoiceHttpUrl(wsUrl: string): string {
  const url = new URL(wsUrl);
  url.protocol = url.protocol === "wss:" ? "https:" : "http:";
  url.pathname = "/";
  url.search = "";
  url.hash = "";
  return url.origin;
}

/** The headers every request carries. The token is the caller's own. */
export function authHeaders(token: string | null): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}
