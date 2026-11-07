# Phase 10 — mobile-ui — REPORT

## Files changed

- `apps/web/src/app/layout.tsx` — `viewport` export (`viewport-fit=cover`,
  `themeColor`, light colour scheme) and honest metadata.
- `apps/web/src/app/manifest.ts` — installable PWA manifest (standalone,
  `start_url: "/"`, theme/background, 192/512 + maskable icons). No service
  worker.
- `apps/web/public/icons/icon-192.png`, `icon-512.png`,
  `icon-maskable-512.png` — original SparkIcon mark on the brand-green tile,
  rendered from an inline geometry script with no third-party art.
- `apps/web/src/app/globals.css` — `100dvh` body, safe-area bottom padding,
  ≥16 px form fields, 48 px+ option rows, no-shrink grid children.
- `apps/web/src/features/call/app.module.css` — phone call layout, bottom
  control bar, transcript drawer, confirm sheet, mic-check styles, sticky
  primary action, 48 px tab targets, desktop/tablet breakpoints.
- `apps/web/src/features/call/CallExperience.tsx` — 48 px header CTA, tab-bar
  test id; the existing bottom tab bar (Home/Practice/Progress) is the phone
  navigation.
- `apps/web/src/features/call/views/CallView.tsx` — status is the largest
  text at the top, coach visual centred, Mute / Give me a moment / End in the
  bottom bar, End confirm-guarded, transcript in a pull-up drawer, speaker
  control kept as a labelled icon, Coach me now kept.
- `apps/web/src/features/call/components/MicCheck.tsx` — pre-call check that
  explains the browser prompt in plain words, stops the test track at once,
  and shows a next step (site settings or Android app permissions) plus
  retry when denied.
- `apps/web/src/features/call/views/SettingsView.tsx`,
  `views/ScenariosView.tsx` — mic check on setup, sticky primary action in
  thumb reach above the tab bar, stacked full-width setup fields.
- `apps/web/tests/flow/{a11y,call-flow,privacy}.spec.ts`,
  `tests/evidence/capture.spec.ts` — End now needs the confirm step.
- `apps/web/tests/flow/mobile-ui.spec.ts` — three new checks: manifest
  fields, phone tab bar with 48 px targets, reachable call controls and the
  End guard.

## Commands run

- `cd apps/web && NODE_OPTIONS=--max-old-space-size=512 npx tsc --noEmit`
  → exit 0. Raw output: `evidence/tsc-noemit.log`,
  `evidence/tsc-command.txt`.
