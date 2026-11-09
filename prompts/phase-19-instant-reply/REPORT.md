# Phase 19 — instant-reply (B6, NORMAL)

Status: **BUILT.** All voice/web checks below ran on a throw-away local
uvicorn at `127.0.0.1:8100`; the production `gnani-voice` unit was **not**
restarted or stopped and `/etc/gnani-coach/` was not edited. Phase 20 owns
the restart and the Vercel deploy.

## Cause of the 07:58 disconnect

`journalctl -u gnani-voice` around the call shows the socket opened at
07:58:07 and the server failed at 07:58:38 sending `status thinking`:

```
starlette.websockets.WebSocketDisconnected: Cannot call "send" once a close message has been sent.
```

The client had already sent its close. The call was **31.0 s** old, so the
browser's 45 s idle watchdog (`IDLE_TIMEOUT_MS = 45_000`) **could not have
fired**: that timer needs 45 s without a server message. The old code also
reported this as an internal failure (`call failed ...`), not as the client
going away. This phase adds both facts to the log:

* `_read_loop` records the disconnect code, and a `WebSocketDisconnected`
  on send is now handled as the client leaving (`closed_by=client`,
  `close_code=1006` because the close frame carried no usable code);
* every call ends with one content-free line:
  `call closed ... closed_by=... close_code=... elapsed_ms=...
  since_last_server_message_ms=... speculation_calls=...
  speculation_discarded=... backchannels=...`.

The next field test will therefore say whether the browser's idle timer,
the page/network, or the server closed the socket. The evidence from this
run is `evidence/journal_after.txt` (`closed_by=client close_code=1000`).

## A. Seeing first (applied)

* `conversation/logging_setup.py`, applied at import from
  `conversation/router.py`: one `INFO` handler on the `gnani_coach` family,
  level from `SPEAKING_COACH_LOG_LEVEL` (default `INFO`), stderr → journal.
  `main.py` is untouched. The `turn timings` line now appears; see
  `evidence/journal_after.txt`.
* Per-connection close logging as above, content-free (ids, code, ms).
* `evidence/before.txt` is the unmodified `HEAD` run of
  `tests/smoke/call_two_utterances.py` on the same throw-away server.

## B. What was applied

1. **Fast end of turn.** `FAST_TURN_HOLD_MS = 700` is used when the
   recogniser has a closed segment (or the turn already has one); the
   1200 ms hold is kept when nothing has been recognised, and a "Give me a
   moment" mute still keeps its extension. Gnani's conversation
   `x-min-silence-ms` default is **600** (documented conversation range
   600–900; https://docs.gnani.ai/api/STT/stt-websocket, VAD tuning, read
   2026-11-09). `x-min-speech-ms` and the threshold were not changed.
2. **Speculative reasoning.** When a live segment is closed and the learner
   has been silent ≥400 ms, one reasoning call starts on a **peek** of that
   text (`pending_text`), so the turn's own collect still sends the
   transcript exactly once. The reply is adopted only if the turn really
   completes; new speech cancels it and its output is discarded. At most
   one speculative call per turn; `speculation_calls` and
   `speculation_discarded` are logged per call. The passing run discarded
   **1**.
3. **Immediate acknowledgement.** Fixed phrases ("Mm-hmm.", "Okay.",
   "Right.", "I see.") are synthesised **once** per phrase into a
   process-wide PCM cache (bounded to 24 clips, ≤800 ms each) and warmed in
   the background as the call opens. Each filler is sent under its **own**
   `turnId` with `kind: "backchannel"`; it never uses the transcript, it
   rotates so the same phrase is not repeated twice in a row, and it is
   skipped when a speculative reply is already in hand. The client starts
   the real reply after the filler's audio ends, so the two do not overlap.
4. **Mid-sentence backchannels.** One cached "Mm-hmm." after a real
   endpointing pause of ≥500 ms, with ≥4 s of speech in the turn, at most
   once per 12 s, never in the first 3 s, dropped if the learner resumes
   within 150 ms. Behind `BACKCHANNEL_ENABLED` and
   `SPEAKING_COACH_BACKCHANNEL_ENABLED` (default on). English only: no
   other catalog language has a validated voice, so they fall back to
   English rather than an invented translation. "Continuous speech" is
   measured as speech in the turn, because any 32 ms inter-word gap resets
   a raw run and a raw-run test would never fire on real speech.
