# Phase 04 — call-ui (B2, PARALLEL:G1) — REPORT

**Phase:** 04 — browser side of the speaking coach (call UI, audio capture, transport, session UI).
**Group:** PARALLEL:G1 (B2). Siblings: 05 coaching-runtime, 06 private-history.
**Status:** built and verified against the frozen seams, fixture-proven only.
**Date:** 2026-10-20

**Inputs read:** `prompts/phase-04-call-ui/BUILD.md`, `prompts/phase-04-call-ui/UI-REFERENCE.md`,
`../../UI.png` (1536 × 1024, opened), `docs/contracts/seams.md`, `docs/contracts/call-transport.md`,
`docs/contracts/capability-states.md`, `prompts/parallel-G1/ADDENDUM.md` (§B–§H),
`packages/contracts/**` (schemas, catalog, capabilities).

---

## 1. What was built

`CallExperience({ catalog })` — the export in `apps/web/src/features/call/index.ts` is **unchanged** —
is now the real browser side of the product:

```
landing → scenarios → settings → call ⇄ coaching break → summary → history
```

Eight views in one client component (`apps/web/src/features/call/CallExperience.tsx`), a desktop top
nav and a mobile bottom nav, built from the tokens in `apps/web/src/app/globals.css`
(read-only; **not edited**).

Three libraries, all in Phase 04's own tree:

| Library | What it owns |
|---|---|
| `apps/web/src/lib/audio/**` | the microphone, the 16 kHz `s16le` worklet, the 1,024-byte frame packer, the coach's TTS playback |
| `apps/web/src/lib/transport/**` | the WebSocket client, the frozen envelope, connection/sequence/turn fencing, plain-word errors |
| `apps/web/src/lib/session-ui/**` | the call reducer, the settings→session-settings build, the metric wording, the history routes, the auth adapter, the hook that wires the three together |

### The frozen seam is intact

- `apps/web/src/features/call/index.ts` — unchanged export.
- `apps/web/src/app/page.tsx` — **not touched**; it still renders `CallExperience` and nothing else.
- `apps/web/src/lib/voice.ts` — **not touched**; `VOICE_WS_URL` is imported, never edited.
- `apps/web/src/lib/auth/**` — **not touched**; the three Phase 06 exports are read through the
  Phase 04 adapter `apps/web/src/lib/session-ui/accessToken.ts` (ADDENDUM §C).

---

## 2. Screen map: the 3 desktop areas and the 7 mobile screens

| Reference area (`UI-REFERENCE.md` §2) | Implemented view | File | Data source |
|---|---|---|---|
| **Desktop landing** | `LandingView` | `apps/web/src/features/call/views/LandingView.tsx` | `catalog.json` (languages, scenarios, levels) + `capabilities.json` for the honest capability strip; the coach illustration is the original inline SVG in `components/CoachAvatar.tsx` |
| **Desktop features** | `FeaturesView` | `apps/web/src/features/call/views/FeaturesView.tsx` | `packages/contracts/data/capabilities.json` (state + `renderedState` per capability) — only implemented/validated capabilities are advertised |
| **Desktop scenario browser** | `ScenariosView` | `apps/web/src/features/call/views/ScenariosView.tsx` | `catalog.json` scenarios with their presets; the custom-topic field from the catalog's `customTopic` contract |
| **1. Splash / onboarding** | `LandingView` (mobile, single column) | as above | same as the desktop landing |
| **2. Select scenario** | `ScenariosView` | as above | `catalog.json`; the chosen scenario carries into the settings screen through `state/settings.ts` |
| **3. Language & settings** | `SettingsView` | `apps/web/src/features/call/views/SettingsView.tsx` | `catalog.json` languages (with the four honest capability badges per language), `catalog.json` levels, the transient custom topic, and `state/settings.ts` for the recording/subtitles toggles |
| **4. Call / conversation** | `CallView` | `apps/web/src/features/call/views/CallView.tsx` | live `status` events only; the transcript and the coach's last line are transient reducer state |
| **5. Coaching break** | `CoachingView` | `apps/web/src/features/call/views/CoachingView.tsx` | the `round_feedback` event's `strengths[]`, `improvements[]`, `languageNotes[]` and `evidence[]`, each metric rendered through `lib/session-ui/feedback.ts` |
| **6. Session summary** | `SummaryView` | `apps/web/src/features/call/views/SummaryView.tsx` | the rounds the reducer kept for this session; the retry comparison through `compareAttempts()` |
| **7. Progress & history** | `HistoryView` | `apps/web/src/features/call/views/HistoryView.tsx` | `GET /api/history` (ADDENDUM §B) through `lib/session-ui/history.ts`; `GET`/`DELETE /api/recordings/{id}` for the replay and delete controls |

