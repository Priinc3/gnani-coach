# Phase 16 — voice-listening (B5, PARALLEL:G3)

Status: **built, verified on a local throw-away server. The production
`gnani-voice` service was not restarted** (Phase 18 owns that).

## Cause — confirmed with numbers

All timings below are from `tests/smoke/call_two_utterances.py`, which sends
a synthetic "Hello." (0.64 s), 2 s of silence, a 9.12 s synthetic long
utterance, and 3 s of silence at real time. Only event types, counts and
durations are printed; no transcript, audio or token appears in the
evidence.

**1. The main loop blocked on `collect()` — confirmed.**
`before.txt` (unmodified `HEAD` in a detached worktree, local uvicorn
`:8100`):

| Measure | Before |
|---|---|
| Longest gap between any two server messages | **20,883 ms** |
| End of long speech → first coach audio | **18,300 ms** |
| Long transcript arrival after end of speech | ~16.0 s |
| `transcript_final` count / long transcript chars | 2 / 191 |
| Heartbeats during the wait | none |

The browser closes a socket after 45 s with no message
(`apps/web/src/lib/transport/client.ts`). The 20.9 s silent gap is the
inline `stream.collect()` replay: the loop read no frames, ran no
endpointing and sent no heartbeat until the replay finished. The reported
52 s call is this same mechanism with a longer clip or a turn that stayed
open for the word count.

**2. A one-word answer never advanced the conversation — confirmed.**
Before the fix the "Hello." transcript arrived at +7.29 s, but no
`thinking`, `coach_text` or `listening` followed it: the turn stayed open
because `min_words = 3`, and the long utterance was merged into the same
turn (the next server event was the long transcript at +28.18 s). After
the fix, the one-word turn advances (unit test
`test_a_one_word_turn_advances_the_conversation`, and the live run shows
`status thinking` 1.7 s after "Hello." ends).

**3. Leading silence, replay and a reconnect per submission — confirmed.**
With the minimal loop fix but before the live pump
(`after-clip-path-run2.txt` / `after-timings.txt`):

```
pending_audio_ms=10144  stt_collect_ms=13891  stt_connect_ms=128
```

A 9.12 s clip produced a 10.14 s pending buffer (trailing/hold silence
included), a 13.9 s collect (≈ replay + 0.8 s trailing silence + 1.5 s
idle grace), and a 128 ms reconnect: `GnaniSttSession.stream_pcm` closes
the socket with `stream-complete` after every submission, so the
`CancelledError("session is closed")` path opened a new one. Leading
silence is now trimmed to a 96 ms pre-roll and a clip with no speech frame
is never submitted (`recognition.py`).

