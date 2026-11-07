# Phase 03 — FIX 1: close the two seam gaps G1 would otherwise hit (small)

Type: **NORMAL** · B1 · Owner: Phase 03 only · Siblings: none · G1 stays locked.

Review basis: your REPORT plus a read of `docs/contracts/seams.md` and `call-transport.md`. I have not run your tests. The freeze is accepted except for two gaps. Fix only these, then re-run your commands. No scope growth.

## 1. 🟠 Origin allowlist and the voice-service URL are specified but not built
`call-transport.md` §7.6 requires an Origin allowlist for the WebSocket handshake and CORS. A grep of `main.py` and `settings.py` finds no CORS middleware, no allowed-origins setting, and no setting for how the browser finds the voice service. B1 TEST probes CORS, and Phase 04 and 05 each need these answers. Neither may edit `main.py` or `settings.py`.

Fix, in your own files:
- Add `SPEAKING_COACH_ALLOWED_ORIGINS` (a list; the default is the local web origin only; `*` is rejected at settings parse, with a test).
- Add the CORS middleware with that exact list. Methods are limited to those the routes use. Credentials are off unless the history routes need them (state which).
- Export a reusable `origin_allowed(origin: str | None) -> bool` in `ports/` or `main.py`, and document it in `seams.md` so Phase 05's `/ws/call` router calls it before `accept()`. Apply it to the stub `/ws/call` now: a disallowed Origin gets the handshake rejected (HTTP 403 or close 1008); an allowed Origin keeps today's `not_available`/1011 behaviour. Decide what a missing Origin does (non-browser clients) and write it down.
- Add `NEXT_PUBLIC_VOICE_WS_URL` (the non-secret voice service URL the browser uses). Document it in `seams.md` §6 and `.env.example` if one exists; give `ws://localhost:<port>/ws/call` as the dev default. No secret may use the `NEXT_PUBLIC_` prefix.
- Add integration tests: an allowed Origin passes; `https://evil.example` fails on both the HTTP CORS preflight and the WS handshake.
- Source: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html and the FastAPI CORS docs. Cite them in `seams.md`.

## 2. 🟡 Waiver dispositions (my decision; apply it)
- **W02:** apply your verified upgrade: `eslint@10.13.0` exact pin in `apps/web/package.json`, plus a lockfile refresh (`npm install --package-lock-only` or the repo's usual way). Then run `npm run lint`, `typecheck`, `build`, `test:contracts`, `test:integration`, `test:e2e` and save the output. If anything fails, revert and report; do not debug it. Never use `--force`.
- **W01:** I renew it until the Phase 09 release packaging, with the same conditions. Make no code change.

## Out of scope
Everything else in your REPORT stands. Do not touch `providers/**`, `tools/**`, `fixtures/**` or UI files. Do not start G1 or commit.

## Report
Append a `## FIX-1` section to `REPORT.md`: files changed, commands with raw output paths under `evidence/fix-1/`, the origin rules as built (missing Origin behaviour included), and the URL setting. End with `PHASE 03 FIX-1 BUILT — AWAITING B1 TEST` or `BLOCKED: reason`. Stop there.