**Navigation.** Desktop: a compact top nav (Features · Scenarios · Progress · Languages). Mobile: a
persistent bottom nav (Home · Practice · Progress). The "Languages" nav entry scrolls to the language
list on the landing view, so it is never a dead link, and the features view is reachable from the
hero at every screen size (checked in `apps/web/tests/flow/a11y.spec.ts`).

---

## 3. Files changed (Phase 04's own tree only)

### Added — `apps/web/src/features/call/`

| File | Purpose |
|---|---|
| `CallExperience.tsx` | the view router, the navigation, the start/end/retry wiring |
| `app.module.css` | the Speakify-flavoured styles, built only from the tokens in `globals.css` |
| `index.ts` | **unchanged** — the frozen export |
| `components/CoachAvatar.tsx` | the original inline-SVG coach (see §8, asset gap) |
| `components/Icon.tsx` | the icon set (all icons have text labels beside them) |
| `state/settings.ts` | the learner's choices → the frozen session-settings shape, with validation |
| `state/capabilities.ts` | the capability register reader and its plain-word labels |
| `views/LandingView.tsx` | the landing / onboarding view |
| `views/FeaturesView.tsx` | the features view |
| `views/ScenariosView.tsx` | the scenario browser |
| `views/SettingsView.tsx` | the language and settings view |
| `views/CallView.tsx` | the call screen |
| `views/CoachingView.tsx` | the coaching break |
| `views/SummaryView.tsx` | the session summary |
| `views/HistoryView.tsx` | progress and history |

### Added — `apps/web/src/lib/audio/`

`constants.ts` (16 kHz / mono / s16le / 1,024 bytes), `capture-worklet.js` (the worklet itself),
`frames.ts` (the frame packer and the s16le writer), `level.ts` (the speech-onset detector used to
interrupt), `capture.ts` (getUserMedia + worklet + the plain-word microphone failures),
`playback.ts` (the per-turn TTS queue), `index.ts`.

### Added — `apps/web/src/lib/transport/`

`types.ts` (the frozen shapes, as types), `envelope.ts` (the only place an envelope is built +
the session-settings validation), `fencing.ts` (connection/sequence/turn fencing, pure),
`errors.ts` (every error category → plain words + the shape's retry rule), `client.ts` (the
WebSocket client), `index.ts`.

### Added — `apps/web/src/lib/session-ui/`

`callState.ts` (the pure reducer), `useCallSession.ts` (the hook), `feedback.ts` (the metric
wording and the retry comparison), `history.ts` (the four HTTP routes), `http.ts` (the HTTP base
URL derived from `VOICE_WS_URL`), `accessToken.ts` (the ADDENDUM §C adapter), `index.ts`.

### Added — `apps/web/tests/`

`playwright.config.ts` (unit / flow / evidence projects), `fakes/contracts.ts` (the Ajv validators
for every message and every fixture), `fakes/voice-server.ts` (the fake voice service),
`fakes/history-server.ts` (the fake history service),
`unit/{frames,worklet,fencing,client,settings,feedback,reducer}.spec.ts`,
`flow/{call-flow,a11y,privacy}.spec.ts`, `evidence/capture.spec.ts`.

### Added — the report and the evidence

`prompts/phase-04-call-ui/REPORT.md` (this file),
`prompts/phase-04-call-ui/evidence/**` (46 captures + `evidence/README.md` + `evidence/commands/**`).

### Not touched (verified with `git status`)

`apps/web/src/app/**`, `apps/web/src/lib/auth/**`, `apps/web/src/lib/voice.ts`,
`packages/contracts/**`, `services/voice/**`, `supabase/**`, `tests/integration/**`,
`tests/foundation/**`, `tools/**`, every manifest and lock, `UI.png`, the CEO prompts.

---

## 4. Commands and raw output

Every raw log is in `prompts/phase-04-call-ui/evidence/commands/`.

| # | Command | Result | Log |
|---|---|---|---|
| 1 | `npm run lint` | **exit 0**, no errors | `commands/01-lint.txt` |
| 2 | `npm run typecheck` | **exit 0** | `commands/02-typecheck.txt` |
| 3 | `npm run build` | **exit 0** — the app builds (Turbopack) | `commands/03-build.txt` |
| 4 | `npx playwright test --config apps/web/tests/playwright.config.ts` | **77 passed** (unit 49 · flow 23 · evidence 5), exit 0 | `commands/04-phase04-tests.txt` |
| 5 | `npm run test:contracts` | **PASS** — all contract examples and catalog invariants hold, exit 0 | `commands/05-test-contracts.txt` |
| 6 | `npm run test:integration:web` | **3 failed, 2 passed**, exit 1 — *not my file*, see §12 | `commands/06-test-integration-web.txt` |
| 7 | `npm run test:e2e` | **10 failed, 2 passed**, exit 1 — *not my file*, see §12 | `commands/07-test-e2e-foundation.txt` |
| 8 | `uv run --project services/voice python tools/probes/secret_scan.py` | **0 findings** (was 1, in my file — fixed, see §12.3) | `commands/08-secret-scan.txt` |

