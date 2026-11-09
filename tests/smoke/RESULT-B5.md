# B5 TEST-RESULT — ship (Phase 18)

Date: 2026-11-09. Box: the EC2 voice host (2 GB RAM). All checks ran against
the public URLs.

## URLs and deployment

| Piece | Value |
| --- | --- |
| Web app | https://gnani-coach.vercel.app |
| Vercel deployment | `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` |
| Deployment URL | https://gnani-coach-6ox4341pr-0-prince-0s-projects.vercel.app |
| Voice health | https://13-205-26-178.sslip.io/health |
| Voice socket | wss://13-205-26-178.sslip.io/ws/call |
| Voice commit | `7186341` (`phase-16: record report commit hash`) |
| Web build | commit `7186341`; `NEXT_PUBLIC_VOICE_WS_URL` unchanged (`wss://13-205-26-178.sslip.io/ws/call`) |
| APK | **not published** — GitHub Actions still blocked |

## Raw outputs

| File | What it is |
| --- | --- |
| `prompts/phase-18-ship/evidence/git-log.txt` | `git log --oneline -6` |
| `prompts/phase-18-ship/evidence/update-voice.txt` | full `update-voice.sh` run |
| `prompts/phase-18-ship/evidence/voice-state.txt` | `systemctl is-active`, `MemoryCurrent`, local and public `/health` |
| `prompts/phase-18-ship/evidence/voice-env-names.txt` | key names with `SET`/`EMPTY` only (no values) |
| `prompts/phase-18-ship/evidence/vercel-deploy.txt` | full `vercel deploy --prod` output |
| `prompts/phase-18-ship/evidence/vercel-inspect.txt` | `vercel inspect gnani-coach.vercel.app` |
| `prompts/phase-18-ship/evidence/check-deploy.txt` | full `check_deploy.py` run |
| `prompts/phase-18-ship/evidence/call-two-utterances.txt` | full `call_two_utterances.py` run against the public socket |
| `prompts/phase-18-ship/evidence/web-root.headers`, `web-root.html` | `/` headers and HTML |
| `prompts/phase-18-ship/evidence/web-check.txt` | word count, status codes, CSP, manifest |
| `prompts/phase-18-ship/evidence/manifest.headers`, `manifest.webmanifest` | manifest response and body |
| `prompts/phase-18-ship/evidence/signin.headers`, `signin.html` | `/auth/sign-in` response |

## Pass/fail

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| G1 | `git pull --ff-only`, phase-16 and phase-17 commits present | **PASS** — `7186341`, `9a373fc`, `1cdca4b`, `5215224` | `git-log.txt` |
| V1 | `update-voice.sh` (pull, `uv sync --frozen`, restart, health) | **PASS** — `UPDATE OK (commit 7186341)` | `update-voice.txt` |
| V2 | `systemctl is-active gnani-voice` | **PASS** — `active` (`running`) | `voice-state.txt` |
| V3 | Voice memory | **PASS** — `MemoryCurrent=55173120` (~52.6 MiB), under `MemoryHigh=500M` | `voice-state.txt` |
| V4 | `/health` local and public | **PASS** — HTTP 200 / HTTP 200 | `voice-state.txt` |
| V5 | Provider keys present by name | **PASS** — `GNANI_API_KEY=SET`, `GEMINI_API_KEY=SET`; no `keys.env` override file | `voice-env-names.txt` |
| W1 | `vercel deploy --prod` | **PASS** — `readyState: READY`, alias `https://gnani-coach.vercel.app` | `vercel-deploy.txt` |
| W2 | Alias points at the new deployment | **PASS** — inspect resolves the alias to `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` | `vercel-inspect.txt` |
| W3 | `NEXT_PUBLIC_VOICE_WS_URL` unchanged | **PASS** — value matched `wss://13-205-26-178.sslip.io/ws/call`; compared without printing it | this run |
| C1 | `check_deploy.py` | **PASS** — `SUMMARY pass=16 fail=0 skip=1` (APK SKIP) | `check-deploy.txt` |
| C2 | `call_two_utterances.py` (Phase 16 live check) | **FAIL** — long-turn coach reply timed out; see below | `call-two-utterances.txt` |
| C3 | `call_once.py` | **NOT RUN** — stopped on C2 per the BUILD rule and the provider-turn budget | — |
| H1 | `/` returns 200 | **PASS** — HTTP 200 | `web-check.txt` |
| H2 | `/manifest.webmanifest` returns 200, `display: standalone` | **PASS** — HTTP 200 | `web-check.txt`, `manifest.webmanifest` |
| H3 | `/auth/sign-in` returns 200 | **PASS** — HTTP 200 | `web-check.txt`, `signin.headers` |
| H4 | CSP `connect-src` contains the wss origin | **PASS** — `connect-src 'self' wss://13-205-26-178.sslip.io https://13-205-26-178.sslip.io` | `web-check.txt` |

## Live voice check (C2) — FAIL

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

The server log for the same window:

```
Nov 09 07:44:45 ... coach turn failed session=ses_7bc245fa7d09510c turn=trn_4092fae2c29addf6 category=timeout
```

The long utterance was transcribed (39 words, 191 chars) and the turn entered
`thinking` at +13.555 s, but no `coach_text` or coach audio followed. The
client received one `error` event at +34.644 s, i.e. after the reasoning
attempt budget (`REASONING_ATTEMPT_TIMEOUT_S = 10.0`, two attempts) elapsed.
The first "Hello." turn was also superseded by the long utterance and
produced no coach line, so `coach_text_count=0`.

A first attempt without `--url` used the script's local default
(`ws://127.0.0.1:8100`) and failed to connect; it made no provider call and
is not counted as the live run. The public run above is the one live run.

Provider turns used: 1 successful reasoning turn (the "Hello." attempt was
fenced by the next utterance) + 2 timed-out reasoning attempts = 3 reasoning
attempts; 2 STT submissions; 0 coach audio. Within the ≤ 6 budget.

## Latency

Definition used by `call_two_utterances.py`: the end of the last learner
audio frame of the long utterance → the first coach audio byte. This run
reported `None` because no coach audio arrived. The longest gap between any
two server messages was 15,002 ms; the 45 s browser idle watchdog did not
fire.

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

- The long-turn coach reply in production: the reasoning provider timed out
  twice, so the Phase 16 fix is deployed but not proven end-to-end live.
- The basic one-turn regression (`call_once.py`) was not run, to respect the
  stop-on-first-failure rule and the provider-turn budget.
- Real phone, Android WebView, other browsers, microphone permission UI,
  and languages other than English.
- The APK: not rebuilt and not published (GitHub Actions blocked).
