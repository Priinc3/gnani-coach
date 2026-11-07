# Phase 02 — FIX cycle 2 report (bounded filler experiment)

Working directory for every command: repository root
(`/Users/princegondaliya/Learning/Projects/temp/gnani`).
Executor: Phase 02 agent (FIX cycle 2). Date: 2026-10-20. All timestamps
in evidence are UTC.

The FIX-1 report is preserved unchanged at
[`REPORT-FIX-1.md`](REPORT-FIX-1.md). This file is the FIX-2 report.

Docs delivered: [`docs/feasibility/SETUP.md`](../../docs/feasibility/SETUP.md) ·
[`DECISION.md`](../../docs/feasibility/DECISION.md) ·
[`CAPABILITIES.md`](../../docs/feasibility/CAPABILITIES.md) ·
[`HANDOFF.md`](../../docs/feasibility/HANDOFF.md)

> **Rotation.** Recorded as
> `WAIVED: owner-accepted risk, user declined rotation 2026-10-20`, and
> scoped to the owner's own keys. Nothing else is relaxed: no key value
> appears in a prompt, in code, in a log, in evidence or in this report,
> and no value was read from anywhere.

---

## 1. The annotation (Step 0, offline)

| Item | Value |
|---|---|
| Sidecar | [`fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json`](../../fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json) |
| Audio | `fixtures/synthetic/audio/spoken-filled-hesitation.wav` — **unaltered** |
| sha256 (recomputed before writing the sidecar) | `82900f998131e7f512a2bee278e16f5bc849a5475510272ac5d321b53018ab56` |
| Hash check | `shasum -a 256` → **identical** to `fixtures/synthetic/manifest.json` → `sha256MatchesManifest: true` |
| Reviewer | `project owner (user)` |
| Date | `2026-10-20` |
| `um_present` / `uh_present` | `true` / `true` |
| Event positions | **`null`** — the reviewer reported presence only; no position was provided and none is inferred, estimated or invented |
| Scope note | one clip — **not** the ≥20 positive + ≥20 negative set; the audio was not altered and **no capability flag was flipped** |

The owner's answer resolves the ambiguity the FIX-1 report recorded: the
two fillers **are audible in this clip**, so the fillers that are missing
from the recogniser's output were really spoken in the audio that was
recognised. `DECISION.md` Q3 is updated with this fact. The Q3 verdict
itself is **unchanged**: the target (≥90 % precision, ≥80 % recall, p95
boundary ≤300 ms) is still neither met nor refuted, because a
presence-only annotation is not an evaluation set.

---

## 2. The three routes (Step 1)

One clip, one shared budget, `--max-requests 16`. **Pass rule:** a route
passes when it reports **both** fillers on the hesitation clip **and**
reports none on `spoken-clear-sentence`. Command:

```bash
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  filler --allow-live --max-requests 16
```

### 2.1 The table

| Route | Variant | Exact settings | Recognised text / detected events | Positions | Pass/fail | Wire attempts |
|---|---|---|---|---|---|---|
| **E1** | `verbatim-min-silence-500` | `lang_code=en-IN`, `x-sample-rate=16000`, `x-format=verbatim`, `x-vad-threshold=0.7`, `x-min-silence-ms=500`, `x-min-speech-ms=100`, `x-min-segment-ms=120`, substitution off, no bias, real-time pacing | — | — | **BLOCKED** — `GNANI_API_KEY` missing | **0** |
| **E1** | `verbatim-min-silence-300` | as above with `x-min-silence-ms=300` | — | — | **BLOCKED** — `GNANI_API_KEY` missing | **0** |
| **E1** | `transcribe-min-silence-300` | `x-format=transcribe`, `x-min-silence-ms=300` | — | — | **BLOCKED** — `GNANI_API_KEY` missing | **0** |
| **E1** | `verbatim-min-silence-300-bias-1.0` | `+ x-bias-list=["um","uh"]`, `x-bias-score=1.0`, `x-format=verbatim` | — | — | **BLOCKED** — `GNANI_API_KEY` missing | **0** |
| **E1** | `verbatim-min-silence-300-bias-2.0` | `+ x-bias-list=["um","uh"]`, `x-bias-score=2.0` | — | — | **BLOCKED** — `GNANI_API_KEY` missing | **0** |
| **E2** | `audio-review-filled-hesitation` | model `GEMINI_MODEL` (unset), clip attached inline (wav, 117,804 bytes), prompt asks for a verbatim transcript + filled pauses as JSON with `MM:SS` positions, `store=false`, SDK `HttpRetryOptions(attempts=1)` | — | — | **BLOCKED** — `GEMINI_API_KEY`, `GEMINI_MODEL` missing | **0** |
| **E2** | `audio-review-clear-sentence` | as above, on `spoken-clear-sentence` (81,964 bytes) | — | — | **BLOCKED** — `GEMINI_API_KEY`, `GEMINI_MODEL` missing | **0** |
| **E3** | `inside-region-scan-filled-hesitation` | Silero VAD (ONNX, `sha256 2623a295…`), inside-region scan: frames 25 ms / hop 10 ms, event band **150–800 ms**, frame RMS ratio 0.15–1.20 of the region's median frame RMS, voicing (energy ≤500 Hz) ≥0.50, mean spectral change ≤0.30 | **1 candidate event**: 2260–2415 ms (155 ms), RMS ratio 0.93, voicing 0.58, mean spectral change 0.019, dominant peak 200 Hz | 2260–2415 ms (1 event, not 2) | **FAILED** — one event is not both fillers | **0** |
| **E3** | `inside-region-scan-clear-sentence` | as above, on `spoken-clear-sentence` | **0 candidate events** | — | **PASSED** (negative control) | **0** |
| **E1** | negative control on `spoken-clear-sentence` | — | — | — | **NOT RUN** — no E1 variant reported both fillers, so no control was needed | **0** |

