# Phase 18 — ship (B5, NORMAL)

Status: **BLOCKED — the new web UI and the new voice code are live, but the
one live voice check failed: the long-turn coach reply timed out.**

## Production

| Piece | Value |
| --- | --- |
| Web URL | **https://gnani-coach.vercel.app** |
| Vercel deployment id | `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` |
| Deployment URL | https://gnani-coach-6ox4341pr-0-prince-0s-projects.vercel.app |
| Deployment state | `READY`, target `production`, alias points at this id |
| Web commit | `7186341` |
| `NEXT_PUBLIC_VOICE_WS_URL` | unchanged: `wss://13-205-26-178.sslip.io/ws/call` (compared without printing it) |
| Voice service | `gnani-voice.service` `active`/`running`, commit `7186341` |
| Voice memory | `MemoryCurrent=55173120` (~52.6 MiB); unit limits `MemoryHigh=500M`, `MemoryMax=600M` |
| Voice health | local `http://127.0.0.1:8000/health` 200; public `https://13-205-26-178.sslip.io/health` 200 |
| Provider keys | `GNANI_API_KEY=SET`, `GEMINI_API_KEY=SET`; `/etc/gnani-coach/keys.env` absent. No values read or printed. |

No Vercel env value, deployment protection, billing, repo visibility, AWS or
GitHub setting was changed. No APK was rebuilt.

## Checks and raw output

All raw outputs are under `prompts/phase-18-ship/evidence/`.

| Check | Result | Raw output |
| --- | --- | --- |
| Phase 16 + 17 commits present | PASS | `evidence/git-log.txt` |
| `update-voice.sh` (pull, `uv sync --frozen`, restart, health) | PASS — `UPDATE OK (commit 7186341)` | `evidence/update-voice.txt` |
| `systemctl is-active`, `MemoryCurrent`, both `/health` | PASS | `evidence/voice-state.txt` |
| Key names set/empty only | PASS | `evidence/voice-env-names.txt` |
| `vercel deploy --prod --yes` | PASS — `READY`, alias assigned | `evidence/vercel-deploy.txt` |
| `vercel inspect gnani-coach.vercel.app` | PASS — alias resolves to `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` | `evidence/vercel-inspect.txt` |
| `check_deploy.py` | PASS — `pass=16 fail=0 skip=1` (APK SKIP) | `evidence/check-deploy.txt` |
| `call_two_utterances.py` (Phase 16) | **FAIL** — long-turn coach reply timed out | `evidence/call-two-utterances.txt` |
| `call_once.py` | NOT RUN — stopped on the first live failure, provider budget preserved | — |
| Web `/`, `/manifest.webmanifest`, `/auth/sign-in` | PASS — all 200 | `evidence/web-check.txt`, `evidence/web-root.headers`, `evidence/manifest.webmanifest`, `evidence/signin.headers` |
| CSP `connect-src` has the wss origin | PASS | `evidence/web-check.txt`, `evidence/web-root.headers` |

### The failing live check

```
transcript_final_count=2
long_transcript_chars=191
coach_text_count=0 coach_after_long=0
longest_gap_between_server_messages_ms=15002
end_of_long_speech_to_first_coach_audio_ms=None
errors=1 socket_closed_early=False
RESULT=FAIL
```

Server log at the same time:

```
coach turn failed session=ses_7bc245fa7d09510c turn=trn_4092fae2c29addf6 category=timeout
```

The long utterance was transcribed (39 words, 191 chars) and the turn went
`thinking`, but no `coach_text` and no coach audio arrived. The client got one
`error` event after the two 10 s reasoning attempts. The "Hello." turn was
superseded by the long utterance, so it produced no coach line either.

A first invocation without `--url` used the script's local default
(`ws://127.0.0.1:8100`) and failed to connect before any provider call. The
public invocation above is the one live run.

Provider turns used: 3 reasoning attempts (1 superseded + 2 timed out), 2 STT
submissions, 0 coach audio. Under the ≤ 6 budget.

### Web content

Live landing page, rough strip-tags count: **26** words whole document
(`<title>` included), **19** body-only, **11** main content. Phase 17's table
said 12 for Landing. The live HTML contains the Phase 17 copy
(`Speak with confidence`, `Practice out loud.`, one `Start`, one `Sign in`);
the extra counted words are the document title, the top nav and bottom tab
bar, and two `aria-hidden` floating labels.

## App-code edits

None. No file under `apps/` or `services/` was changed. The only writes are
this report, `tests/smoke/RESULT-B5.md`, and `evidence/`.

## Defects

| Severity | Defect | Evidence |
| --- | --- | --- |
| 🔴 | A long learner utterance (39 words) gets no coach reply in production: the reasoning provider times out twice and the client receives an `error` event instead of `coach_text`/audio. The Phase 16 loop fix is deployed but not proven live. | `evidence/call-two-utterances.txt`, journal line `category=timeout` |
| 🟡 | `update-voice.sh` prints `Warning: The unit file ... changed on disk. Run 'systemctl daemon-reload'`. The running unit is the expected one; the warning is pre-existing and harmless this run. | `evidence/update-voice.txt` |
| 🟡 | APK still not published; the web PWA is the only delivery. | `evidence/check-deploy.txt` |

## What the user must do

1. **Phone check (web/PWA only):** open **https://gnani-coach.vercel.app** and
   follow `tests/smoke/PHONE-CHECKLIST.md`. Do not expect a long answer to
   work until the 🔴 above is fixed; a short sentence is the useful check now.
2. **APK:** do **not** rebuild for this phase. `prompts/phase-17-simple-ui/REPORT.md`
   records no native file change, and GitHub Actions is still blocked.
3. **Keys / billing:** nothing to do. No key or password appears in this
   report or the evidence.

## Why this is BLOCKED

The phase goal requires the new voice fix to be proven by one live check.
That check failed in production with `category=timeout` on the long turn, so
the deploy is live but not proven. Per the BUILD rule I stopped at the first
failure and did not retry or run `call_once.py`.

BLOCKED: live long-turn coach reply timed out in production (`category=timeout`, no `coach_text`/audio; `call_two_utterances.py` RESULT=FAIL).
