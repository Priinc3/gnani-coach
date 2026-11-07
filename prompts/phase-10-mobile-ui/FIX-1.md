# Phase 10 — FIX-1 (G2, one cycle, scope locked)

You are Phase 10 again. **Siblings running now:** [11 deploy-voice: `deploy/**`, `scripts/deploy/**`], [12 apk-ci: `apps/mobile/**`, `.github/workflows/android-apk.yml`]. Phase 14 is finished (its files are read-only for you). Comm folder: `prompts/parallel-G2/`.
Your OWN files for this fix: `apps/web/src/features/call/**`, `apps/web/tests/**`, your own row in `prompts/parallel-G2/STATUS.md` and your own entry in `prompts/parallel-G2/COMM.md`, plus `REPORT.md` (append a `## FIX-1` section; do not rewrite the old text).
DO NOT TOUCH: `apps/web/src/lib/auth/**`, `apps/web/src/app/auth/**`, `apps/web/src/proxy.ts`, `next.config.ts`, `package.json`, `services/**`, `deploy/**`, `apps/mobile/**`, `.github/**`, other phases' rows or COMM entries.
Review: [VERIFY.md](VERIFY.md). Box rules unchanged: no `next build`, no Playwright, one `tsc` and one `eslint` run at the end.

## Problem (critical first)

1. 🟠 **A learner cannot reach sign-in, sign-out from settings, or account deletion.** `grep` finds no link to `/auth/sign-in` anywhere under `features/`, and nothing calls `deleteAccount`. The sign-in page, the account backend (Phase 14) and the saved-history promise all exist, but the user cannot get to them. A signed-in learner also has "Sign out" only on the live call screen. Deleting data is a stated privacy rule.
2. 🟡 **Process:** Phase 14's commit `6453781` overwrote your row in `STATUS.md` (back to `NOT STARTED`) and dropped your entry from `COMM.md`.

## Fix

1. **Reach sign-in on a phone and a laptop.** Add a clear "Sign in or create an account" entry, shown only to guests, in all three places: the landing view, the empty state of the Progress/history view, and the Settings view. Use `next/link` to `/auth/sign-in` (same origin, so it stays inside the APK WebView). Min height 48 px, plain words, and one line saying guests can still practise but nothing is saved. The tab bar stays Home / Practice / Progress.
2. **Account section in Settings (signed-in only):**
   - "Signed in. Your history is stored on our server." plus a **Sign out** button (call `onSignOut`/`signOut` the way `CallExperience.handleSignOut` already does).
   - **Delete my account and data**: a destructive button that opens the same kind of confirm sheet you built for End; it asks for the password in a `type="password"` field (16 px, `autocomplete="current-password"`), says plainly "This deletes your account, history and saved recordings. It cannot be undone.", then calls `deleteAccount(password)` from `@/lib/auth`.
   - On `ok`: reset the session state, return to the landing view, show a short confirmation. On failure: show the returned `message` in plain words and keep the sheet open. Never log or store the password; clear the field on close.
3. **Process:** restore **only your own** STATUS row (`10 | DONE | <time> | Phone layout, PWA, mic check, account entry`) and re-add your COMM entry (`## 10 08:45 — Phase 10 done ...`, text in commit `88f4b26`). Do not alter other rows or entries; if another phase edited the files since, pull first.
4. Update only the tests whose assertions you change; add **at most one** small test (guest sees the sign-in link in Settings). Do not run Playwright here.

## Verify with
- Read: a guest sees a link to `/auth/sign-in` in all three places; a signed-in learner sees no such link, sees Sign out and Delete; the delete flow calls `deleteAccount` exactly once per confirmed submit.
- `NODE_OPTIONS=--max-old-space-size=512 npx tsc --noEmit` exit 0, then `npx eslint` on touched files exit 0 (raw output in `evidence/`).
- `git diff --stat` shows no path outside your OWN list.

## Constraints
No new dependency. Honesty rules unchanged (no scores, no "end-to-end encrypted", no all-ten-language claim). Mobile rules unchanged (no horizontal scroll at 360 px, 44 px targets).

## Git (user-authorized W08)
`git add` only your own paths, commit `phase-10: fix-1 account entry points`, `git pull --rebase origin main`, `git push origin main`, report the hash.

## Update REPORT.md
Append `## FIX-1`: files changed, commands with output paths, how each point was verified, limits (nothing executed in a browser), commit hash. End with `PHASE 10 FIX-1 BUILT`. Stop there.
