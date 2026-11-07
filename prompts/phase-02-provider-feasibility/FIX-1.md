# Phase 02 — FIX cycle 1: trustworthy bounds, evidence and handoff

Type: **NORMAL** · Batch **B1** · Owner **Phase 02 only**

**READY FOR OFFLINE REPAIR. LIVE PROBES ON HOLD.** Read current `VERIFY.md`, `DECISION-NEEDED.md`, `prompts/provider-access.md`, original BUILD and the current tracker. Correct P02-01–P02-07 in this cycle. The no-go feature decision is not yours to override.

Siblings running: **none**. Phase 03 and G1 are paused. No COMM/STATUS folder. No automatic delegation, deployment, commit/push or new model training.

## Scope

OWN: the existing `providers/**`, `services/voice/tests/providers/**`, `tools/probes/**`, `fixtures/synthetic/**`, `docs/feasibility/**`, the voice `pyproject.toml`/`uv.lock` for a researched necessary compatibility change, and your own REPORT/new `evidence/fix-1/**`.

DO NOT TOUCH: shared settings/main/contracts, foundation tests, npm/runtime/global/ignore files, web/UI, `UI.png`, Supabase, other phase files or CEO prompts/waivers. Preserve earlier evidence and the uncommitted work of Phase 01. Do not visit/delete arbitrary external credential files or kill processes by broad name; only processes you started and positively identified may be stopped.

The user privately supplies replacements through the process environment or user-created `tools/probes/.env` (already ignored; mode `0600`). Agents must not populate secrets by copying the conversation into files. Do not inspect/reveal secret-file contents in tool output. Offline fakes use unmistakably dummy, noncredential sentinel values.

## 1. Credential and scope disposition — P02-01

- Keep all four posted values out of prompts, code, tests, logs, evidence and reports. Request **rotation/configuration status**, not replacement values. No live use until the owner confirms rotation/replacement privately.
- Correct contradictory ownership language. Identify who created the reported external temp credential file, what authorization existed and whether actual cleanup evidence exists. If unknown, say unknown. SETUP's “deleted” sentence is not evidence. Do not fabricate or recreate cleanup.
- Provide an in-repository credential-leak check whose output contains only paths, line numbers, rule IDs and counts. Never print matching text or embed real secrets in commands/tests. A clean repo scan cannot erase conversation exposure.
- Update SETUP to document private environment injection and the user-managed local option in `provider-access.md`; no blanket instruction to create outside-repository files. Fix its duplicated contradictory `--env-file` ordering example.

Verify-with: content-suppressed scan output, accurate inventory/cleanup account and user rotation status. CEO/user handles any provider-dashboard action; you must not silently revoke or create keys.

## 2. Enforce budgets at the actual attempt boundary — P02-02

- Choose one retry authority. Prefer disabling hidden SDK retries and performing explicitly budgeted retries at the adapter boundary, or use a documented per-attempt hook with demonstrated accounting. Verify the installed SDK's semantics; do not assume “attempts” equals “retries.”
- Each wire attempt must be admitted by the same budget before it starts. Record logical calls, actual attempts, connections and retries distinctly. A timed-out attempt still counts. Unknown historical wire counts must be labeled unknown, not reconstructed as zero.
- Calculate speech/chain plans using the exact framed **submitted** audio including trailing silence and the actual five-stage-operation minimum before retries. Refuse an over-limit plan before any side effect.
- Reserve child allowances or share atomic accounting; do not hand out the same remaining allowance twice. Do not clamp absorption to hide overspend. Check finite/nonnegative inputs and every global maximum, including connection limits.
- Derive exact new totals from the immutable run ledger. Correct REPORT/HANDOFF's blanket claims and keep historical estimates visibly historical.

Verify-with offline transport/client fakes: one remaining operation with a retrying upstream; over-limit chain refused with zero calls; audio limit equal to genuine duration but less than padded duration; simultaneous children; failed/partial attempts; negative/nonfinite limit input; accounting after cancellation. Check observed fake wire attempts, not just the budget object's own counter.

## 3. Repair lifecycle and error behavior — P02-03

- Inspect the supported async API of the actual pinned Google GenAI SDK, using https://github.com/googleapis/python-genai and https://googleapis.github.io/python-genai/index.html. Prefer documented async transport/context-manager cleanup where supported. Do not swap API surfaces based on memory.
- Remove the fresh unbounded daemon-per-call workaround. If blocking work is unavoidable, bound outstanding workers/clients, retain a slot until work actually ends, safely fence late completion, and close resources. A caller timing out must not silently free capacity still used by abandoned work.
- Never call a closed event loop from a late worker. Close clients on success/error/cancellation. A late model response must not reach TTS for a canceled turn.
- Distinguish a bounded local wait, closed local connection, and provider-side cancellation/billing. Do not advertise “cancels cleanly” when only the wait ended.
- Use a documented, configurable overall deadline suitable for a feasibility probe, keeping the app's eventual ≤3-second voice target distinct from this diagnostic deadline. Align actual defaults, command output and docs; a 70-second timeout is not successful call responsiveness.

Verify-with repeated offline timeouts/cancellations in **one long-lived event loop**, late replies after cancellation, success/error cleanup, bounded worker/client counts and loop shutdown. Do not rely on process exit or killing a shell as proof of reusable-service safety.

Sources: Python 3.12 https://docs.python.org/3.12/library/threading.html and the Google SDK references above. If the supported cancellation surface cannot meet this boundary, stop with evidence/options rather than silently adding another abandonment layer.

## 4. Make matrix and language results truthful — P02-04