**Phase 04's own test command** (documented as the build requires):

```
npx playwright test --config apps/web/tests/playwright.config.ts
```

The evidence captures alone:

```
npx playwright test --config apps/web/tests/playwright.config.ts --project=evidence
```

Both use the existing `@playwright/test` 1.64.1 and Ajv from the workspace. **No dependency was
added**, no manifest or lock was touched, and `npm install`/`npm ci`/`uv sync` were not run.

### Test breakdown

- **unit (49)** — the frame packer (1,024 bytes, real-time cadence), the worklet (evaluated as the
  real file through `new Function` with a shimmed `AudioWorkletProcessor`: 48 kHz → 16 kHz, s16le
  little-endian, the level preserved, muting keeps the cadence), the fence (stale connection,
  duplicate sequence, fenced turn, stale turn), the transport client (`start` first, the token in
  the start event and never in the URL, binary frames only after the server's answer, the
  reconnect with a new connection), the settings reducer and the session-settings validation, the
  metric wording and the retry comparison, the call reducer.
- **flow (23)** — the whole flow end to end against the fake service, a double click on Start opening
  only one connection, the plain-word error and its retry rule, the retry opening a **new**
  connection, the disconnect/reconnect, the duplicate event, the four history states (list, empty,
  guest, error), the replay control appearing only when the fetch works, the delete confirmation,
  the a11y checks, and the privacy checks (the microphone is opened only after the gesture; nothing
  is written to `localStorage`, `sessionStorage` or a cookie).
- **evidence (5)** — the 46 captures.

### Message validation

Every message the client sends and every fixture the fake service emits is validated against
`packages/contracts/schemas/*.json` with Ajv, in `apps/web/tests/fakes/contracts.ts`. The flow test
`the whole flow: onboarding, scenario, settings, call, coaching break, summary` asserts
`validateEnvelope(start) === true` and reads the frozen field names back out of the `start` payload.

---

## 5. Screenshots index

The full index, with what each capture shows, is `prompts/phase-04-call-ui/evidence/README.md`.
Summary of the 46 captures in `prompts/phase-04-call-ui/evidence/`:

| Group | Files |
|---|---|
| **Before** (the Phase 01 stub at commit `6805a30`) | `before-stub-{1440,1280,390,360}.png` |
| **Landing** | `landing-{1440,1280,390,360}.png` |
| **Scenarios** | `scenarios-{1440,1280,390,360}.png` |
| **Settings, recording OFF** | `settings-recording-off-{1440,1280,390,360}.png` |
| **Settings, recording ON** | `settings-recording-on-{1440,1280,390,360}.png` |
| **Call — listening** | `call-listening-{1440,1280,390,360}.png` |
| **Call — coach speaking** | `call-coach-speaking-{1280,390}.png` |
| **Call — interrupted** | `call-interrupted-1280.png` |
| **Call — connecting** | `call-still-connecting-1280.png` |
| **Call — reconnecting** | `call-reconnecting-1280.png` |
| **Call — error** | `call-error-1280.png` |
| **Call — microphone denied** | `call-mic-denied-1280.png` |
| **Coaching break** | `coaching-break-{1440,1280,390,360}.png` |
| **Summary** | `summary-{1440,1280,390,360}.png` |
| **History — empty** | `history-empty-{1440,1280,390,360}.png` |
| **History — list** | `history-list-1280.png` |
| **History — guest** | `history-guest-1280.png` |
| **History — error** | `history-error-1280.png` |

**No horizontal overflow.** Every capture asserts
`document.documentElement.scrollWidth - document.documentElement.clientWidth <= 1` before the shot is
taken (`apps/web/tests/evidence/capture.spec.ts`), and the flow suite repeats the check on every
screen at all four widths (`apps/web/tests/flow/a11y.spec.ts`).

**Before / reference / implemented.** The "before" captures are the Phase 01 starter screen, taken
from a throwaway `git worktree` at `6805a30` run on port 3001 and then deleted — no file in the
working tree was changed to produce them. The reference is `../../UI.png`; it is read-only input and
is deliberately not copied into the evidence folder. §9 lists the intentional differences.

---

## 6. State evidence

