# B5 TEST-RESULT — ship (Phase 18)

Date: 2026-11-09. Box: the EC2 voice host (2 GB RAM). All checks ran against
the public URLs.

Status: **PASS after one fix.** The first live voice check failed with a
reasoning timeout; the minimum fix is recorded below and the same check then
passed.

## URLs and deployment

| Piece | Value |
| --- | --- |
| Web app | https://gnani-coach.vercel.app |
| Vercel deployment | `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` |
| Deployment URL | https://gnani-coach-6ox4341pr-0-prince-0s-projects.vercel.app |
| Voice health | https://13-205-26-178.sslip.io/health |
| Voice socket | wss://13-205-26-178.sslip.io/ws/call |
| Voice commit | `097720f` (`phase-18: raise coach reasoning timeout after live long-turn timeout`) |
| Web build | commit `7186341`; `NEXT_PUBLIC_VOICE_WS_URL` unchanged (`wss://13-205-26-178.sslip.io/ws/call`) |
| APK | **not published** — GitHub Actions still blocked |

The web build did not change after the fix; only the voice service restarted.

## Raw outputs

| File | What it is |
| --- | --- |
| `prompts/phase-18-ship/evidence/git-log.txt` | `git log --oneline -6` before the fix |
| `prompts/phase-18-ship/evidence/git-log-after-fix.txt` | `git log --oneline -4` after the fix |
| `prompts/phase-18-ship/evidence/update-voice.txt` | `update-voice.sh` before the fix |
| `prompts/phase-18-ship/evidence/update-voice-after-fix.txt` | `update-voice.sh` after the fix (commit `097720f`) |
| `prompts/phase-18-ship/evidence/voice-state.txt` | service state and `/health` before the fix |
| `prompts/phase-18-ship/evidence/voice-state-after-fix.txt` | service state and `/health` after the fix |
| `prompts/phase-18-ship/evidence/voice-env-names.txt` | key names with `SET`/`EMPTY` only (no values) |
| `prompts/phase-18-ship/evidence/voice-timeouts-after-fix.txt` | journal grep after the restart (no timeout lines) |
| `prompts/phase-18-ship/evidence/vercel-deploy.txt` | full `vercel deploy --prod` output |
| `prompts/phase-18-ship/evidence/vercel-inspect.txt` | `vercel inspect gnani-coach.vercel.app` |
| `prompts/phase-18-ship/evidence/check-deploy.txt` | full `check_deploy.py` run |
| `prompts/phase-18-ship/evidence/call-two-utterances.txt` | first live run — **FAIL** |
| `prompts/phase-18-ship/evidence/call-two-utterances-after-fix.txt` | second live run — **PASS** |
| `prompts/phase-18-ship/evidence/web-root.headers`, `web-root.html` | `/` headers and HTML |
| `prompts/phase-18-ship/evidence/web-check.txt` | word count, status codes, CSP, manifest |
| `prompts/phase-18-ship/evidence/manifest.headers`, `manifest.webmanifest` | manifest response and body |
| `prompts/phase-18-ship/evidence/signin.headers`, `signin.html` | `/auth/sign-in` response |

## Pass/fail

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| G1 | `git pull --ff-only`, phase-16 and phase-17 commits present | **PASS** — `7186341`, `9a373fc`, `1cdca4b`, `5215224` | `git-log.txt` |
| V1 | `update-voice.sh` (pull, `uv sync --frozen`, restart, health) | **PASS** — `UPDATE OK (commit 7186341)`; after fix `UPDATE OK (commit 097720f)` | `update-voice*.txt` |
| V2 | `systemctl is-active gnani-voice` | **PASS** — `active` (`running`) | `voice-state*.txt` |
| V3 | Voice memory | **PASS** — 52.6 MiB before, 120.7 MiB after; both under `MemoryHigh=500M` | `voice-state*.txt` |
| V4 | `/health` local and public | **PASS** — HTTP 200 / HTTP 200, both runs | `voice-state*.txt` |
| V5 | Provider keys present by name | **PASS** — `GNANI_API_KEY=SET`, `GEMINI_API_KEY=SET`; no `keys.env` override file | `voice-env-names.txt` |
| W1 | `vercel deploy --prod` | **PASS** — `readyState: READY`, alias `https://gnani-coach.vercel.app` | `vercel-deploy.txt` |
| W2 | Alias points at the new deployment | **PASS** — inspect resolves the alias to `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` | `vercel-inspect.txt` |
| W3 | `NEXT_PUBLIC_VOICE_WS_URL` unchanged | **PASS** — value matched `wss://13-205-26-178.sslip.io/ws/call`; compared without printing it | this run |
| C1 | `check_deploy.py` | **PASS** — `SUMMARY pass=16 fail=0 skip=1` (APK SKIP) | `check-deploy.txt` |
| C2 | `call_two_utterances.py` (Phase 16 live check) | **FAIL then PASS** after the timeout fix | `call-two-utterances*.txt` |
| C3 | `call_once.py` | **NOT RUN** — the ≤ 6 provider-turn budget was reached (see below) | — |
| H1 | `/` returns 200 | **PASS** — HTTP 200 | `web-check.txt` |
| H2 | `/manifest.webmanifest` returns 200, `display: standalone` | **PASS** — HTTP 200 | `web-check.txt`, `manifest.webmanifest` |
| H3 | `/auth/sign-in` returns 200 | **PASS** — HTTP 200 | `web-check.txt`, `signin.headers` |
| H4 | CSP `connect-src` contains the wss origin | **PASS** — `connect-src 'self' wss://13-205-26-178.sslip.io https://13-205-26-178.sslip.io` | `web-check.txt` |