**Route verdicts:** E1 **BLOCKED**, E2 **BLOCKED**, E3 **FAILED**.
**NO ROUTE PASSED.**

### 2.2 What the E3 result does and does not say

The inside-region scan is the extension the brief asked for: the existing
candidate detector only looked at the **gaps between** VAD speech
regions, and this clip is a single VAD region (160–3520 ms), so the gap
scan can see nothing in it. The extended scan looks **inside** the
region for a short voiced, steady event — and it finds exactly **one**,
at 2260–2415 ms, 155 ms long, with a very steady spectrum (mean
spectral change 0.019) and a constant 200 Hz dominant peak.

That is **not** both fillers, so the route fails its own pass rule. Three
things are kept apart on purpose:

- **One event is not two.** The clip holds two audible filled pauses; the
  scan reports one candidate event of the required shape.
- **The event cannot be matched to "um" or "uh".** The reviewer gave
  **presence only** — no positions — so there is nothing to match the
  event against. It is a **candidate**, never a confirmed filled pause.
- **The clean clip is clean.** The same scan on `spoken-clear-sentence`
  reports **0** events, so the single event on the hesitation clip is not
  a general property of speech.

The clip's internal low-energy stretches are recorded in the evidence as a
**description of the signal only** (820–960 ms, 2010–2160 ms, 2400–2520 ms
and others). A low-energy stretch is not a filled pause; they are never
counted as candidates, and no parameter was moved to reach them.

**No detector parameter was tuned against this clip.** The parameters are
stated above, are printed with every result, and were fixed before the
run. The scan's stated limitation: an event is an **uninterrupted** run of
qualifying frames, so a single non-qualifying 10 ms frame splits a run.

### 2.3 Stop rules honoured

- Each route ran **once per variant**; no variant was re-run to change an
  outcome.
- **No** ≥20/≥20 set was built — that is the next decision, not this
  cycle's.
- **No** new detector project, **no** training, **no** extra provider
  (Groq/NIM were not touched; Gemini was kept).
- **No** loop: the step stopped at "no route passed" and reported the
  options.

### 2.4 One clip is a smoke signal only

Even had a route passed, it would have been a **smoke signal on one
clip**. It is **not** precision ≥90 %, **not** recall ≥80 % and **not** a
p95 boundary error ≤300 ms, and nothing in this report may be read that
way. Independently of any result, E2 could not have met the ≤300 ms
boundary target: the documented Gemini audio timestamps are `MM:SS`, one
second of resolution.

---

## 3. Raw output — `evidence/fix-2/`

Immutable run-ID directories, exactly as in fix-1. Nothing is overwritten.

| Run | Directory | Exit | What it holds |
|---|---|---|---|
| **The experiment (authoritative)** | `evidence/fix-2/20261020T093625Z-filler-45696009ad-e6d276/` | 1 | the whole step: `stdout.txt` (route table, settings, plan line), `result.json` (per-route records, events, positions, budget), `run.json` |
| Offline dry run of E1/E2 | `evidence/fix-2/20261020T093345Z-dryrun-filler-routes-229fe58df6-488b34/` | 0 | the two blocked routes' code paths against **fakes** — a fake transport and a fake Gemini client. Proves the code runs end to end; proves **nothing** about any provider |
| Verification — tests | `evidence/fix-2/20261020T093421Z-pytest-services-004797f835-ab50e4/` | 0 | `pytest services/voice/tests -v` — 247 passed, 3 skipped |
| Verification — leak scan | `evidence/fix-2/20261020T093427Z-secret-scan-ed172a5c4d-d84d89/` | 0 | `secret_scan.py` — **0 findings** |
| Earlier runs of the same command | `evidence/fix-2/20261020T0920*/`, `…0929*/` | — | the same computation with progressively more evidence recorded (the first run crashed on a syntax error in the new module; the next two add the structure diagnostic and the measured attempt accounting). **No detector threshold, gate or parameter changed between them** — only the recording of evidence |
| Ledger | `evidence/fix-2/run-index.jsonl` | — | the append-only index of every fix-2 invocation, failures included |