| Required state | How it is proven | Where |
|---|---|---|
| microphone denied | `getUserMedia` rejects with `NotAllowedError` → "Your browser blocked the microphone. Allow it from the site settings, then start the call again." + a retry | `call-mic-denied-1280.png`; `apps/web/src/lib/audio/capture.ts` `describeMicFailure` |
| connecting | no `status` event yet → "Connecting…"; after one second → "Still connecting to the coach…" | `call-still-connecting-1280.png` |
| listening | the `status` event with `state: "listening"` | `call-listening-*.png` |
| coach speaking | the `status` event with `state: "speaking"` | `call-coach-speaking-{1280,390}.png` |
| coaching break | the `round_feedback` event | `coaching-break-*.png` |
| interrupted | the learner's speech start (local energy VAD) or a server transcript while the coach is speaking → `interrupt` + the turn fenced + the audio stopped | `call-interrupted-1280.png` |
| reconnect / error | the socket closed → "Reconnecting…"; a server `error` envelope → the plain-word error with the shape's retry rule | `call-reconnecting-1280.png`, `call-error-1280.png` |
| insufficient evidence | the `filler.count` chip is always the insufficient-evidence state: "Counting filled pauses has not been validated, so we do not report a number." — never a count, never `0` | inside `coaching-break-*.png`; `lib/session-ui/feedback.ts` |
| empty history | `{"sessions":[]}` → "No sessions yet" | `history-empty-*.png` |
| recording OFF / ON | the toggle is **off by default**; the plan line reads "recording not saved" / "recording kept for replay (audio only; transcripts stay transient)" | `settings-recording-off-*.png`, `settings-recording-on-*.png` |

**Every one of these is a fixture capture.** The voice service behind them is
`apps/web/tests/fakes/voice-server.ts` and the microphone is Chromium's fake device. They prove what
the interface does with a known event sequence; they are **not** evidence about the real service.

### The other states the brief lists, and how they are covered

| Requirement | Implementation | Where |
|---|---|---|
| Offline | `navigator.onLine === false` at start → "You are offline." + a retry | `lib/session-ui/useCallSession.ts`; `lib/transport/errors.ts` |
| Slow network (> 1 s without a status) | the status pill becomes "Still connecting to the coach…" after one second | `views/CallView.tsx` `describeStatus` |
| Double-click on Start | one connection only: a ref guard in `CallExperience.handleStart` **and** a `startedRef` guard in `useCallSession.start`; the flow test clicks twice in one task and asserts exactly one `start` envelope | `apps/web/tests/flow/call-flow.spec.ts` "a double click on Start opens only one connection" |
| Microphone taken by another app | `NotReadableError` / `TrackStartError` → "Another app is using your microphone right now. Close it, then start the call again." | `lib/audio/capture.ts` |
| Unsupported browser | no `isSecureContext`, no `getUserMedia`, no `AudioWorkletNode` → "This browser cannot run a live call." with **no** retry (the shape says it will not help) | `lib/audio/capture.ts` `isCaptureSupported`, `lib/transport/errors.ts` |
| Every error category | `CATEGORY_COPY` in `lib/transport/errors.ts` maps all eleven categories of the frozen error shape to a headline, a fallback message and a next step; the **retry rule comes from the shape** (`payload.retryable`), never from a client guess | `apps/web/tests/unit/…` |

---

## 7. The contract, and how it is met

### Transport (`docs/contracts/call-transport.md`)

- **`start` first.** `CallClient.start()` opens the socket and `sendStart()` sends the `start`
  envelope before anything else. The token travels in the `start` payload's `auth.token` — **never
  in the URL** (asserted in `apps/web/tests/unit/client.spec.ts`).
- **Every server event is handled**: `status`, `transcript_partial`, `transcript_final`,
  `coach_text`, `round_feedback`, `audio.frame.descriptor`, `error`, and the binary frames.
- **Connection fencing.** A reconnect calls `fence.beginNewConnection()`: the old `connectionId` is
  kept until the new one says hello, so a late event from the old connection is dropped.
- **Sequence fencing.** An event whose `sequence` is not greater than the last accepted one is
  dropped (duplicate and out-of-order).
- **Stale-turn drop.** A `coach_text` or a descriptor for a turn older than the current one is
  dropped; a turn the learner interrupted is fenced and never played.
- **Heartbeat / idle.** The client tracks the last message and the idle watchdog closes a dead
  connection after 45 s of silence so the bounded reconnect runs.
- **Bounded reconnect with a new connection.** Three attempts, 500/1,000/2,000 ms, and each attempt
  is a **new socket with a new `start`** — no duplicated turns, because the old connection's events
  are fenced out.