## The fix (one defect, one edit)

**File:** `services/voice/src/gnani_coach/conversation/config.py`

| Line | Before | After |
| --- | --- | --- |
| 109 | `REASONING_DEADLINE_S = 20.0` | `REASONING_DEADLINE_S = 30.0` |
| 115 | `REASONING_ATTEMPT_TIMEOUT_S = 10.0` | `REASONING_ATTEMPT_TIMEOUT_S = 20.0` |

**Reason:** a direct probe of the same `gemini-3.5-flash-lite` call
(`thinking_level=low`, 300 output tokens) took **9.61 s**. The old 10 s
per-attempt bound was at the edge of normal latency, and the 20 s overall
deadline left no room for a retry, so a 39-word learner turn timed out twice
and the client got an `error` event instead of a coach line. The new bounds
give one attempt 20 s and the call 30 s. Heartbeats every 15 s reset the
browser's 45 s idle watchdog, so 30 s stays inside the client contract.

No other file changed. No prompt, event, status, payload key or dependency
changed.

## Live voice check

### Before the fix — FAIL

`services/voice/.venv/bin/python tests/smoke/call_two_utterances.py --url wss://13-205-26-178.sslip.io/ws/call`

```
transcript_final_count=2
long_transcript_chars=191
coach_text_count=0 coach_after_long=0
longest_gap_between_server_messages_ms=15002
end_of_long_speech_to_first_coach_audio_ms=None
errors=1 socket_closed_early=False
RESULT=FAIL
```

Server log:

```
Nov 09 07:44:45 ... coach turn failed session=ses_7bc245fa7d09510c turn=trn_4092fae2c29addf6 category=timeout
```

### After the fix — PASS

```
transcript_final_count=2
long_transcript_chars=191
coach_text_count=1 coach_after_long=1
longest_gap_between_server_messages_ms=10329
end_of_long_speech_to_first_coach_audio_ms=6975
errors=0 socket_closed_early=False
RESULT=PASS
```

The coach line arrived at +19.152 s, followed immediately by `speaking` and
coach audio frames. The journal since the `07:51:08` restart has no
`coach turn failed` or `category=timeout` line.

## Latency

Definition used by `call_two_utterances.py`: the end of the last learner
audio frame of the long utterance → the first coach audio byte.

| Run | End of long speech → first coach audio | Longest gap between server messages |
| --- | --- | --- |
| Before fix | `None` (timeout) | 15,002 ms |
| After fix | **6,975 ms** | **10,329 ms** |

Both gaps are below the browser's 45 s idle watchdog. The first "Hello."
turn is still superseded by the long utterance (the learner starts speaking
again 2 s later), so it produces no coach line by design.

## Provider turns

At most **6 reasoning attempts** were spent in this phase: 3 on the failed
run (1 superseded "Hello." attempt + 2 timed-out long-turn attempts), 1 on
the direct latency probe, and 2 on the passing run (1 superseded "Hello."
attempt + 1 successful long-turn attempt). This reaches the ≤ 6 budget, so
`call_once.py` was not run. The passing `call_two_utterances.py` is the one
required live proof.

## Web content — landing word count

Rough strip-tags count of `https://gnani-coach.vercel.app/` (whole document,
`<title>` included): **26** words. Body-only visible words: **19**. The main
content (title + line + Start + Sign in) is **11** words; the rest is the
document title, the top nav and bottom tab bar, and two `aria-hidden`
floating labels.

| Screen | Phase 17 table | Live 2026-11-09 | Method |
| --- | --- | --- | --- |
| Landing | 12 | 26 rough / 19 body / 11 main | `curl` + strip tags; whole document includes `<title>` and nav |

The live build contains the Phase 17 copy (`Speak with confidence`,
`Practice out loud.`, one `Start`, one `Sign in`); no Phase 04/10 stats,
hero paragraph or long privacy block is present.

## What is unproven

- `call_once.py` (one-turn / silence / drop-and-reconnect regression) was
  not run because the provider-turn budget was reached.
- Real phone, Android WebView, other browsers, microphone permission UI,
  and languages other than English.
- The APK: not rebuilt and not published (GitHub Actions blocked).