> **The verification was run last.** The two directories cited above
> (`…093421Z-pytest-services…` and `…093427Z-secret-scan…`) cover the
> final code. A **final** verification capture was run again after this
> report was written, so the two newest `pytest-services-*` and
> `secret-scan-*` directories in the ledger are that later pair; both
> exited **0**. The ledger is the authoritative list — no earlier run is
> ever overwritten.

---

## 4. Credentials and blockers

**Names only. No value was read, printed, stored or inferred.**

| Name | State | Needed by |
|---|---|---|
| `GNANI_API_KEY` | **missing** | E1 (all five variants) |
| `GEMINI_API_KEY` | **missing** | E2 (both reviews) |
| `GEMINI_MODEL` | **missing** | E2 (model selector; none is defaulted by design) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | not required | no probe in this phase uses them |

Sources checked: the process environment (no matching names set) and
`tools/probes/.env` (**the file does not exist**; it is the owner's to
create, mode `0600`, and no agent populates it).

**The blocker is exactly one thing: no credentials are configured.** The
offline part of the step — the annotation and the whole of E3 — ran in
full. To unblock E1 and E2, supply the three names privately and re-run
the one command in §2; the code paths are already verified by the dry run
in §3.

---

## 5. Changed files — this cycle only

**Created**

| Path | Purpose |
|---|---|
| `fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json` | the reviewer's annotation (sidecar; the WAV is untouched) |
| `tools/probes/live/filler_experiment.py` | the three routes, the shared budget, the pass rule |
| `tools/probes/dryrun_filler_routes.py` | offline, fake-backed proof that E1 and E2 run end to end |
| `tools/probes/capture_fix2_evidence.py` | captures the two verification commands as immutable fix-2 evidence |
| `prompts/phase-02-provider-feasibility/evidence/fix-2/**` | immutable run directories (one per invocation, never overwritten) + `run-index.jsonl` |

**Modified**

| Path | Change |
|---|---|
| `tools/probes/analysis/filler.py` | the detector now also scans **inside** VAD speech regions (voiced, steady, 150–800 ms), with stated parameters; the gap scan is unchanged and the new scan is off by default so the published numbers stand |
| `tools/probes/run.py` | the `filler` subcommand; the result and the measured attempt accounting are stored with the run's evidence |
| `tools/probes/evidence.py` | `evidence/fix-2/` as a separate immutable root |
| `services/voice/src/gnani_coach/providers/stt.py` | word-boosting rules are validated locally (single words of letters only, a documented score, `x-format: verbatim` required) and the score is written as `1.0`/`2.0`, because the provider **skips invalid boosting silently**; `build_config` can now carry the format and the boost |
| `services/voice/src/gnani_coach/providers/redaction.py` | `x-bias-list` / `x-bias-score` are recorded as settings, not masked as secrets |
| `docs/feasibility/DECISION.md` | Q3 carries the reviewer's fact; Option A is marked answered; the verdict is unchanged |
| `docs/feasibility/SETUP.md` | the `filler` command, the dry run, the boost rules, the fix-2 evidence root |
| `prompts/phase-02-provider-feasibility/REPORT.md` | this file (the fix-1 report is preserved as `REPORT-FIX-1.md`) |

**Not touched:** shared settings/main/contracts, capability flags, the
web/UI, Supabase, other phases, the CEO prompts/waivers/tracker,
`SOURCES.md`, `HANDOFF.md`, `CAPABILITIES.md`. Nothing was staged,
committed, pushed or deployed; no delegation, no training. Phase 03 and
G1 remain paused.

---

## 6. Recommendation (one line)

**Continue to the labelled set** — and the data it needs is
**position-labelled** audio: the same "both fillers, none on the clean
clip" rule, but over ≥20 positive + ≥20 negative clips per enabled filler
mode, with a reviewer giving **start/end positions** (the presence-only
annotation from this cycle cannot be scored against); supply the three
credential names privately and re-run the one command in §2 to fill in
E1 and E2 first, since a word-boosted or `transcribe` recognition may
change the picture before any new audio is rendered.

---

## 7. Bottom line

- **The annotation is recorded.** The hesitations were audible in the
  clip; the recogniser omitted them on that sample. No capability flag
  was flipped and the audio was not altered.
- **NO ROUTE PASSED.** E1 and E2 were **BLOCKED** — no credentials are
  configured — and E3 **failed** its own pass rule with one candidate
  event where the clip holds two filled pauses.
- **The goal is preserved.** Nothing was narrowed, no labelled set was
  faked, no provider was added, and the Q3 verdict still stands.

---

**BLOCKED: credentials not configured**
