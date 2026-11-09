# Phase 17 — simple-ui (G3)

## Words per screen (before → after)

Counts are visible words from the JSX strings, including buttons and the
bottom tab bar, excluding the learner's own transcript. "Before" is the
Phase 04/10 screen; "after" is this build.

| Screen | Before (approx.) | After | Budget |
|---|---|---|---|
| Landing | ~300 | 12 | 25 |
| Pick (scenario + language) | ~120 | 39 | 40 |
| Call | ~60 static | 5 | 12 |
| Summary | ~200 | 18 | 40 |
| Progress (empty) | ~120 | 11 | 25 |
| Settings (guest) | ~250 | 27 | 40 |

The budgets are asserted at 390×844 in
`apps/web/tests/flow/word-budget.spec.ts` (written, not run here).

What was removed: the stats row, hero paragraph, the "what is measured"
page and its nav entry (`FeaturesView.tsx` deleted), repeated privacy
paragraphs, coach-detail blocks, the long field help, the language list,
the evidence chips and the comparison panels. Presets, coaching language
and level are behind one `More` disclosure.

What was kept, one short line each:

- `Your voice is sent to our speech partners to reply.` on the Pick screen.
- `Recording off unless enabled.` on Pick, and `Off unless you turn it on.`
  next to the Settings toggle.
- `Not yet checked` badge on every language that is not conversation-tested.
- Plain-word errors with one action (`Try again`, `Allow microphone`).
- No scores, no filler counts, no "all languages verified", no
  "end-to-end encrypted", no confidence numbers.

## Slow server

- The call status is one of Connecting, Listening, Thinking, Speaking,
  Reconnecting.
- `useCallSession` tracks the time since the last server event and the
  reducer exposes `msSinceEvent`. After 8 s the status becomes
  `Still working…`; End is never disabled.
- `useCallSession` computes a throttled RMS level from the captured frames
  (10 times a second) and the avatar has a `micRing` that scales and fades
  with it.
- Transcript lines arrive in the drawer. The main screen shows only the
  last coach line, clamped to two lines.
- `apps/web/src/lib/transport/client.ts` was not changed; the 45 s idle
  watchdog is untouched.

## Android WebView fit

- `layout.tsx`: `viewportFit: "cover"` and
  `interactiveWidget: "resizes-content"` (Next 16.4.2 types the value;
  Next docs `generate-viewport`).
- CSS uses both `env(safe-area-inset-*)` and Capacitor's injected
  `var(--safe-area-inset-*)` through `max(...)` for top, bottom, left and
  right. Bottom controls, the tab bar, the transcript drawer and the
  confirm sheet all include the bottom inset.
- `app.module.css`: `min-height: 100dvh`, no fixed `height: 100dvh` on the
  phone call screen, no horizontal overflow at 360 px (single-column
  scenario grid below 380 px), `touch-action: manipulation`, transparent
  tap highlight, `user-select: none` on controls, and 48 px targets.
- `apps/mobile/capacitor.config.ts`: `backgroundColor: "#f7f6f2"` and
  `plugins.SystemBars: { insetsHandling: "css", style: "DEFAULT",
  hidden: false }`. `SystemBars` is bundled with `@capacitor/core` 8.6.0
  (`node_modules/@capacitor/core/system-bars.md`).
- `MainActivity.java`: `EdgeToEdge.enable(this)` in `onCreate`, as the
  Capacitor 8 SystemBars doc asks when `insetsHandling` is not `disable`.
- `styles.xml` / new `colors.xml`: status and navigation bars use the app
  canvas `#f7f6f2` with dark icons (`windowLightStatusBar`,
  `windowLightNavigationBar`); the window background matches.
- `AndroidManifest.xml`: `android:windowSoftInputMode="adjustResize"` added.
  Permissions are unchanged:

```
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />
```

- The offline pages in `apps/mobile/www` use `100dvh` and the same safe-area
  padding.

**APK rebuild required:** native files changed. Run:

```
bash scripts/mobile/build-apk.sh
```

## Files changed

- `apps/web/src/app/layout.tsx`
- `apps/web/src/features/call/CallExperience.tsx`
- `apps/web/src/features/call/app.module.css`
- `apps/web/src/features/call/components/{AccountSection,Icon,SignInEntry}.tsx`
- `apps/web/src/features/call/views/{Call,Coaching,History,Landing,Scenarios,Settings,Summary}View.tsx`
- `apps/web/src/features/call/views/FeaturesView.tsx` (deleted)
- `apps/web/src/lib/session-ui/{callState,useCallSession}.ts`
- `apps/web/tests/flow/{word-budget,a11y,call-flow,mobile-ui,privacy}.spec.ts`
- `apps/web/tests/evidence/capture.spec.ts`
- `apps/mobile/capacitor.config.ts`
- `apps/mobile/www/{index,error}.html`
- `apps/mobile/android/app/src/main/AndroidManifest.xml`
- `apps/mobile/android/app/src/main/java/com/gnanicoach/app/MainActivity.java`
- `apps/mobile/android/app/src/main/res/values/{styles,colors}.xml`

## Verified by reading

- Next.js viewport docs in `node_modules/next/dist/docs/.../generate-viewport.md`
  and the `interactiveWidget` type in
  `next/dist/lib/metadata/types/extra-types.d.ts`.
- Capacitor 8.6.0 `node_modules/@capacitor/core/system-bars.md` for
  `insetsHandling: "css"`, `style`, `hidden`, and `EdgeToEdge.enable`.
- MDN `env()` and `dvh` behaviour for the safe-area `max()` fallback.
- Existing 390 px captures in `prompts/phase-04-call-ui/evidence/` for the
  visual language; the illustration, avatar and palette are unchanged.
- `NODE_OPTIONS=--max-old-space-size=512 npx tsc --noEmit` exited 0.
- `npx eslint` on every touched TS/TSX file exited 0.

## Limits

No browser, no device and no Gradle run happened here. The word-budget and
flow specs are written for the user or CI to run. If the Android layout is
still off, send **one screenshot of the Pick screen and the Call screen**
plus the phone model — not a description.

## Commit

Commit hash: `5215224`.

PHASE 17 BUILT