5. **Streaming reply.** The pinned `google-genai` 2.31.0 exposes
   `AsyncInteractions.create(..., stream=True)` returning
   `AsyncStream[InteractionSSEEvent]`; `step.delta` / `TextDelta.text`
   carries the pieces (checked in the installed package and at
   https://ai.google.dev/gemini-api/docs/interactions, read 2026-11-09).
   The runtime cuts at the first `. ? !`/danda boundary, starts Gnani TTS
   for that sentence immediately, and synthesises the rest while the first
   plays. Each sentence keeps the existing sanitising and length limits.
   If streaming raises before any sentence, the non-streaming `reply` path
   is used once; if it raises after audio started, the turn ends with the
   frozen error shape rather than replaying text.
6. **Smaller reply.** `max_output_tokens` 300 → **120**, `thinking_level`
   stays `low`, and both system instructions now require at most two short
   sentences and under 30 words. A model-only probe of the exact turn
   prompt measured **1.844 s** for the streamed reply and **0.866 s** for
   the non-streamed reply, so no alternative model is proposed.
7. **Client.** `audio.frame.descriptor` and `coach_text` carry the optional
   `kind`. The player treats a backchannel as low priority: it is dropped
   while the learner speaks or a real reply is playing, it never changes
   the main status, and the real reply starts after its audio ends.
   `onSpeechStart` stops backchannels without any message; the "You spoke
   over the coach" note is only for the real coach turn. `CallView` still
   shows `Listening` while the learner talks and the 8 s "Still working…"
   state and 45 s watchdog are unchanged.

## Before / after

Definitions:

* **(i) end of speech → first sound of any kind** — from the end of the
  synthetic long clip to the first binary frame after it (filler or reply).
* **(ii) end of speech → first word of the real reply** — the same, but the
  first binary whose descriptor has `kind: reply`.
* **(iii) longest gap between server messages** — the largest interval
  between any two server messages in the run.
* **speculation discarded** — the server's `speculation_discarded` counter.

| Measure | Before | After |
|---|---|---|
| (i) first sound of any kind | **4,748 ms** | **618 ms** |
| (ii) first word of the real reply | 4,748 ms (no filler existed) | **3,542 ms** |
| (iii) longest server-message gap | 9,642 ms | 9,806 ms |
| coach after the long turn | 1 | 1 |
| backchannels in the run | 0 | 2 |
| errors / early close | 0 / no | 0 / no |
| speculation discarded | n/a | **1** |

Raw: `evidence/before.txt`, `evidence/after.txt`,
`evidence/journal_after.txt`.

**Honest limit:** these are two turns from one run each, not a p50 over
n ≥ 5. The provider-turn budget was the binding constraint (see below), so
no p50 is claimed; the per-turn numbers above are the whole sample. The
longest-gap figure did not improve: it is dominated by the model turn, not
by the endpointing changes.

### Long monologue

`tests/smoke/long_monologue.py` streams a compacted synthetic clip with two
real 672 ms pauses (≥15 s of speech):

```
backchannel_count=2
mid_turn_backchannels=1
backchannels_during_speech=0
backchannels_in_first_3s=0
RESULT=PASS
```

Raw: `evidence/long_monologue.txt`. One backchannel is the mid-sentence
"Mm-hmm."; the other is the turn-close acknowledgement. The reaction at
8.89 s lands exactly as the learner resumes and is stopped by the client;
the test counts a reaction as "during speech" only when it is more than
150 ms into a loud run, which is the guard the phase specifies.

## Tests

| Check | Result | Raw |
|---|---|---|
| Conversation suite (from repo root) | **117 passed, 1 skipped** | — |
| Provider files touched (`gemini`, `stt`, `tts`, probes, budget) | **137 passed** | — |
| Foundation contract/privacy | **13 passed** | — |
| `call_two_utterances.py` | **PASS** | `evidence/after.txt` |
| `long_monologue.py` | **PASS** | `evidence/long_monologue.txt` |
| `call_once.py` (full) | **2 PASS / 1 FAIL** — H failed on a late segment | `evidence/call_once.txt` |
| `call_once.py --only h` after the fix | **PASS**, first sound 1,422 ms | `evidence/call_once_h.txt` |
| `tsc --noEmit` (`NODE_OPTIONS=--max-old-space-size=512`) | clean | — |
| `eslint` on the touched web files | clean | — |

The full `call_once` run exposed a real regression from the shorter hold:
the first collect could run just before the live recogniser published its
segment, leaving the turn waiting for speech that had already finished.
`_collect_segments` now retries twice (900 ms then 250 ms) before giving
up; the H scenario passes after that change.

New unit tests (5, all in `services/voice/tests/conversation/test_backchannel.py`):
backchannel off switch; filler has its own turn id and precedes the reply;
speculative reply adopted once; speculation discarded on new speech; first
sentence goes to TTS before the stream ends. The existing fenced-turn test
still covers late audio being dropped.

## Contract additions (diff)

Only the two fields the phase allows, plus the explanatory note:

```diff
 coachTextPayload:
+  "kind": { "enum": ["reply", "backchannel"], "default": "reply" }
 audioFrameDescriptor:
+  "kind": { "enum": ["reply", "backchannel"], "default": "reply" }
```

`docs/contracts/call-transport.md` §1 has the matching paragraph. No other
contract edit, no new event type, no change to ids, sequence, heartbeat or
caps. The client treats an absent `kind` as `reply`.

## Provider turns and limits

**Provider turns used: 20 reasoning calls (the cap).** TTS/STT calls are
not counted as "turns" (the smoke scripts define a provider turn as one
coach reply). The cap is reached, so no further live runs were made.

Limits of this evidence:

* synthetic TTS speech only, one network path (local uvicorn → live
  providers), not a phone and not a browser;
* the before/after sample is 2 turns each, so no p50;
* backchannel taste is subjective: the mid-turn window is narrow because a
  pause must be long enough for the 150 ms guard but shorter than the
  700 ms fast hold; longer pauses correctly become a new turn;
* the client playback behaviour is covered by `tsc` and the unit-tested
  reducer/transport, not by Playwright (not run, per the box limits).

Commit: `4efc3ee` (`phase-19: instant reply with backchannels and streaming`).

PHASE 19 BUILT — NEEDS RESTART OF gnani-voice AND A VERCEL DEPLOY