- Aggregate all **requested required stages**, not STT alone. Any requested TTS/reasoning failure produces a failed/inconclusive aggregate and corresponding nonzero exit; skipped/unavailable stages cannot count as successful coverage.
- Separate parameter-acceptance smoke checks from actual language fixtures and quality review. English audio/text sent with a Tamil parameter must not become evidence of Tamil speech accuracy. Use matching-language synthetic speech/text where available; otherwise retain NOT RUN labels and explain the missing fixture.
- Resolve practice/reply language IDs, display names and STT/TTS codes through the existing catalog. Reject invalid combinations before requests; keep Hinglish's separate STT/TTS mapping. Do not edit the catalog yourself.
- Preserve partial-stage results and errors. A failed Gemini row must remain failed even when STT and TTS succeeded. No empty model response counted as successful reasoning.

Verify-with offline all-stage combinations, including the captured Tamil-shaped failure; native-fixture-missing vs parameter-only status; display name/code inputs and invalid mappings. Any later live check uses repaired bounds and fresh private credentials.

## 5. Preserve the no-go truth; prepare the decision — P02-05

- Amend DECISION/HANDOFF to say “fillers absent from recognition; actual rendered filler presence not reviewed.” Do not assert the speaker hesitated twice, permanent recognizer incapability, or that only one research approach can work.
- Keep the heuristic as an unvalidated candidate. Do not tune against holdout labels or invent a reviewer. Zero reviewed examples means the target is not evaluable, not a measured zero-filler success.
- Make the current clip's path/hash/duration and review status easy to find. If the user provides the requested annotation, record provenance without altering the original audio. One reviewed clip does not satisfy the 20-positive/20-negative requirement.
- Stop further detector investment pending the user's direction in DECISION-NEEDED. A narrowed product needs explicit approval and a revised plan; repairing scaffolding does not resolve the goal-level block.

Verify-with artifact/annotation integrity and the absence of unearned filler-success/capability flags. This item may remain **BLOCKED ON USER** while the code repairs finish.

## 6. Preserve reproducible evidence — P02-06

- Write new runs to immutable run-ID locations under `evidence/fix-1/`; never overwrite a prior success/failure. Store exact commands, working directory, runtime, exit code and full redacted stdout/stderr. Index failures and cancellations as well as successes.
- For an approved synthetic chain, record fixture hash/locale, per-stage attempt IDs, actual recognized text/reply and their references, bytes/chunks/timestamps. Never use the intended fixture script in place of recognition. Keep raw keys/headers and private provider metadata out.
- Clearly separate documentation samples from actual captured frames. Do not label `req_abc123` or a copied 2024 timestamp as a live capture. If original raw frames/stdout are missing, say so; a new replay creates new evidence, not a replacement history.
- Fix REPORT's relative document links and reconcile totals with the ledger. Qualify unmeasured internal retries and historical output loss.
- Every command and live count must be reproducible. Do not hide failures behind filtered output, shell pipelines that discard statuses, or summaries that only count successful cells.

## 7. Repair measurement source checks — P02-07

- Require an explicitly trusted learner/synthetic-learner source for these probes; reject empty, assistant-only, mixed or unknown source classifications. Do not claim a string label establishes diarization or echo cancellation.
- Distinguish missing transcription/no analyzable speech from a genuine measured zero. Keep overall-vs-active denominators separate and state whether leading/trailing source silence is included. Preserve end padding exclusion.
- Add negative source/unknown-recognition cases without editing shared schemas; communicate any required final DTO change to Phase 03.

## Optional reasoning comparison — prepared, not automatically authorized

The user supplied additional providers and asked for documentation; `prompts/provider-access.md` records the official Groq/NVIDIA sources. **Do not silently change the application's primary provider or assume these variables already have adapters.**

If the user explicitly chooses “compare reasoning providers” and private rotated credentials are configured, add a small probe-only comparison within your OWN tree: corrected Gemini, one supported Groq text model and one hosted NIM text model, on identical short synthetic inputs and bounded output/deadline settings. Verify exact model endpoints, account access and data terms first; record no-tools behavior, failure types, first-text/complete-text latency and reply-language evidence. Keep all attempted calls within the repaired shared budget.

No automatic fallback race, no raw audio to a text-only model, no replacement of Gnani speech, no self-hosted NIM/GPU provisioning and no production model selection. Otherwise report the comparison **NOT RUN — awaiting user decision**. Credentials alone are not a completed integration.

## Verify-with commands and reporting

Run from repository root, under the existing project toolchain:

- `uv run --project services/voice python -m pytest services/voice/tests/providers -v`
- `uv run --project services/voice python -m pytest services/voice/tests -v`
- `npm run test:contracts` using the existing Node 24 LTS selection, without a runtime reinstall.
- `uv run --project services/voice python tools/probes/run.py preflight`

Preflight remains non-inference and must not reveal values. Live examples, **only after rotation and budget/lifecycle repairs**, use the top-level env flag before the subcommand:

- `uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env chain --language en-IN --fixture spoken-clear-sentence --voice Kaveri --tts-model timbre-v2.5 --allow-live --max-requests 8`

Use offline fakes for the failing-stage matrix/race/budget checks; do not spend credit to trigger provider throttling. This is corrective verification, not the formal three-phase B1 TEST. No TEST-RESULT or VERIFIED verdict is authored by you.

**Always update `prompts/phase-02-provider-feasibility/REPORT.md`** with P02-01–P02-07 dispositions; changed files; commands and raw output; rotation status without values; actual attempt accounting; measured cleanup/bounds; missing evidence; live successes/failures; and blocked user decisions. Use `FIX-1 COMPLETE — AWAITING CEO REVIEW` or `BLOCKED`, retaining the explicit filler no-go where unresolved. Missing rotation/labels cannot be converted into success.

Stop after REPORT. Do not start Phase 03, alter the goal/phase map, run the UI agent, approve a waiver or loop into another fix on your own.
