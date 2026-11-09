# Phase 18 — ship (B5, NORMAL)

Status: **BUILT.** The new web UI and the new voice code are live, and the
one live voice check passes after one minimum fix.

## Production

| Piece | Value |
| --- | --- |
| Web URL | **https://gnani-coach.vercel.app** |
| Vercel deployment id | `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` |
| Deployment URL | https://gnani-coach-6ox4341pr-0-prince-0s-projects.vercel.app |
| Deployment state | `READY`, target `production`, alias points at this id |
| Web commit | `7186341` |
| `NEXT_PUBLIC_VOICE_WS_URL` | unchanged: `wss://13-205-26-178.sslip.io/ws/call` (compared without printing it) |
| Voice service | `gnani-voice.service` `active`/`running`, commit `097720f` |
| Voice memory | `MemoryCurrent=126541824` (~120.7 MiB) after the fix; unit limits `MemoryHigh=500M`, `MemoryMax=600M` |
| Voice health | local `http://127.0.0.1:8000/health` 200; public `https://13-205-26-178.sslip.io/health` 200 |
| Provider keys | `GNANI_API_KEY=SET`, `GEMINI_API_KEY=SET`; `/etc/gnani-coach/keys.env` absent. No values read or printed. |

No Vercel env value, deployment protection, billing, repo visibility, AWS or
GitHub setting was changed. No APK was rebuilt. The web build did not change
after the fix; only the voice service restarted.

## Checks and raw output

All raw outputs are under `prompts/phase-18-ship/evidence/`.

| Check | Result | Raw output |
| --- | --- | --- |
| Phase 16 + 17 commits present | PASS | `evidence/git-log.txt` |
| `update-voice.sh` (pull, `uv sync --frozen`, restart, health) | PASS — `UPDATE OK (commit 7186341)`; after fix `UPDATE OK (commit 097720f)` | `evidence/update-voice.txt`, `evidence/update-voice-after-fix.txt` |
| `systemctl is-active`, `MemoryCurrent`, both `/health` | PASS | `evidence/voice-state.txt`, `evidence/voice-state-after-fix.txt` |
| Key names set/empty only | PASS | `evidence/voice-env-names.txt` |
| `vercel deploy --prod --yes` | PASS — `READY`, alias assigned | `evidence/vercel-deploy.txt` |
| `vercel inspect gnani-coach.vercel.app` | PASS — alias resolves to `dpl_EP7pE5xghjTrdaUngYAgh3uK3aMa` | `evidence/vercel-inspect.txt` |
| `check_deploy.py` | PASS — `pass=16 fail=0 skip=1` (APK SKIP) | `evidence/check-deploy.txt` |
| `call_two_utterances.py` (Phase 16) | **FAIL then PASS** after the fix | `evidence/call-two-utterances.txt`, `evidence/call-two-utterances-after-fix.txt` |
| `call_once.py` | NOT RUN — the ≤ 6 provider-turn budget was reached | — |
| Web `/`, `/manifest.webmanifest`, `/auth/sign-in` | PASS — all 200 | `evidence/web-check.txt`, `evidence/web-root.headers`, `evidence/manifest.webmanifest`, `evidence/signin.headers` |
| CSP `connect-src` has the wss origin | PASS | `evidence/web-check.txt`, `evidence/web-root.headers` |
| Journal after the fix has no coach timeout | PASS | `evidence/voice-timeouts-after-fix.txt` |

### The failing check, then the passing check

Before the fix:

```
transcript_final_count=2
long_transcript_chars=191
coach_text_count=0 coach_after_long=0
longest_gap_between_server_messages_ms=15002
end_of_long_speech_to_first_coach_audio_ms=None
errors=1 socket_closed_early=False
RESULT=FAIL
```

Server log: `coach turn failed ... category=timeout`.

After the fix:

```
transcript_final_count=2
long_transcript_chars=191
coach_text_count=1 coach_after_long=1
longest_gap_between_server_messages_ms=10329
end_of_long_speech_to_first_coach_audio_ms=6975
errors=0 socket_closed_early=False
RESULT=PASS
```

The coach line arrived at +19.152 s, followed by `speaking` and audio frames.
No timeout line appears in the journal since the `07:51:08` restart.

## The app-code edit (successor right: one defect, one edit)

**File:** `services/voice/src/gnani_coach/conversation/config.py`

| Line | Before | After |
| --- | --- | --- |
| 109 | `REASONING_DEADLINE_S = 20.0` | `REASONING_DEADLINE_S = 30.0` |
| 115 | `REASONING_ATTEMPT_TIMEOUT_S = 10.0` | `REASONING_ATTEMPT_TIMEOUT_S = 20.0` |

**Reason:** a direct probe of the same `gemini-3.5-flash-lite` call
(`thinking_level=low`, 300 output tokens) took **9.61 s**. The old 10 s
per-attempt bound was at the edge of normal latency, and the 20 s deadline
left no room for a retry, so a 39-word learner turn timed out twice and the
client got `error` instead of a coach line. The new bounds give one attempt
20 s and the call 30 s. Heartbeats every 15 s reset the browser's 45 s idle
watchdog, so 30 s stays inside the client contract.

No other file changed. No prompt, event, status, payload key or dependency
changed. Commit `097720f`.

## Web content

Live landing page, rough strip-tags count: **26** words whole document
(`<title>` included), **19** body-only, **11** main content. Phase 17's table
said 12 for Landing. The live HTML contains the Phase 17 copy
(`Speak with confidence`, `Practice out loud.`, one `Start`, one `Sign in`);
the extra counted words are the document title, the top nav and bottom tab
bar, and two `aria-hidden` floating labels.

## Provider turns

At most **6 reasoning attempts**: 3 on the failed run, 1 on the direct
latency probe, 2 on the passing run. This reaches the ≤ 6 budget, so
`call_once.py` was not run.

## Defects

| Severity | Defect | Evidence |
| --- | --- | --- |
| ✅ fixed | The coach reasoning timeout was too tight for normal provider latency; a long learner turn got `error` instead of a reply. Fixed by raising the attempt bound to 20 s and the deadline to 30 s. | `evidence/call-two-utterances*.txt`, `services/voice/src/gnani_coach/conversation/config.py:109,115` |
| 🟡 | `update-voice.sh` prints `Warning: The unit file ... changed on disk. Run 'systemctl daemon-reload'`. The running unit is the expected one; the warning is pre-existing and harmless this run. | `evidence/update-voice*.txt` |
| 🟡 | APK still not published; the web PWA is the only delivery. | `evidence/check-deploy.txt` |

## What the user must do

1. **Phone check (web/PWA):** open **https://gnani-coach.vercel.app** and
   follow `tests/smoke/PHONE-CHECKLIST.md`. The long-answer timeout is fixed;
   a long sentence should now get a spoken reply, though the wait can be up
   to ~20 s on a slow provider day.
2. **APK:** do **not** rebuild for this phase. `prompts/phase-17-simple-ui/REPORT.md`
   records no native file change, and GitHub Actions is still blocked.
3. **Keys / billing:** nothing to do. No key or password appears in this
   report or the evidence.

PHASE 18 BUILT — AWAITING B5 VERDICT