- **The 10-minute cap with a 9-minute warning.** `CALL_LIMIT_MS = 600 000`, `CALL_WARNING_MS` fires
  first; the warning is shown in a `role="status"` banner and the cap ends the call with
  `reason: "time_limit"`.
- **Controls.** `interrupt`, `mute`, `end`, `retry`, `coaching_choice` — each is a frozen envelope.

### Audio (`docs/contracts/call-transport.md` §4, ADDENDUM §D)

- `getUserMedia` with `echoCancellation`, `noiseSuppression` and `autoGainControl` — **requested,
  not guaranteed**, and the code says so.
- The worklet resamples to **16 kHz mono s16le** and emits **1,024-byte** frames at real-time
  cadence (32 ms of audio per frame). `start.audio.sampleRateHz` is `16000`.
- The resampler is a **box-filter average** when `inputRate / outputRate` is an integer (48 kHz →
  16 kHz) and **linear interpolation** otherwise.
- The worklet file lives in Phase 04's own tree and is loaded with
  `new URL("./capture-worklet.js", import.meta.url)` — the form Next.js documents for a static asset
  that lives next to the code (see the citation in §8).

### Playback

- The TTS chunks are queued **per `turnId`** and played in order.
- An interrupt or a new learner speech **stops the audio at once** and drops that turn's queue.
- Audio for a **fenced or stale** turn is never played (`Fence.isTurnFenced` + the current-turn
  check in `CallClient.handleBinary`).
- The app **never claims the provider request was cancelled**. The call screen says: *"You spoke
  over the coach, so the coach stopped. The request was not cancelled — it may still finish on the
  service."*
- **Binary frames carry no turn id.** They are attributed to the last accepted descriptor; if that
  descriptor was dropped as stale, the attribution is unchanged rather than guessed (documented in
  `lib/transport/client.ts`, asserted in `apps/web/tests/unit/client.spec.ts`).

### The coaching break and the summary

- `round_feedback` is rendered as ≤1 strength, ≤2 improvements and a language note, with an
  evidence chip per metric.
- **Every metric uses its own status.** `available` shows the number; `unavailable` and
  `insufficient_evidence` show plain words and **no number at all** — a missing measurement is
  never `0`.
- **Filler is always the insufficient-evidence state**, with the reason
  `filler_detection_unvalidated` (ADDENDUM §H). There is no filler count anywhere in the code.
- The three buttons: **Try again** (sends `retry` with the turn id), **Keep talking**
  (`coaching_choice: keep_talking`), **Skip the feedback** (`coaching_choice: skip_feedback`).
- **The retry comparison** shows only the metrics **both** attempts carry (the metric key *is* the
  definition), and a difference is computed only from two `available` values — and then it is
  labelled *"Estimated difference: …"*.
- **No overall score, no confidence %, no pronunciation grade, no "you improved by X %".** The flow
  test asserts the summary text contains no `n/100`, no "confidence" and no "pronunciation".

### The history (`ADDENDUM §B`)

- `GET /api/history` → a real list; `401` → the **guest** state ("Sign in to keep progress"), not
  an error; anything else → a plain error state with a retry.
