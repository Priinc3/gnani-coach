# Evidence — Phase 04 (call-ui)

Every image in this folder was produced by `apps/web/tests/evidence/capture.spec.ts`
(with one exception, noted below) and every command log was produced by a real
run at the repo root.

> **These are fixture captures.**
> The voice service behind every capture is the fake one in
> `apps/web/tests/fakes/voice-server.ts`, which speaks the frozen event
> envelope of `docs/contracts/call-transport.md`, and the microphone is
> Chromium's fake device. A capture proves **what the interface does with a
> known event sequence**. It is **not** evidence that the real service behaves
> that way. B2's integrated test still has to prove the real service.

## How they were made

```
npx playwright test --config apps/web/tests/playwright.config.ts --project=evidence
```

The whole suite (unit + flow + evidence) is the same command without
`--project=evidence`; its raw output is in `commands/04-phase04-tests.txt`.

## The "before" captures

`before-stub-*.png` are the **only** images here that were **not** made by the
Phase 04 suite. They are the Phase 01 starter screen, captured from a
throwaway `git worktree` at commit `6805a30` ("Phase 01 foundation"), run on
port 3001 and then deleted. They show the ivory, serif "conversation studio"
look that `prompts/phase-04-call-ui/UI-REFERENCE.md` §1 supersedes. The
worktree has been removed; no file in the main working tree was changed to
produce them.

## The reference board

`../../../UI.png` (repo root, 1536 × 1024) is the user-supplied visual
reference. It is read-only input and is deliberately **not** copied into this
folder. Every intentional difference from it is listed in
`../REPORT.md` § "Intentional differences from the reference".

## Screenshot index

### Before (Phase 01 starter screen, commit `6805a30`)

| File | Width | What it shows |
|---|---|---|
| `before-stub-1440.png` | 1440 | The stub: serif heading, ivory canvas, one big setup panel, no coach illustration |
| `before-stub-1280.png` | 1280 | The same stub at the second desktop width |
| `before-stub-390.png` | 390 | The same stub at the first phone width |
| `before-stub-360.png` | 360 | The same stub at the narrowest phone width |

### Landing, scenarios, settings (implemented)

| File | Width | What it shows |
|---|---|---|
| `landing-1440.png` | 1440 | Landing: wordmark, compact nav, "Speak with confidence in real life" hierarchy, coach illustration, two CTAs, the ten documented languages |
| `landing-1280.png` | 1280 | The same landing at the second desktop width |
| `landing-390.png` | 390 | The same landing on a phone (single column) |
| `landing-360.png` | 360 | The same landing at the narrowest phone width |
| `scenarios-1440.png` | 1440 | Scenario browser: cards for every catalog scenario, presets under the workplace category |
| `scenarios-1280.png` | 1280 | The scenario browser at the second desktop width |
| `scenarios-390.png` | 390 | The scenario list on a phone |
| `scenarios-360.png` | 360 | The scenario list at the narrowest phone width |
| `settings-recording-off-1440.png` | 1440 | Settings: separate speaking/coaching language selectors, level, preset, recording **off** (default) |
| `settings-recording-off-1280.png` | 1280 | The same settings at the second desktop width |
| `settings-recording-off-390.png` | 390 | The same settings on a phone |
| `settings-recording-off-360.png` | 360 | The same settings at the narrowest phone width |
| `settings-recording-on-1440.png` | 1440 | Settings with the recording toggle **on** and the plain explanation of what is kept |
| `settings-recording-on-1280.png` | 1280 | The same, second desktop width |
| `settings-recording-on-390.png` | 390 | The same on a phone |
| `settings-recording-on-360.png` | 360 | The same at the narrowest phone width |

### Call (implemented)

