# Phase 16 — voice-listening (B5, PARALLEL:G3)

You are Phase 16 (G3). **Siblings running now:** [17 simple-ui: `apps/web/src/**`, `apps/web/public/**`, `apps/web/tests/**`, `apps/mobile/capacitor.config.ts`, `apps/mobile/www/**`, `apps/mobile/android/app/src/main/{res,java}/**`].
Your OWN files: `services/voice/src/gnani_coach/conversation/**`, `services/voice/src/gnani_coach/providers/stt.py`, `services/voice/src/gnani_coach/ports/provider_adapters.py`, `services/voice/tests/conversation/**`, `services/voice/tests/providers/**`, `tests/smoke/**`, your `prompts/phase-16-voice-listening/REPORT.md` + `evidence/`.
DO NOT TOUCH: `apps/**`, `deploy/**`, `scripts/**`, `.github/**`, `packages/**` (frozen contracts), `docs/contracts/**`, other `services/voice/**` (identity, persistence, settings, main), CEO files.
Shared read-only: `docs/contracts/call-transport.md` (event names and status values are frozen; a new event or status = `HELP:` to the CEO, never a silent change).
Comm folder: `prompts/parallel-G3/`.

## Context
Goal (`prompts/00-plan.md` §10 and §11): a learner talks naturally on the web app or the APK and the coach hears **everything**, replies fast, and the call never stalls.

**The bug (user report, 2026-11-09):** on a real phone the learner spoke a longer answer, the app "only captured the hello", the rest never appeared, and the call died. Server log of that call (content-free):

```
06:52:03  WebSocket /ws/call [accepted]
06:52:55  call failed ... starlette.websockets.WebSocketDisconnect
          at conversation/runtime.py:749 in _maybe_finish_turn -> self._send("transcript_final", ...)
          "error envelope could not be sent"
```
52 s after opening, the **client** was already gone when the server tried to send. The web client closes a socket that received nothing for `IDLE_TIMEOUT_MS = 45_000` (`apps/web/src/lib/transport/client.ts:58,465-477`).

**CEO's reading of the code (a hypothesis, prove it first):**
1. `runtime.py:_on_frame -> _maybe_finish_turn` awaits `stream.collect()` **inline in the single main loop** (`runtime.py:631-691`, `715-765`). `collect()` replays the whole pending clip to Gnani **at real-time pace** (1 s of audio takes 1 s), then +800 ms trailing silence, then +1.5 s idle grace (`recognition.py:122-161`, `providers/stt.py:535-646`). While it runs, the loop reads no frames and sends **no heartbeat** (`_on_timeout`, every 15 s, is never reached). Audio keeps arriving; the 256-event queue (~8 s) fills; the reader blocks. After 45 s without a server message the browser hangs up.
2. A turn needs `min_words = 3` (`turns.py:216`). "Hello" is 1 word, so the turn stays open and the same cost is paid again on the next hold.
3. The pending buffer includes the leading silence from the moment the call starts, and every submission opens a **new** Gnani socket (a `CancelledError("session is closed")` retry path in `collect()`), so each turn pays connect + replay time. The per-call ceiling is 24 submissions (`config.py:96`).
4. Measured on 2026-11-07 with a 3 s clip: 9.7–16.4 s from end of speech to first coach audio (waiver W09).

## Box limits (hard)
2 GB RAM, ~150 MB free. The voice service runs here under systemd (`gnani-voice`, `MemoryMax=600M`). **Do not restart or stop it yourself and do not edit `/etc/gnani-coach/`.** Run tests with `nice -n 15`, only the files you touch, one process at a time, never the full suite. Live provider spend: **at most 14 provider turns in total** (report the count). Synthetic speech only, no real personal data, never print transcripts or audio.

## Deliverables (in this order)

### A. Prove the cause (before changing code)
1. Add content-free stage timing to the call path: per turn, log (INFO, numbers only) `frames_buffered`, `pending_audio_ms`, `stt_collect_ms`, `stt_connect_ms`, `llm_ms`, `tts_first_byte_ms`, `queue_depth_max`, `loop_blocked_ms_max`. Never log text.
2. `tests/smoke/call_two_utterances.py`: a scripted live call (same transport as `tests/smoke/call_once.py`) that sends, **in real time**: "Hello." → 2 s of silence → a **long** second utterance (8–12 s, several sentences, generate once with the live TTS and keep it under `fixtures/synthetic/audio/`, git-ignored is fine) → 3 s of silence. Print only event types, per-event arrival times relative to start, number of `transcript_final` events, `coach_text` count, longest gap between **any** two server messages, success/fail.
3. Run it **once against a local, throw-away uvicorn on a free port you start yourself** (`127.0.0.1:8100`, your own env with the existing keys inherited from `/etc/gnani-coach/voice.env` read via `sudo -n` into the process environment only, never written anywhere; if you cannot, run it against the live service and say so). Save the output in `evidence/before.txt`. Confirm or refute each of points 1–3 above with numbers. If the hypothesis is wrong, say what the numbers show instead and fix that.

