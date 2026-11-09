# RESULT-B6 — Phase 19 live on production

Checked from the **EC2 box over the public internet**, not from a phone.

| Piece | Value |
| --- | --- |
| Web | https://gnani-coach.vercel.app |
| Web deployment | `dpl_7jxHEx6cEFyajUNTF493qzkYsqGy` (`gnani-coach-1xiygm581-…`), `Ready`, production |
| Voice | `wss://13-205-26-178.sslip.io/ws/call` |
| Voice commit | `02d5c30` |
| Voice unit | `active`, `MemoryCurrent=55,291,904` (~52.7 MiB), `MemoryMax=629,145,600` |
| Health | local `200`, public `200` |

## Checks

| Check | Result | Raw output |
| --- | --- | --- |
| `check_deploy.py` | **PASS** — `pass=16 fail=0 skip=1` (APK not published) | `prompts/phase-20-ship-2/evidence/check-deploy.txt` |
| `call_two_utterances.py` (production) | **PASS** | `evidence/call-two-utterances.txt` |
| `call_once.py` (production) | **PASS** — H, E1, E2 all pass | `evidence/call-once.txt` |
| `turn timings` in the journal | **present** | `evidence/journal-turn-timings.txt` |
| Vercel deployment newer than Phase 19 and `Ready` | **PASS** | `evidence/vercel-ls.txt`, `evidence/vercel-inspect.txt` |

## The three Phase 19 numbers

Definitions are the same as Phase 19: (i) end of the long synthetic clip →
first binary frame of any kind; (ii) the same, but the first binary whose
descriptor is `kind: reply`; (iii) the largest interval between two server
messages.

| Measure | Production |
| --- | ---: |
| (i) end of speech → first sound of any kind | **1,674 ms** |
| (ii) end of speech → first word of the real reply | **4,393 ms** |
| (iii) longest gap between server messages | **10,527 ms** |
| backchannels | 3 |
| errors / early close | 0 / no |

`call_once.py` H: first sound **681 ms**; E2 clean second call: **645 ms**.

The two targets (≤1.5 s and ≤4 s) are narrowly missed over the public
internet (1.674 s and 4.393 s). The local Phase 19 run measured 618 ms and
3.542 s; the extra time is the public path, not a code regression. This is
recorded, not edited away.

## Not proven

* A real phone and the Android WebView were not used.
* Only English and synthetic TTS speech were used; other catalog
  languages have no validated backchannel voice and fall back to English.
* The p50 over n ≥ 5 was not measured; this is one production run of each
  script.
* Backchannel taste remains subjective.

Provider turns used in this phase: **4** (2 in `call_two_utterances`, 2 in
`call_once`), within the ≤ 8 limit.
