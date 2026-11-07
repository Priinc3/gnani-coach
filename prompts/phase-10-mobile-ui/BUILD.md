# Phase 10 — mobile-ui (B4, PARALLEL:G2)

You are Phase 10 (G2). **Siblings running now:** [11 deploy-voice: `deploy/**`, `scripts/deploy/**`, `docs/release/DEPLOY.md`, root `.env.example`], [12 apk-ci: `apps/mobile/**`, `.github/workflows/android-apk.yml`], [14 sqlite-backend: `services/voice/src/gnani_coach/{identity,persistence}/**`, `apps/web/src/lib/auth/**`, `apps/web/src/app/auth/**`, `apps/web/src/proxy.ts`].
Your OWN files: `apps/web/src/**` **except** `lib/auth/**`, `app/auth/**`, `proxy.ts` (Phase 14 owns those); `apps/web/public/**` (new), `apps/web/tests/**` (except tests of Phase 14's files), your `prompts/phase-10-mobile-ui/REPORT.md` + `evidence/`.
Auth screens: Phase 14 builds the sign-in page and posts the export name for delete-account in COMM. You may link to it and call its exports, never edit them. Sign-in is email + password on our own server (no Supabase), so any copy about magic links or Supabase must go.
DO NOT TOUCH: `apps/web/next.config.ts`, `apps/web/package.json` and any lockfile (no new dependency), `services/**`, `packages/**`, `supabase/**`, `deploy/**`, `apps/mobile/**`, `.github/**`, root files, `tests/integration/**`, CEO files.
Shared read-only: `docs/contracts/**` (frozen seams), `packages/contracts/**`, `prompts/phase-04-call-ui/UI-REFERENCE.md`, `UI.png`.
Comm folder: `prompts/parallel-G2/`.

## Context
End goal (`prompts/00-plan.md` §10): a learner uses the app on a phone or a laptop and completes a real voice call. The UI exists (Phase 04, 8 views, Speakify look) but was laid out desktop-first and shrunk for phones. The same site is also loaded inside the Android APK WebView (Phase 12). **Do not just make things smaller.** Reorganise for one-hand phone use.

## Box limits (hard)
EC2 with 2 GB RAM and 2 CPUs, almost no free memory. **Do not run `next build`, `next dev` with Turbopack for long, Playwright or the full test suite.** Allowed: `NODE_OPTIONS=--max-old-space-size=512 npx tsc --noEmit` and `npx eslint <your files>`, one at a time, each at most once per hour. Look at the existing 390 px screenshots in `prompts/phase-04-call-ui/evidence/` instead of rendering. Vercel builds the app.

## Goal
Phone-first layout with the same features, no feature loss on desktop, and an installable PWA.

## Deliverables
1. **Layout (CSS in `apps/web/src/features/call/app.module.css` and `apps/web/src/app/globals.css`, JSX in `features/call/**`)**
   - Use `100dvh`, `env(safe-area-inset-*)` and `viewport-fit=cover` (export `viewport` from `layout.tsx`, with `themeColor`).
   - Below 720 px: single column; **bottom tab bar** (Home, Practice, Progress) with ≥ 48 px targets, replacing any top nav; primary action pinned in a bottom sheet area within thumb reach.
   - **Call screen on phone:** big status text at top, coach/learner visual centred, controls in a bottom row: Mute, "Give me a moment", End (End is separate and confirm-guarded). Transcript collapses into a pull-up drawer so the call screen never scrolls.
   - **Setup on phone:** scenario, level, speaking language, coaching language as stacked full-width cards or a stepper, not a wide grid. Recording consent toggle stays visible, OFF by default.
   - Inputs ≥ 16 px font (no iOS zoom), no horizontal scroll at 360 px, tap targets ≥ 44 px, visible focus, `prefers-reduced-motion` kept.
   - Desktop (≥ 960 px) keeps the multi-column look; tablets sit between.
   - Keep every existing honesty rule: no scores, no filler counts, no "all 10 languages verified" copy. If a language flag is not validated in `catalog.json`, say "not yet checked" as today.
2. **PWA:** `apps/web/src/app/manifest.ts` (name, short_name, `display: "standalone"`, `start_url: "/"`, theme/background colour, icons 192/512 + maskable). Original icons in `apps/web/public/icons/` (simple SVG-derived PNG or SVG; the coach mark in the existing design; no third-party art). **No service worker** (it could cache authenticated responses; out of scope).
3. **Mobile microphone UX:** a pre-call mic check that explains the browser prompt in plain words and handles denied permission with a visible next step (open settings / retry). Works when the page is opened over https in a phone browser and inside an Android WebView (which asks Android for `RECORD_AUDIO`).
4. **Keep existing unit tests passing** by reading them; update only tests of the files you changed. Add at most 3 small tests (tab bar renders, call controls reachable, manifest fields).
5. Leave `next.config.ts` as is (Phase 07 CSP: `connect-src` already allows the voice URL; manifest and icons are same-origin so they pass).

## Criteria
- 360×740, 390×844, 768×1024, 1280×800: nothing clipped, no horizontal scroll, one obvious next action on each screen (review by reading CSS and the existing screenshots; **do not** launch a browser here).
- `tsc --noEmit` and eslint on touched files exit 0 (once each, at the end).
- No new dependency, no change to the frozen `CallExperience({catalog})` seam.

## Constraints
Search before any API use and cite the URL in a code comment or REPORT: Next.js `viewport` and `manifest` metadata (https://nextjs.org/docs/app/api-reference/functions/generate-viewport , https://nextjs.org/docs/app/api-reference/file-conventions/metadata/manifest), CSS `dvh` and `env(safe-area-inset-*)` (MDN). Do not invent versions from memory.

## Parallel rules (G2)
- First agent to start creates `prompts/parallel-G2/COMM.md` and `STATUS.md` if missing. COMM stub: `# G2 COMM` then entries. STATUS stub: header row `| Phase | State | Updated | Doing now | Need |` plus separator and one row per phase (10, 11, 12) with `NOT STARTED`.
- COMM.md: `## NN HH:MM — <≤25 words>` plus tag `INFO|HELP|DECISION|BLOCKED`. No code or logs; link REPORT. Author appends `RESOLVED: reason`. Keep < 60 lines.
- STATUS.md: update **only your row** at start, on state change, at finish. State `ACTIVE|BLOCKED|DONE`; Doing < 15 words.
- Read COMM + STATUS at start and before REPORT. Need a change in another phase's files: post `HELP:` and wait for a CEO FIX. Editing a sibling's files is 🔴.
- Blocked on a sibling for more than one cycle: write REPORT with a `BLOCKED BY:` section.
- STATUS/COMM stubs list rows 10, 11, 12, 14.

## Git (autonomous, user-authorized W08)
`git add` **only your OWN paths** (never `-A` or `.`), commit `phase-10: <what>`, `git pull --rebase origin main`, `git push origin main`. No force-push, no `.env*` except `*.example`, leave the pre-existing dirty files (`fixtures/synthetic/manifest.json`, phase-02 evidence) alone. Report the commit hash.

## REPORT.md (required; missing = NOT VERIFIED)
Files changed; commands run with raw output paths in `evidence/`; what you verified and how (by reading, by tsc/eslint); limits (no browser run here); help needed. End with `PHASE 10 BUILT` or `BLOCKED: reason`. Stop there.