### B. Fix the cause
Minimal, in this order of preference; stop when the acceptance criteria pass:
1. **Never block the main loop on the recogniser.** Run `collect()` in a background task per turn; the loop keeps reading frames, keeps the heartbeat, and keeps endpointing. Keep one in-flight submission at a time and fence it when the learner starts speaking again or on interrupt. A failed or late result must not complete a fenced turn.
2. **Send a status within 1 s of end of speech** using an **existing** status value (check `docs/contracts/call-transport.md`; e.g. `thinking`), and keep the heartbeat while waiting, so the browser never sees 15 s of silence.
3. **Do not submit silence.** Skip the leading/idle silence in the pending buffer (trim to the first speech frame minus a short pre-roll) and do not submit a clip with no speech frame. This removes the empty first submission and cuts replay time.
4. **Do not make a short answer wait for the word count.** "Hello" is a valid learner turn: keep `min_words` for coaching **rounds**, but let a turn that ended with a closed segment move the conversation on (the coach may answer briefly). If the `turns.py` rule is frozen by a test, change the test only with an explanation in REPORT.
5. **Reuse the Gnani connection across submissions in the same call** instead of opening one per clip, or, if reuse is not safe with the provider's `stream-complete` close, say so with the evidence and keep the reconnect but measure it.
6. If the above still leaves end-of-speech → first audio over 6 s, send the clip at faster-than-real-time **only if** the provider docs allow it. The docs say frames "must be sent at real-time cadence … do not buffer and burst; this degrades VAD accuracy" (https://docs.gnani.ai/api/STT/stt-websocket, "Sending rules"), so **do not burst**. The compliant speed-up is streaming frames to Gnani **while the learner is still speaking** (live pump, then `commit` control frame `{"type":"commit"}` at end of turn, documented on the same page) so no replay is needed. Do this only if A shows replay is the dominant cost, and keep it behind a clean seam so it can be reverted in one commit.

### C. Verify
- `before.txt` vs `after.txt` from `call_two_utterances.py`: both `transcript_final` events present, the long utterance transcribed, **longest gap between server messages ≤ 15 s**, no disconnect, and end-of-speech → first coach audio reported with its definition (p50 of the runs you made; do not claim p95).
- Existing unit tests for files you touched pass (`nice -n 15 services/voice/.venv/bin/python -m pytest <those files> -q -x -p no:cacheprovider`). Add at most 4 small tests: loop keeps reading and heartbeats while a slow fake recogniser runs; silence-only clip is not submitted; a one-word turn advances; a fenced result is dropped.
- Repeat `tests/smoke/call_once.py` once (regression).

## Constraints
Frozen contracts stay frozen. No new dependency. No secret in code, logs or evidence. Search before relying on any provider behaviour and cite the URL in a comment (Gnani STT page above; Gnani TTS https://docs.gnani.ai/api/TTS/tts-websocket). Untrusted audio and transcripts: no content in logs.

## Parallel rules (G3)
- First agent to start creates `prompts/parallel-G3/COMM.md` and `STATUS.md` if missing (stubs: `# G3 COMM`; STATUS header `| Phase | State | Updated | Doing now | Need |`, separator, rows 16 and 17 as `NOT STARTED`). **Re-read the file before every write and change only your own row/entry** (G2 had one overwrite).
- COMM.md: `## NN HH:MM — <≤25 words>` + `INFO|HELP|DECISION|BLOCKED`. STATUS: update only your row; `ACTIVE|BLOCKED|DONE`; Doing < 15 words.
- A needed change in a sibling's files, or a transport-contract change: `HELP:` and wait for the CEO. Editing a sibling's files is 🔴.

## Git (autonomous, user-authorized W08)
`git add` only your own paths (never `-A` or `.`), commit `phase-16: <what>`, `git pull --rebase origin main`, `git push origin main`. No force-push, no `.env*`. Leave the pre-existing dirty files alone.

## REPORT.md (required)
Cause confirmed or refuted with numbers; files and line ranges changed; before/after; provider turns used; limits (synthetic speech, one network path, not a phone); commit hash. Do **not** restart the production service: end with `PHASE 16 BUILT — NEEDS RESTART OF gnani-voice` (Phase 18 restarts it). Stop there.