- `cd apps/web && npx eslint <touched TS/TSX files>` → exit 0 (the two CSS
  files are ignored by the repo's ESLint config). Raw output:
  `evidence/eslint.log`, `evidence/eslint-command.txt`.

The first `tsc` attempt ran while Phase 14 was mid-write on
`app/auth/sign-in/SignInPanel.tsx` and reported two missing auth exports from
that in-flight file; the clean run above is after the sibling finished.

## What was verified, and how

- Read the existing 360/390 screenshots in
  `prompts/phase-04-call-ui/evidence/` before changing the layout. No browser
  was launched on this box.
- Phone layout by reading CSS/JSX: below 720 px the top nav is hidden and the
  bottom tab bar is shown with `min-height: 48px`; the call screen is
  `height: 100dvh; overflow: hidden` with the transcript in a fixed drawer
  above the bottom control bar; End opens an `alertdialog` and only
  `End call now` calls `onEnd`; setup screens use stacked fields and a
  sticky full-width primary button above the tab bar.
- Desktop (≥960 px) keeps the hero two-column composition and the wide
  feature/scenario grids; 720–959 px keeps the top nav and a normal
  transcript panel.
- Safe areas: `viewportFit: "cover"` in `layout.tsx`, and
  `env(safe-area-inset-bottom/top)` in the shell, tab bar, call controls,
  drawer and sticky action.
- Inputs are `max(16px, 1rem)` (no iOS zoom); tap targets are 44–52 px.
  Focus-visible and `prefers-reduced-motion` rules are unchanged.
- Honesty rules untouched: no scores, no filler counts, no verified-language
  claim; the existing “Not yet verified” badge is kept.
- PWA: `manifest()` has `display: "standalone"`, `start_url: "/"`, the two
  required sizes and a maskable icon; icons are same-origin and pass the
  existing CSP. `next.config.ts`, `package.json` and lockfiles are untouched.
- Mic UX: the check only opens the microphone on a button press; a denied
  result explains the site-settings and Android `RECORD_AUDIO` paths and
  offers retry. The call itself still opens the microphone only from the
  Start gesture, so `privacy.spec.ts` keeps its zero-request guarantee.

## Limits

- No `next build`, `next dev`, Playwright or full suite on this box (2 GB
  box rule). The three new tests and the updated End-confirm steps are
  written but not executed here; Vercel/CI runs them.
- Visual acceptance at 360×740, 390×844, 768×1024 and 1280×800 was done by
  reading the CSS and the Phase 04 screenshots, not by rendering.
- The first `tsc` run overlapped Phase 14's edit; only the second run is
  evidence.

## Help needed

- None. Phase 14 may call its own `deleteAccount` export from the sign-in
  page; Phase 10 did not edit those files.

PHASE 10 BUILT

## FIX-1

### Files changed

- `apps/web/src/features/call/components/SignInEntry.tsx` (new) — the
  guest-only same-origin link to `/auth/sign-in`, min height 48 px, with the
  one-line promise that guests can still practise but nothing is saved.
- `apps/web/src/features/call/components/AccountSection.tsx` (new) — guest
  entry in Settings; signed-in account state, Sign out, and the destructive
  delete flow. Delete reuses the End-call sheet, asks for the password in a
  `type="password"` field with `autocomplete="current-password"`, states
  “This deletes your account, history and saved recordings. It cannot be
  undone.”, calls `deleteAccount(password)` once per confirmed submit, keeps
  the sheet open on failure with the returned message, and clears the field
  on close.
- `apps/web/src/features/call/views/LandingView.tsx` — guest sign-in entry
  and a short account-deleted confirmation.
- `apps/web/src/features/call/views/HistoryView.tsx` — guest sign-in entry
  inside the existing empty Progress state.
- `apps/web/src/features/call/views/SettingsView.tsx` — renders the account
  section at the top of the settings stack and accepts `onSignOut` /
  `onDeleted`.
- `apps/web/src/features/call/CallExperience.tsx` — wires the existing
  `handleSignOut`, adds `handleAccountDeleted` (reset call state, landing
  view, confirmation), and passes `signedIn`/`notice` to the landing view.
- `apps/web/src/features/call/app.module.css` — styles for the sign-in entry,
  account cards, delete form and error line; 48 px destructive/secondary
  targets.
- `apps/web/tests/flow/mobile-ui.spec.ts` — one new test: a guest sees the
  sign-in link in Settings, its href is `/auth/sign-in`, and its target is at
  least 48 px tall.

### Commands run

- `cd apps/web && NODE_OPTIONS=--max-old-space-size=512 npx tsc --noEmit`
  → exit 0. Raw output: `evidence/tsc-fix1.log`,
  `evidence/tsc-fix1-command.txt`.
- `cd apps/web && npx eslint <touched TS/TSX files>` → exit 0 (CSS is
  ignored by the repo config). Raw output: `evidence/eslint-fix1.log`,
  `evidence/eslint-fix1-command.txt`.

### Verified by reading

- Guest entry exists in all three places and only for guests:
  `LandingView` renders it when `signedIn` is false; `HistoryView` renders it
  in the `state.kind === "guest"` branch; `AccountSection` renders it in
  Settings when `signedIn` is false. Signed-in learners get the account card
  instead, with Sign out and Delete.
- Delete calls `deleteAccount(password)` exactly once per submit: the form
  has one `onSubmit`, and a `busy` guard returns before a second request.
  The password lives only in component state, is cleared on success and on
  close, and is never logged.
- On success `deleteAccount` has already moved the session to guest; the app
  calls `session.reset()`, returns to landing and shows
  “Your account, history and saved recordings were deleted.”
- No paths outside the FIX-1 OWN list were edited; `git diff --stat` before
  the commit showed only `features/call/**`, `tests/**`, the two G2 files and
  this phase folder.
- Honesty and mobile rules unchanged: no scores, no “end-to-end encrypted”
  claim, no language-verification claim; the new link is a 48 px target and
  does not add horizontal scroll.

### Process restore

- `STATUS.md` row 10 restored to `DONE | 08:52 | Phone layout, PWA, mic
  check, account entry`.
- `COMM.md` re-added the `## 10 08:45 — Phase 10 done …` entry from
  `88f4b26` and added the FIX-1 entry. No other row or entry was changed.

### Limits

- No browser, Playwright or `next build` on this box (2 GB rule). The new
  test and the delete/sign-out UI were verified by reading and by `tsc` /
  `eslint`; the real click-through belongs to the Phase 13 smoke.
- Commit hash: `3d03a29` (`phase-10: fix-1 account entry points`).

PHASE 10 FIX-1 BUILT