**4. Replay was the dominant cost — confirmed, so B6 was implemented.**
Before: 18.3 s end-of-speech → first audio. After the live pump: 4.4 s
and 8.9 s in the two final runs; `stt_collect_ms` fell from 13,891 ms to
900–901 ms and `stt_connect_ms` to 0 (one Gnani socket reused for the
whole call). The remaining latency is the model (1.9–6.5 s), not the
recogniser. The live pump sends each 32 ms frame at real-time cadence
while the learner speaks, as the provider requires
(https://docs.gnani.ai/api/STT/stt-websocket, "Sending rules"); it never
bursts a buffered clip. It is behind one constant,
`LIVE_PUMP_ENABLED` in `recognition.py`, so it reverts in one line.

## Files changed (line ranges are the final file)

| File | What changed |
|---|---|
| `services/voice/src/gnani_coach/conversation/runtime.py` | `_TurnTiming` (249–260); background collect state (303–320); main loop timing + heartbeat deadline (647–690); frame epoch/fencing (700–760); `_maybe_finish_turn` starts `_collect_turn` off-loop (789–900); llm/tts timings (1042–1125); per-turn content-free log (1099–1125); collect task cancelled on shutdown. |
| `services/voice/src/gnani_coach/conversation/recognition.py` | `LIVE_PUMP_ENABLED` (67–70); pre-roll and no-speech skip (120–230); live forward + pacing (`_push_live`, 190–216); live `collect` (232–260); `_is_speech_frame` (363–380). |
| `services/voice/src/gnani_coach/conversation/turns.py` | `turn_is_complete(..., closed_segment=...)` (202–226): a closed segment advances a turn even when it is one word. |
| `services/voice/src/gnani_coach/providers/stt.py` | `last_connect_ms` (309, 382); live pump `start_live` / `send_live_frame` / `collect_live` (568–640). The clip path is unchanged. |
| `services/voice/src/gnani_coach/ports/provider_adapters.py` | `last_connect_ms` and live-pump pass-through (49–93). |
| `services/voice/tests/conversation/phase05_support.py` | Optional slow fake recogniser (`delay`). |
| `services/voice/tests/conversation/test_turns.py` | One-word turn advances; slow recogniser keeps the loop reading and heartbeating; fenced result is dropped. The old `test_a_turn_with_too_few_words_stays_open` is replaced because Phase 16 deliberately changes that rule: the word count still governs a coaching round, but a closed segment is a learner turn. |
| `services/voice/tests/conversation/test_recognition.py` | Silence-only clip is not submitted; leading silence is trimmed to the pre-roll. |
| `tests/smoke/call_two_utterances.py` | New scripted live call; prints event types, arrival times, counts and gaps only. |
| `tests/smoke/call_once.py` | Optional `--url` / `--origin` so the regression can run against the local throw-away server without changing the deployed defaults. |

No frozen contract changed: no new event, status, payload key or
dependency. The only statuses sent are the existing `thinking`,
`listening`, `speaking`, `heartbeat` and `ended`.

## Before / after

`before.txt` vs the final `after.txt` / `after-run2.txt`:

| Measure | Before | After run 1 | After run 2 |
|---|---|---|---|
| `transcript_final` count | 2 | 2 | 2 |
| Long transcript chars | 191 | 191 | 191 |
| Coach line after the long turn | 1 | 1 | 1 |
| Longest gap between server messages | **20,883 ms** | **10,354 ms** | **6,543 ms** |
| End of long speech → first coach audio | **18,300 ms** | **4,416 ms** | **8,882 ms** |
| Socket disconnected early | no | no | no |
| Errors | 0 | 0 | 0 |

**p50 of the two final runs = 6.65 s** (with n = 2 this is their mean;
the definition is the end of the last learner audio frame of the long
utterance to the first coach audio byte). Both `transcript_final` events
are present, the long utterance is transcribed, the longest gap is under
15 s, and there is no disconnect. The intermediate clip-path runs
(`after-clip-path*.txt`) show the same pass with a 13.9 s gap and 18.6 s
first audio; they are kept to show the replay cost the live pump removed.

Regression `tests/smoke/call_once.py` against the same local server:
`SUMMARY pass=3 fail=0`, first audio 3,708 ms for one real turn and
6,188 ms after a dropped socket (`regression-call_once.txt`).

## Provider spend

Live provider turns used: **8 coach/reasoning turns** (the definition
`call_once.py` reports), within the 14-turn allowance. For transparency:
4 TTS calls to generate the two fixtures (2 attempts), 11 STT
submissions/connections and 12 TTS synthesis calls across all before,
after and regression runs. Synthetic speech only; no real voice and no
personal data.

## Limits

* Synthetic TTS speech only, one network path (local uvicorn on
  `127.0.0.1:8100` to the live providers), not a phone or a browser. The
  browser's 45 s idle timer was not itself exercised; the server-side
  gap that feeds it was measured.
* The production `gnani-voice` service was not restarted or stopped; all
  evidence comes from a throw-away uvicorn process using the existing
  keys from `/etc/gnani-coach/voice.env`, read into the process
  environment only and never written anywhere.
* The live pump was measured on this provider path only. It reuses one
  Gnani socket per call and relies on the turn's own hold silence to
  close the VAD window (no `commit` frame is sent); if a future provider
  closes the socket between turns, `_push_live` falls back to the clip
  path for the rest of the call.
* p50 of two runs, not p95. Latency is dominated by the model in these
  runs, so a slower model increases it even though the recogniser no
  longer replays the clip.
* Unit tests: `services/voice/tests/conversation` and the touched
  provider tests — **203 passed, 1 skipped**.

## Commit

`COMMIT_HASH_PLACEHOLDER`

PHASE 16 BUILT — NEEDS RESTART OF gnani-voice
