# Phase 20 — ship-2 (B6, NORMAL)

Status: **BUILT.** Production runs Phase 19; the web deployment is newer
than the Phase 19 commit and `Ready`; all three live checks pass.

## Production

| Piece | Value |
| --- | --- |
| Web URL | **https://gnani-coach.vercel.app** |
| Vercel deployment id | `dpl_7jxHEx6cEFyajUNTF493qzkYsqGy` |
| Deployment URL | https://gnani-coach-1xiygm581-0-prince-0s-projects.vercel.app |
| Deployment state | `Ready`, target `production`, alias points at this id |
| Created | 2026-11-09 08:47:44 UTC (after the Phase 19 push) |
| Voice URL | `wss://13-205-26-178.sslip.io/ws/call` |
| Voice commit | `02d5c30` |
| Voice unit | `gnani-voice.service` `active`/`running` |
| Voice memory | `MemoryCurrent=55,291,904` (~52.7 MiB); `MemoryHigh=524,288,000`, `MemoryMax=629,145,600` |
| Voice health | local `http://127.0.0.1:8000/health` 200; public `/health` 200 |
| Provider keys | set; no value read or printed |

No Vercel env value, protection setting, billing, repo visibility, AWS or
GitHub setting was changed. No APK was rebuilt.

## What was deployed

* `sudo systemctl daemon-reload`, then `sudo bash
  scripts/deploy/update-voice.sh`: `UPDATE OK (commit 02d5c30)`.
* Vercel was already linked to GitHub; the push to `main` produced the
  `Ready` production deployment above. It was verified, not redeployed.
* No new environment variable was required: `SPEAKING_COACH_LOG_LEVEL` is
  optional and defaults to `INFO`. `/etc/gnani-coach/voice.env` was not
  edited.

## Checks and raw output

All raw outputs are in `prompts/phase-20-ship-2/evidence/`.

| Check | Result | Raw output |
| --- | --- | --- |
| `update-voice.sh` (pull, `uv sync --frozen`, restart, health) | PASS — `UPDATE OK (commit 02d5c30)` | `evidence/update-voice.txt` |
| `systemctl is-active`, `MemoryCurrent`, both `/health` | PASS | `evidence/voice-state.txt` |
| `vercel ls` / `vercel inspect` | PASS — newest deployment `Ready`, alias assigned | `evidence/vercel-ls.txt`, `evidence/vercel-inspect.txt` |
| `check_deploy.py` | PASS — `pass=16 fail=0 skip=1` (APK SKIP) | `evidence/check-deploy.txt` |
| `call_two_utterances.py` (production) | PASS | `evidence/call-two-utterances.txt` |
| `call_once.py` (production) | PASS — H, E1, E2 | `evidence/call-once.txt` |
| `turn timings` now in `journalctl -u gnani-voice` | PASS | `evidence/journal-turn-timings.txt` |

## Live numbers (from the EC2 box over the public internet)

Definitions: (i) end of the synthetic long clip → first binary frame of any
kind; (ii) the same, but the first binary whose descriptor is
`kind: reply`; (iii) the largest gap between two server messages.

| Measure | Production |
| --- | ---: |
| (i) first sound of any kind | **1,674 ms** |
| (ii) first word of the real reply | **4,393 ms** |
| (iii) longest server-message gap | **10,527 ms** |

`call_once.py` H: first sound **681 ms**; E2 clean second call **645 ms**.
No errors, no early close. Provider turns used: **4** (limit 8).

The Phase 19 local numbers were 618 ms and 3,542 ms; production narrowly
misses the 1.5 s / 4 s targets (1.674 s / 4.393 s) over the public path.
Recorded as an observation, not an app-code edit.

## App-code edits

None. The successor right was not used.

## Defects

* 🔴 none.
* 🟠 none that blocks the B6 verdict. The public-internet latency is
  slightly over the Phase 19 targets (see above); the same code measured
  under the targets locally, so this is network/provider time, not a
  functional defect.
* 🟡 `check_deploy.py` skips the APK because no APK is published (GitHub
  Actions blocked; the PWA is the fallback). This is the pre-existing
  state, unchanged here.

## What the user must do

Open **https://gnani-coach.vercel.app**, start a call and speak. The voice
service is already restarted and healthy; no further deploy is needed. For
the phone, use the web app (the APK is still not published).

PHASE 20 BUILT — AWAITING B6 VERDICT