- `GET /api/recordings/{id}` → the replay control appears **only** when the fetch works; a `404`
  (someone else's or missing — the service answers both identically) means **no replay control at
  all**, while the delete control stays.
- `DELETE /api/recordings/{id}` → behind a confirmation ("Delete this recording? It cannot be
  undone.").
- **No fake data anywhere.** An empty list is an empty list.

### Security and lifecycle

- No provider key and no Supabase secret is in the client code (the credential scan is at **0
  findings**).
- The transcripts are **only in memory** — the reducer holds them, and the `ended` action clears
  them. The privacy test asserts the learner's words appear in neither `localStorage`, nor
  `sessionStorage`, nor a cookie.
- Nothing is written to `localStorage` at all.
- No `dangerouslySetInnerHTML`; model text is rendered as text.
- The microphone starts **only on a user gesture** — the Start button (asserted by the privacy test).
- All tracks are stopped and the socket is closed on end, on route change and on unmount.

---

## 8. Asset gap

**There is no illustration asset in the repository.** `UI.png` is a design *board*, not an asset
pack, and `UI-REFERENCE.md` §4 forbids embedding its tiny text or its cards as production artwork.

What Phase 04 did instead: an **original, clearly intentional inline-SVG coach** —
`apps/web/src/features/call/components/CoachAvatar.tsx`. It is drawn in the component itself (a
geometric, friendly face with a headset), it uses only the tokens in `globals.css`, and it is
rendered large on the landing view and cropped into the circular avatar on the call and coaching
screens.

**This is a deliberate temporary treatment, not a finished visual match.** The gap is:

- no illustrated coach art matching the reference's character;
- no illustration asset pipeline (the brief's `assets/` directory with a supported import approach
  was not needed because no asset exists to import);
- no icon font or third-party icon set — the icons are original inline SVG in
  `components/Icon.tsx`;
- no web font was introduced, so the type is the platform sans with Indic fallbacks. That was a
  deliberate choice (no licensing question, no layout shift), not an oversight, but it means the
  reference's exact typeface is **not** reproduced.

### The worklet loading — the cited approach

The AudioWorklet module is loaded with:

```ts
const CAPTURE_WORKLET_URL = new URL("./capture-worklet.js", import.meta.url).toString();
```

- **Citation.** Next.js 16.4.2's own bundled documentation uses exactly this form for a static
  asset that lives next to the code:
  `node_modules/next/dist/docs/01-app/02-guides/progressive-web-apps.md` (line 160 and the
  JavaScript tab at line 241) —
  `navigator.serviceWorker.register(new URL('../lib/service-worker.js', import.meta.url), …)`.
  The file stays in Phase 04's own tree; no `public/` directory was added and no global style was
  edited.
- **Verified in this build.** `npm run build` (Turbopack) emits the worklet **raw** to
  `apps/web/.next/static/media/capture-worklet.185yn7pwipdh2.js` (6,028 bytes, comments intact),
  and the client chunk `apps/web/.next/static/chunks/3k3tewbaqh4dr.js` references that exact
  filename. The worklet therefore runs as a real `AudioWorkletGlobalScope` module, not as a
  bundled chunk.
- The worklet is also evaluated **as the real file** in `apps/web/tests/unit/worklet.spec.ts`
  (through `new Function` with a shimmed `AudioWorkletProcessor`/`registerProcessor`), so the
  resampler and the frame packer are tested against the file that actually ships.

---

## 9. Intentional differences from `UI.png` (`UI-REFERENCE.md` §3)

1. **The recording defaults OFF**, although the mockup shows it ON. Live processing and retained
   audio are two different things and are explained separately on the settings screen.
2. **The experience is hands free.** There is no "Tap to speak"; the call screen shows the genuine
   status and a mute control, not a push-to-talk button.
3. **No invented scores.** The pictured 78/100, confidence 82, pronunciation 80 and +28 % are not
   reproduced anywhere — there is no overall score, no confidence and no pronunciation grade, and a
   comparison is only computed from two available values and then labelled an estimate.
4. **No fake history.** The mockup's seven sessions and twelve hours are not reproduced; the app
   shows a real list or an honest empty state.
5. **Language claims follow the capability evidence.** The ten documented languages are listed with
   their native names and the honest "Not yet verified" badge; there is no "10+" claim, no French
   and no flags.
6. **The subtitles are transient.** The toggle shows the live transcript only, and it is cleared
   when the call ends; it is not consent to keep anything.
7. **No fabricated pricing or testimonials.** There is no pricing page and no "Watch demo" button —
   the two CTAs are "Start a practice call" and "See what is measured", and both lead somewhere
   real.
8. **The feedback cites actual observations.** Where the analysis cannot support a claim, the
   insufficient-evidence state is shown instead ("Counting filled pauses has not been validated…").

**Not reproduced from the picture:** the device frames and the phone mockups (the board is a design
board, not a page of seven phones — `UI-REFERENCE.md` §1), and the reference's serif display type
(§1 supersedes it with a bold sans-serif).

---

## 10. Accessibility checks

| Check | How | Where |
|---|---|---|
| Labels on icon-only buttons | every button has an accessible name (the audit fails on any button without one) | `apps/web/tests/flow/a11y.spec.ts` "every button has an accessible name" |
| Keyboard-complete flow | the whole flow — landing → scenarios → settings → call → end → summary — is completed with the keyboard alone | `a11y.spec.ts` "the flow is complete with the keyboard alone" |
| Visible focus | the computed `outline-style` is not `none` and the outline width is > 0 | `a11y.spec.ts` "the focus is visible on the controls" |
| `aria-live` for the status and the feedback | the status pill and the coach bubble are live regions; the flow test counts them | `a11y.spec.ts` "the status and the feedback are announced" |
| Reduced motion | with `prefers-reduced-motion: reduce` the decorative pulse does not animate | `a11y.spec.ts` "the reduced-motion preference is honoured" |
| Sufficient contrast | the palette is taken from the frozen tokens in `globals.css` (dark ink `#1f…` on near-white and white panels; the muted text is the `--ink-soft` token, not a lighter ad-hoc grey) | `apps/web/src/app/globals.css` (read-only) |
| Indic-script rendering | `हिन्दी` (`lang="hi-IN"`) and `தமிழ்` (`lang="ta-IN"`) are rendered with their own `lang`, and the test asserts a non-zero box for both | `a11y.spec.ts` "the Indic scripts are rendered with their own language" |
| No horizontal overflow | every screen at 1440 / 1280 / 390 / 360 | `a11y.spec.ts` + every evidence capture |
| The transcript is transient | the transcript control is gone after the call ends | `a11y.spec.ts` "the transcript is not kept after the call ends" |
| The coaching break is structured | the break uses a `role="tablist"` with `role="tabpanel"` sections | `views/CoachingView.tsx` |
| Errors are announced | every error block is `role="alert"` | `views/CallView.tsx`, `views/HistoryView.tsx` |

---

## 11. Deviations from the frozen contract

**None.** The envelope, the error shape, the session-settings shape, the audio format, the four
HTTP routes and the capability register are all used as frozen.

Two points where the contract leaves a choice, and the choice is documented in the code:

1. **"Give me a moment" maps to `mute {muted: true}`.** The contract has no dedicated pause event,
   and the mute control already carries exactly that semantics. The button says so on the screen:
   *"'Give me a moment' turns your microphone off, so the coach cannot hear you while you think. It
   is the same pause the mute control uses."* (`views/CallView.tsx`).
2. **A binary frame is attributed to the last accepted descriptor.** The binary frame carries no
   turn id, so there is nothing else to attribute it to; a dropped (stale) descriptor leaves the
   attribution unchanged rather than guessing at a new turn. Asserted in
   `apps/web/tests/unit/client.spec.ts`.

---

## 12. `HELP:` items

### 12.1 `npm run test:integration:web` — 3 failed, 2 passed (exit 1)

**`tests/integration/call-experience.spec.ts` is not my file** (Phase 03's). The exact failures:

**(a) `:17` — "the home page renders the CallExperience mount point"**

```
Error: expect(locator).toBeVisible() failed
Locator: getByRole('heading', { name: 'Practice speaking, not just studying.' })
Expected: visible
Timeout: 5000ms
Error: element(s) not found
```

The test asserts the **Phase 01 stub**: the heading "Practice speaking, not just studying.", a
**disabled** "Start live practice call" button, and the note "Live calling will be enabled after
speech-provider setup." Phase 04 replaced the stub with the real app, so the heading is gone, the
button is enabled (there is a real call behind it now) and the note is gone.

**HELP:** the three assertions target the placeholder screen. They should be re-pointed at the real
app (for example: the landing heading is present, and the start action is *enabled* and leads to
the scenario picker). The file is Phase 03's; I did not edit it.

**(b) `:59` — "the history seam answers not_available"**

```
Error: expect(received).toBe(expected) // Object.is equality
Expected: 503
Received: 401
```

`GET /api/history` now answers **401** (the guest case), because Phase 06 implemented the private
history routes. `ADDENDUM.md` §B pins `401` for "guest/no token", so the **service** is right and
the **test** is out of date.

**HELP:** the expectation should become `401` (and the body should be the frozen error shape).

**(c) `:68` — "the call socket sends the frozen error envelope and closes"**

```
Error: expect(received).toBe(expected) // Object.is equality
Expected: "error"
Received: "status"
```

The first message on `/ws/call` is now a `status` envelope (Phase 05's real runtime), not the
Phase 03 `error`/`not_available` placeholder. This is the same item Phase 05 already posted in
COMM entry 14.

**HELP:** the assertion should accept the real runtime's first message.

The two tests that pass are "the voice service answers /health" and "the web page requests no
microphone access" — the latter is now also covered by Phase 04's own suite.

### 12.2 `npm run test:e2e` — 10 failed, 2 passed (exit 1)

**`tests/foundation/starter-screen.spec.ts` is not my file** (Phase 01's). Every failure is an
assertion about the **Phase 01 stub screen**, which Phase 04 replaced:

| Test | The assertion that no longer holds |
|---|---|
| `shows the honest headline and no fake data visuals` | the heading "Practice speaking, not just studying." and the text "Foundation build" |
| `start call is visibly unavailable with a plain reason` | the *disabled* start button, the `aria-describedby="start-reason"` note, and "only one button in `main`" |
| `requests no microphone access on load, even after interaction` | the labels "What language do you want to practise?" and the status "practising Hindi" |
| `recording retention is off by default, explained, and keyboard-toggleable` | the label "Save the session recording for replay" and the status "recording not saved" / "recording would be kept for replay" |
| `practice language select is focusable, labeled, and updates the plan` | the labels "What language do you want to practise?" / "What language should the coach explain in?" and the status "practising Hindi" |
| `coaching language follows practice until changed manually` | the same two labels, and the status "coach explains in English" |
| `scenario radios are keyboard operable` | the radio names "Interview practice" / "Workplace conversations" and the status "Workplace conversations" |
| `sample preview is optional and clearly labeled` | the summary "Optional: see a sample coaching break" and the label "sample preview — no live AI or recording" |
| `layout does not overflow a 360px-wide screen` | the stub heading (the overflow check itself still passes) |
| `honours reduced-motion preference` | the class `.scenario-option` and its `transitionDuration` |

The two that pass are "lists all ten catalog languages with honest verification badges" and "does
not offer French or any french language code" — the landing view still lists all ten languages with
their native names and the honest badge, and still offers no French.

**Every one of these properties is covered by Phase 04's own suite:**

| Phase 01 property | Where it is covered now |
|---|---|
| no microphone access on load | `apps/web/tests/flow/privacy.spec.ts` "the microphone is opened only after the learner asks for the call" — the count is 0 after reading the landing, the scenarios and the settings |
| recording off by default, explained, keyboard-toggleable | `apps/web/tests/flow/call-flow.spec.ts` (the checkbox starts unchecked and the plan line says "recording not saved") |
| the coaching language follows the practice language until it is chosen | `apps/web/tests/unit/settings.spec.ts` "the coaching language follows the speaking language until it is chosen", and the flow test |
| the scenario choices carry into the settings | the flow test asserts `scenarioId` and `scenarioPresetId` in the `start` payload |
| keyboard operability | `apps/web/tests/flow/a11y.spec.ts` (the whole flow with the keyboard alone, and the visible focus) |
| reduced motion | `apps/web/tests/flow/a11y.spec.ts` |
| no overflow at 360 px | `apps/web/tests/flow/a11y.spec.ts` and every evidence capture |
| the ten languages with honest badges | the landing view; the Phase 01 test still passes |

**HELP:** `tests/foundation/**` should be re-pointed at the real app, or retired in favour of
`apps/web/tests/**`. I did not edit it — it is Phase 01's file.

### 12.3 The credential scan

COMM entry 16 reported one `GENERIC_SECRET` at `apps/web/tests/unit/client.spec.ts:238` — a
deliberate dummy token in a test. **Fixed**: the line now carries the scanner's own documented
inline marker (`// secret-scan: allow`), and the scan is back to **0 findings**:

```
credential scan: 0 findings
  scope: repository working tree, structural rules only
```

---

## 13. Limits — what is only fixture-proven

- **Every capture and every flow test runs against the fake voice service**
  (`apps/web/tests/fakes/voice-server.ts`) and Chromium's fake microphone. They prove the browser
  side behaves as the contract says; they say **nothing** about the real service. B2's integrated
  test must prove the real behaviour.
- **The real service was never called.** No provider was contacted, no credential was read, no
  live provider call was made from Phase 04 (ADDENDUM §H).
- **The history captures are fixture captures too.** The fake history service answers the four
  ADDENDUM §B routes. The real routes are Phase 06's, and the guest/list/error states were proved
  against the fake.
- **The access token was never a real token.** The adapter resolves `getAccessToken()` when Phase 06
  publishes it; the tests use a dummy string. That the real token reaches the service through the
  `start` event is a Phase 05/06 integration fact.
- **The audio is silence.** The fake service's TTS chunks are zeroed PCM, so the **playback order
  and the interruption** are proved, but not the audible quality. The 48 kHz → 16 kHz resampler and
  the s16le byte order are proved against the real worklet file, with a generated signal.
- **The nine-minute warning and the ten-minute cap are proved by the unit test on the timers, not
  by waiting ten minutes in a browser.**
- **The recording is not proved end to end.** The toggle, the consent, the `start` payload's
  `recordingRetention` and `consent` flags, and the history's replay control are all proved; whether
  the service actually writes a file is Phase 05/06's job.
- **Visual similarity to `UI.png` is not verified.** There is no illustration asset, so the coach is
  an original inline SVG (§8). The layout, the palette, the hierarchy and the responsiveness were
  checked; the character art is a stated gap.
- **Only Chromium was exercised.** The Playwright projects use Chromium with a fake microphone. No
  Safari or Firefox run was made; the AudioWorklet path is standard, but the claim "works in
  Safari" is not proved here.
- **One browser, one service, one language set.** The Indic-script check covers a Hindi and a Tamil
  string; the other eight catalog languages were not rendered in a capture.

---

## 14. Comm and status

- `prompts/parallel-G1/COMM.md` — my entries are 11, 12 and 13; entry 18 records the completed build.
- `prompts/parallel-G1/STATUS.md` — row **04** is set to **DONE**.

---

PHASE 04 BUILT — AWAITING B2 TEST