| File | Width | What it shows |
|---|---|---|
| `call-listening-1440.png` | 1440 | The call screen, status **Listening**, timer, circular coach avatar, controls |
| `call-listening-1280.png` | 1280 | The same at the second desktop width |
| `call-listening-390.png` | 390 | The same on a phone |
| `call-listening-360.png` | 360 | The same at the narrowest phone width |
| `call-coach-speaking-1280.png` | 1280 | Status **Speaking** — the coach is talking |
| `call-coach-speaking-390.png` | 390 | The same on a phone |
| `call-interrupted-1280.png` | 1280 | **Interrupted**: the learner spoke over the coach, the audio stopped and the app says the request was *not* cancelled |
| `call-still-connecting-1280.png` | 1280 | **Connecting**, and the "still connecting to the coach…" notice after one second without a status |
| `call-reconnecting-1280.png` | 1280 | **Reconnecting** after the service dropped the connection |
| `call-error-1280.png` | 1280 | **Error** in plain words, with the retry rule of the error shape ("Try again in a moment. Nothing was saved.") |
| `call-mic-denied-1280.png` | 1280 | **Microphone denied** — the plain recovery state |

### Coaching break and summary (implemented)

| File | Width | What it shows |
|---|---|---|
| `coaching-break-1440.png` | 1440 | The coaching break: one strength, two improvements, a language note, and the evidence chips (including the filler chip in its insufficient-evidence state) |
| `coaching-break-1280.png` | 1280 | The same at the second desktop width |
| `coaching-break-390.png` | 390 | The same on a phone |
| `coaching-break-360.png` | 360 | The same at the narrowest phone width |
| `summary-1440.png` | 1440 | The session summary: the rounds, the metrics with their status, and no overall score |
| `summary-1280.png` | 1280 | The same at the second desktop width |
| `summary-390.png` | 390 | The same on a phone |
| `summary-360.png` | 360 | The same at the narrowest phone width |

### History (implemented)

| File | Width | What it shows |
|---|---|---|
| `history-empty-1440.png` | 1440 | **Empty history** — "No sessions yet" |
| `history-empty-1280.png` | 1280 | The same at the second desktop width |
| `history-empty-390.png` | 390 | The same on a phone |
| `history-empty-360.png` | 360 | The same at the narrowest phone width |
| `history-list-1280.png` | 1280 | A history with a real session in it, with the replay control (the recording fetch succeeded) |
| `history-guest-1280.png` | 1280 | **Guest state** — "Sign in to keep progress", not an error |
| `history-error-1280.png` | 1280 | **Plain error state** — "We could not load your progress" with a retry |

### States required by the brief

| Required state | Evidence |
|---|---|
| microphone denied | `call-mic-denied-1280.png` |
| connecting | `call-still-connecting-1280.png` |
| listening | `call-listening-{1440,1280,390,360}.png` |
| coach speaking | `call-coach-speaking-{1280,390}.png` |
| coaching break | `coaching-break-{1440,1280,390,360}.png` |
| interrupted | `call-interrupted-1280.png` |
| reconnect / error | `call-reconnecting-1280.png`, `call-error-1280.png` |
| insufficient evidence | the filler evidence chip inside `coaching-break-*.png` — "Counting filled pauses has not been validated" |
| empty history | `history-empty-{1440,1280,390,360}.png` |
| recording OFF | `settings-recording-off-{1440,1280,390,360}.png` |
| recording ON | `settings-recording-on-{1440,1280,390,360}.png` |

## Command logs

| File | Command | Result |
|---|---|---|
| `commands/01-lint.txt` | `npm run lint` | exit 0 |
| `commands/02-typecheck.txt` | `npm run typecheck` | exit 0 |
| `commands/03-build.txt` | `npm run build` | exit 0 |
| `commands/04-phase04-tests.txt` | `npx playwright test --config apps/web/tests/playwright.config.ts` | 77 passed, exit 0 |
| `commands/05-test-contracts.txt` | `npm run test:contracts` | PASS, exit 0 |
| `commands/06-test-integration-web.txt` | `npm run test:integration:web` | 3 failed, 2 passed, exit 1 — **not my file**, see `../REPORT.md` § HELP |
| `commands/07-test-e2e-foundation.txt` | `npm run test:e2e` | 10 failed, 2 passed, exit 1 — **not my file**, see `../REPORT.md` § HELP |
| `commands/08-secret-scan.txt` | `uv run --project services/voice python tools/probes/secret_scan.py` | 0 findings, exit 0 |
