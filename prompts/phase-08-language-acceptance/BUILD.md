# Phase 08 — language-acceptance (B3, NORMAL)

You are Phase 08. **Siblings running now: none.** Phase 07 is finished. Phase 09 waits for you. Comm folder: none.

Goal link: `prompts/00-plan.md` §2, §9 and the acceptance targets. The product claims a ten-language catalog and audio-grounded feedback. **Nothing has ever been checked live.** You decide, with evidence, which capability each language and each feature may honestly show on release day. A failed or unchecked item is a disclosed limitation. It is not a pass, and you never write `validated` without live evidence plus a human reviewer entry.

## OWN (write)
`tests/acceptance/**` · `fixtures/evaluation/**` · `packages/contracts/data/capabilities.json` (**data only**) · `docs/evaluation/**` · your own `prompts/phase-08-language-acceptance/REPORT.md` + `evidence/`.
**CEO grant (2026-10-23):** you may also edit the **data values** of each language's `capabilities` flags in `packages/contracts/data/catalog.json` (`accountEnabled`, `conversationTested`, `assessmentValidated`). No shape change, no id change, no added or removed language.
DO NOT TOUCH: any schema, code under `services/**`, `apps/**`, `tools/**` (you may **run** the probes in `tools/probes`), root files, CEO files. A code defect you find → write it in REPORT with file:line. Don't fix it.

## Credentials gate (read this first)
Live work needs `GNANI_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL` in the process environment or `tools/probes/.env` (never read or print values; user-created). If **any is missing**: build the harness and the review sheets offline, run all offline checks, mark every live item `BLOCKED: credentials not configured`, set **no** capability to a passing state, and finish with `BLOCKED: credentials not configured` after everything offline is complete. Do not fake or reuse earlier evidence as new evidence.
Total live budget for this phase: ≤ 120 wire attempts, reported by run id. Use the repaired budget (`--allow-live --max-requests`, `--env-file` before the subcommand). Fixtures are synthetic only. No real personal data.

## Deliverables

### A. Per-language live matrix (10 catalog languages + Hinglish mode)
For each language: (1) render a **native-language** synthetic phrase with TTS in the language and save it under `fixtures/evaluation/audio/<id>/` with sha256 in a manifest (immutable, run-id'd); (2) send that audio through STT with the right `lang_code`, recording the recognised text and a text-similarity score against the intended phrase (word error rate, computed by your script. Define it in `docs/evaluation/`); (3) send the recognised text to Gemini with the coaching prompt in the language and record the reply (language detected, non-empty, on-topic by simple checks); (4) render the reply with TTS. `en-IN` is ambiguous between English and Hinglish. Use the catalog resolver, never guess. Missing native fixture = NOT RUN, never an English substitute. Each row aggregates **all** stages.
Per language the outcome is one of: `PASS-AUTOMATED` (all stages ran and passed thresholds you state up front, e.g. WER ≤ 0.35 on the phrase set, reply in the right language), `FAIL`, `NOT RUN`. Also write the thresholds before the first run. Don't tune them after.

### B. Human review sheets (the user is the reviewer)
A machine score cannot say a voice is intelligible or a coaching reply is useful. Generate `docs/evaluation/review/<id>.md` per language that has audio: the clip path, the sha256, the intended text, the recognised text, the coach reply, and checkbox lines `intelligible: yes/no/unclear`, `reply useful and in language: yes/no/unclear`, `reviewer:`, `date:`. Keep it to ≤ 3 clips per language so the user can finish it in under 30 minutes. A reviewed row copies the reviewer, date and sha256 into the evaluation record. **You never fill the review fields yourself.** A language is `enabled` in the release data only when `PASS-AUTOMATED` and both review answers are `yes` by the user.

### C. Filler capability (goal preserved, honest outcome)
Run once, live: `tools/probes/run.py --env-file tools/probes/.env filler --allow-live --max-requests 16` (the FIX-2 routes E1 and E2). Report the result against the acceptance bar: ≥ 20 labelled positives and ≥ 20 labelled negatives, precision ≥ 90 %, recall ≥ 80 %, matched-boundary p95 ≤ 300 ms. The repository has **one** presence-only reviewed clip, so the bar cannot be met. Do not synthesise labels. Produce `docs/evaluation/filler-labelling-kit.md`: a labelling sheet format and a procedure for the user to annotate 40 short clips (start/end of each filler, or "none") with a minimum time budget estimate, so the work could continue after the contest. State the options with costs: (a) continue to the labelled set, (b) **narrow the release explicitly**: pause/pace/turn-duration remain, and filler stays `unvalidated`/`insufficient_evidence` in every surface (needs the user's approval), (c) pause. The filler state in `capabilities.json` stays `unvalidated` unless a validated state meets **all** the bar numbers with dated evidence. A single passing clip is never `validated`.

### D. Measurement accuracy (offline, repeatable)
Using the existing synthetic fixtures with known gaps (`known-internal-gap`, `silence-3s`, `one-word`, `noise-2s`, `repetition`), run the **service's** analysis module (`gnani_coach.analysis`) and report the error against the annotated truth: pause longest/count error in ms, rate error, the `insufficient_evidence` behaviour on silence/noise/one-word, and the no-divide-by-zero cases. Synthetic-only results stay `validated_synthetic_only`. Say plainly that natural-learner accuracy is unproven.

### E. Latency and interruption (live, only if credentials exist)
Run Phase 07's opt-in latency harness for ≥ 30 turns on English. Report end-of-turn → first audio p50/p95 against the target (p95 ≤ 3 s), with endpointing and provider times split out. If < 30 turns, say "not a p95". Interruption-to-stop p95 ≤ 300 ms over 20 trials in a real browser if feasible; otherwise report the fake-stack number as not the target.

### F. Accessibility and mobile (automated, no new dependency)
Playwright against the real app at 1280 and 390 and 360: keyboard-only completion of the flow, visible focus, accessible names on every control, `aria-live` regions announce status, reduced motion, no horizontal overflow, text zoom 200 % still usable, Hindi and Tamil strings render. Report failures with file:line. Don't fix.

### G. Coaching-language pairs
Pairs to try (practice → coaching): English→English, Hindi→English, Hindi→Hindi, Tamil→Tamil, Hinglish→Hindi. Record each pair's state with the same rules as A. Untested pairs are listed `NOT RUN` in the release data and never shown as supported.

### H. Release capability data
Update `capabilities.json` and the per-language catalog flags to **exactly what the evidence supports**: `enabled`/`validated` only with a dated evidence pointer and (for language/assessment) a user review. Everything else stays documented/unvalidated with `unavailabilityReason`. Validate with `npm run test:contracts`. Write `docs/evaluation/RELEASE-CAPABILITIES.md`: one table (language × STT, TTS, coaching reply, review, state) and a plain-word list of **disclosed limitations** for the demo and the write-up.

## Criteria / commands (repo root, full output into `evidence/`)
`npm run test:contracts` · `uv run --project services/voice python -m pytest services/voice/tests -v` · your acceptance suite (`tests/acceptance`, document the command) · `uv run --project services/voice python tools/probes/secret_scan.py` (0). Offline items must all pass. Live items are PASS, FAIL or BLOCKED with evidence.

## REPORT.md
The language × stage table with run ids and attempts used; thresholds as set before the run; the review-sheet paths and how many are filled (expected: 0); the filler result and options; measurement errors; latency; a11y findings; what the release data now says and why; code defects found (file:line) that need a FIX. End `PHASE 08 BUILT — AWAITING B3 TEST` or `BLOCKED: credentials not configured` (offline parts done). Stop there. Do not start Phase 09.
