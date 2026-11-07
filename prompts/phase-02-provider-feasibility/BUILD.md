# Phase 02 — Provider and audio-evidence feasibility

Type: **NORMAL** · Batch: **B1 (01 → 02 → 03)** · Status: **READY FOR MANUAL EXECUTION**

## Context and goal

You are the **Phase 02 engineer only**. The user said `next` after the scoped Phase 01 FIX-1 review. This admits the next construction step inside B1; it does not mean B1 has passed acceptance. Do not launch another agent, start Phase 03 or build the UI.

Read these files before working:

1. `prompts/00-plan.md` — goal, privacy, measurements, frozen ownership map.
2. `prompts/phase-01-foundation/REPORT.md` and the **current**, not historical, section of its `VERIFY.md`.
3. `prompts/waivers.md`, `prompts/stack-decisions.md`, `prompts/language-support.md`.
4. This phase's `SOURCES.md` and the primary documentation it links.
5. Existing `settings.py`, the voice dependency files and shared draft schemas.

**Goal:** establish whether real Gnani STT → Gemini → Gnani TTS works through reusable backend adapters, and whether audio-grounded pause/filler evidence is technically credible. Deliver a bounded diagnostic harness and a candid feasibility decision **before** later agents build on assumptions.

The app's final goal is a hands-free coaching call with periodic feedback/retry, all ten target languages where validated, metrics-only persistence by default and recording retention only on opt-in. This phase is **backend/provider and measurement feasibility**, not that finished experience.

## Sibling context and scope lock

**Siblings running now: none.** No COMM/STATUS folder for this NORMAL phase.

| Phase | State | Relevant boundary |
|---|---|---|
| 01 foundation | Scoped corrections reviewed; awaiting B1 TEST | Existing settings, schemas, health-only app and test infrastructure are read-only inputs |
| 03 contract-freeze | Not running | Owns final shared schemas, settings/composition changes and integration seams after your evidence |
| 04 call-ui | Locked in G1 | Will implement the user-selected `UI.png`; do not restyle or enable today's UI |
| 05 coaching-runtime | Locked in G1 | Will implement production conversation/analysis state machines after feasibility |
| 06 private-history | Locked in G1 | Owns accounts and persistence; **not a dependency for your speech probes** |

### Your OWN files — exclusive allowlist

- `services/voice/src/gnani_coach/providers/**` — reusable provider adapters and their internal transport/data helpers.
- `services/voice/tests/providers/**` — isolated provider/transport/probe checks, with scoped fixtures/config if needed inside this directory.
- `tools/probes/**` — local CLI, analytical prototypes, replay/measurement tooling, and ignored `.cache/` model assets.
- `fixtures/synthetic/**` — synthetic scripts, manifests, permitted generated audio and annotations.
- `docs/feasibility/**` — setup, exact dependency/model sources, results, contract recommendations and go/no-go decision.
- `services/voice/pyproject.toml` and `services/voice/uv.lock` — **planned sequential handoff** for necessary researched provider/audio dependencies only. Retain the current Python 3.12 family and existing foundation dependencies unless a scoped compatibility decision is approved.
- `prompts/phase-02-provider-feasibility/REPORT.md` and `prompts/phase-02-provider-feasibility/evidence/**` — your required report and evidence.

**DO NOT TOUCH:** `settings.py`, `main.py`, `packages/contracts/**`, foundation tests, root/npm/runtime/ignore files, `apps/web/**`, Supabase, future conversation/analysis/identity/persistence directories, `UI.png`, any other phase's files, or CEO-owned prompts/tracker/waivers/SOURCES. Do not patch shared contracts to fit your adapter. Record needed changes for Phase 03.

All writes must resolve inside the repository and your allowlist; inspect existing uncommitted work first. Tool side effects count. Use the existing environment/version manager without changing global aliases or installing another runtime. Do not stage/commit/push, overwrite old evidence, force-add ignored audio, or touch the historical outside-repository incident path.

Need an out-of-scope change? Write **`HELP NEEDED: path — reason — smallest change`** in REPORT and stop that portion. No silent scope expansion.

## Critical existing-code facts

- `load_settings(env_file=...)` already handles optional configuration. Reuse it; the service otherwise reads process environment, not an implicit `.env`.
- Inspect `settings.voice` and `settings.gemini` separately. The foundation's `provider_readiness()` deliberately stays unavailable and its `configured` calculation includes Supabase. **Do not use that aggregate function to require Supabase credentials for speech.** Do not modify it in this phase.
- Required secret names for live speech/reasoning are **`GNANI_API_KEY`** and **`GEMINI_API_KEY`**. `GEMINI_MODEL` is a nonsecret model selector, not proof of access. An existing user-created ignored env file may be passed explicitly through your CLI; document the exact option in `docs/feasibility/SETUP.md`. Never print env contents or key values.
- No Supabase project, URL or privileged key is needed now. Do not provision services or purchase credits. Existing platform/tool connections are not a substitute for the repository's configured provider credentials.
- The shared schemas remain draft v0.1. Produce provider-internal diagnostic events and propose mappings; do not invent schema fields or flip shared catalog capability flags.

## Deliverables

### A. A small, explicit local probe interface

Implement one root-invoked CLI, **`tools/probes/run.py`**, with the commands listed below. It must be useful with no keys: help, local fixture preparation, protocol fakes and configuration diagnostics work offline. However, absent live evidence must yield `BLOCKED`/`NOT RUN`, never a simulated “live passed.”

- No inference, microphone capture or large model download at import/startup/test collection.
- Live inference requires an explicit **`--allow-live`** switch. A model-asset download requires an explicit preparation option, source/license/hash records and an ignored cache; never silently fetch models during an offline command.
- Proposed probe safeguards: at most **40 provider operations** and **300 seconds of submitted STT audio** per live invocation, bounded output sizes, timeouts, bounded queues and at most two retries for a transient operation. Print a content-free plan/count before calls; count retries against the allowance. Never retry authentication/invalid-input failures indefinitely or silently increase limits.
- Live commands must refuse an over-limit plan before starting; report actual operations/audio consumed. Keep an aggregate run index so repeated invocations are visible. These are safety limits, not pricing estimates or permission to buy more credit.
- Only prepared synthetic fixtures are accepted in this phase. Reject arbitrary external URLs/file paths and unknown fixture IDs; resolve fixture paths against the manifest and authorized directories, including symlink checks. No learner microphone or real recorded-call collection.
- Distinguish `PASSED`, `FAILED`, `BLOCKED`, `NOT RUN` and `INCONCLUSIVE`. A requested live suite with missing credentials/fixtures must exit nonzero and identify the missing **name**, not leak its value. `--help` and deliberately offline inventory can still succeed.

### B. Reusable Gnani realtime adapters

Build under `providers/`, independent of CLI output, FastAPI routes and future UI. Async lifecycle/cancellation, injectable transports for deterministic protocol checks, and explicit error categories are required. No silent REST fallback or replacement STT/TTS provider.

**STT:** use the current documented realtime path, header authentication and language codes. Preserve spoken-form output (`verbatim`) with substitution off for baseline analysis. Do not bias the recognizer with known expected fillers during an accuracy evaluation.

- The checked docs specify **raw mono signed 16-bit little-endian PCM**, **1,024-byte frames** (512 samples), paced to their actual sample rate; at 16 kHz this is 32 ms/frame. Start the reference probe at 16 kHz, and document conversion/source offsets for other supported inputs. Never send a WAV header as a stream frame. [P1]
- Send and receive concurrently; retain observed segment IDs/indexes and server emission times as metadata. Preserve a separate local audio sample clock, recording genuine length versus any end padding. Do not derive word positions from response timestamps/duration or infer gap locations from network delays.
- A VAD-closed segment is not a conversational turn. Try a controlled internal pause and a short answer, recording premature segmentation or lost speech. Keep the 15-minute documented connection ceiling separate from the shorter probe budget.
- Avoid guessing SDK capabilities: the reviewed docs say the Python SDK does not expose VAD tuning. Use a documented low-level transport if that is needed; verify the chosen package's actual version/API before installing it. [P1]

**TTS:** use a verified model/voice pairing and the documented streaming messages. Start with the documented v2.5 family where the account permits it; v3.0 is an explicit capability alternative, not an automatic upgrade. Record actual selection and access evidence.

- Handle start/audio/complete/error messages, base64 decoding, chunk order and one in-flight synthesis per connection. Record first **nonempty** audio-chunk arrival and total bytes/duration. Verify the actual container/header behavior before feeding chunks into a decoder. [P2]
- Evaluate incremental PCM delivery for the future browser. The documented OGG/Opus option may arrive as one chunk at completion; do not label that as proven low-latency incremental audio. [P2]
- Implement consumer-side cancellation/fencing so stale chunks are not forwarded. No undocumented provider “cancel” frame. Evaluate closing/reopening or safely draining a canceled request; distinguish **stopping consumption** from **canceling provider computation/billing**. [P2]
- Do not expose keys, headers, raw exception dumps or full audio in default logs. Save only approved synthetic diagnostic artifacts in this phase.

### C. Gemini reasoning adapter and one real chained turn

- Use the current supported Google GenAI Python SDK/API documented for the selected model. Research and pin a compatible version; do not substitute a deprecated SDK from memory. Choose a documented, account-accessible text-capable model and record its exact ID. Do not enable Gemini Live/TTS as a replacement for Gnani. [P3]
- Accept transient recognized text and scenario/language instructions, return a bounded reply, and support timeout/cancellation. No external tools, web browsing, shell execution or database permissions for the conversation model. Learner speech cannot override storage rules or request secrets. [P6]
- For the chain probe, send **actual Gnani-recognized text** to Gemini and **actual Gemini reply text** to Gnani TTS. Do not pass the known fixture script in place of recognition or play a pre-recorded response while claiming an API chain.
- Record the stage timings, selected models/voice, redacted/nonsecret diagnostics and synthetic output references. At least one complete chain must be evidenced for a successful live-feasibility result.
- Backend first-byte timings are **not browser first-audible latency**. A chained fixture turn is not a working hands-free app. The current frontend/health route must remain unchanged.

### D. Synthetic fixture set and audio-first feasibility

Keep analytical prototypes under `tools/probes/`, not the future production `analysis/` tree. Use Silero VAD for speech-region estimates; prefer a documented CPU/ONNX-compatible path if practical, but verify package/model/license compatibility rather than assuming its footprint. Record the installed versions and model-asset identity. VAD is not filler recognition. [P4]

- Create `fixtures/synthetic/manifest.json` with fixture IDs, synthetic origin, language, actual sample rate/channels/duration, asset hash, generator/version and label provenance. Existing ignore rules exclude audio extensions; leave generated audio ignored, preserve the manifest/recipe and do not amend root ignore rules or force-add audio.
- Include silence, synthetic noise, a clear sentence, one-word speech, a known internal gap, repetition, filled hesitation, lexical “like” versus filler “like,” and at least one code-mixed example. Offline analytic fixtures may be generated without speech providers; real spoken fixtures need an explicitly prepared speech source.
- Insert silence/gaps using known sample indices and preserve those facts across chunking/conversion. A TTS input script is **not proof** the resulting audio contains every hesitation; normalization may remove it. Labels for actual filled sounds need listening/independent review, and the reviewer/source must be identified. Never use the candidate's own prediction as unquestioned ground truth.
- Measure learner clip span, detected speech-active time, internal-pause positions and duration error against known labels. Compute overall word rate from the learner speech span and speech-active rate from speech-active duration as **different denominators**; never include assistant audio or use total network/connection time. Synthetic manipulation boundary labels are not automatically exact natural speech onset labels.
- Evaluate **one bounded audio-aware filler-localization candidate**, beyond simply counting the cleaned transcript. Gemini clip review is permitted as an explicitly labeled candidate; a separately researched alignment component may be proposed with its language/model/license requirements. Do not silently add another paid speech provider, train/fine-tune a model or deploy a second inference service.
- A forced aligner maps supplied text to audio; it does not establish missing fillers that STT omitted. Unknown/ambiguous events stay unknown. No calibrated-confidence percentages, “confidence scores,” pronunciation grades or guaranteed improvement claims. [P7]
- Keep calibration examples separate from holdout examples. Where valid labels exist, report event precision/recall, matching rules and timing errors; the plan's target is ≥90% precision, ≥80% recall and matched-event p95 boundary error ≤300 ms, with at least 20 positive and 20 negative examples **per enabled filler mode**. Do not claim this threshold passed with a smaller/unlabeled pilot. The purpose now is to expose feasibility, not to fabricate full all-language validation.
- If the candidate fails, reliable labels are unavailable, or a language lacks a credible approach, say **NO-GO** or **INSUFFICIENT EVIDENCE** and recommend the cheapest next decision. Do not silently weaken the target, label transcript-only output audio analysis, or declare the original goal met by pauses alone.

### E. Capability matrix and contract handoff

Create `docs/feasibility/CAPABILITIES.md` and a machine-readable companion within your OWN docs/tools paths. Include **all ten catalog languages**, plus a separate Hinglish row, even if some cells are NOT RUN. Read IDs from the shared catalog rather than reauthoring it.

Track independently: documented support, configured credentials, observed STT result, observed TTS model/voice, Gemini response language, verified coaching quality, filler preservation, audio localization and limitations. A successful request in one language proves nothing about the other nine. API access and a synthetic roundtrip do not prove human intelligibility/teaching quality; name what still needs review.

Provide `docs/feasibility/HANDOFF.md` with actual provider event examples from synthetic probes, adapter lifecycle/interfaces, frame/clock rules, cancellation behavior, timeout/limit decisions, and **requested** shared-contract/settings changes. Include:

- Per-provider readiness, without requiring unrelated Supabase settings.
- Separation of overall rate, speech-active rate, elapsed learner span and detected speaking time; do not freeze the current draft's conflated method descriptions.
- Missing event/span/identifier semantics and what the provider cannot supply.
- Where a validated prototype could be promoted in Phase 05 without maintaining duplicate measurement implementations. Do not move code into another phase's tree yourself.
- `UI.png`/Speakify remains the Phase 03/04 visual target; observed capabilities must drive honest loading/error/insufficient-evidence states rather than mock scores.

Finally, `docs/feasibility/DECISION.md` must answer four questions with evidence links: **Can the account support the real speech chain? Can delivery measurements be anchored to audio? Is filler localization credible under the stated target? Which languages/capabilities remain unproven?** Give GO / NO-GO / INSUFFICIENT EVIDENCE per question; this is not a CEO VERIFIED verdict.

## Privacy and security constraints

- Synthetic, nonpersonal input only. No real names, account details, recorded calls or sensitive personal audio in fixtures/prompts/logs. Provider terms and contest recording rules remain unresolved for a real-user launch.
- Review the Gemini account's applicable paid/unpaid data terms before any real-user phase. The checked terms warn against personal/confidential input in Unpaid Services and distinguish it from Paid Services; “we do not save audio” cannot mean “providers retain nothing.” [P5]
- Do not send a whole recording to an optional audio reviewer if a bounded synthetic clip suffices. Record any provider-side stored-object creation and its cleanup behavior; do not promise zero retention without evidence.
- Validate endpoint/host configuration and never forward a provider key to a user-selected host or redirect. Use test transport injection with dummy credentials for local protocol failure scenarios. All provider output is untrusted data, not permission to execute tools or alter files.
- Use offline transport fakes for malformed payloads, floods, 429/timeout/cancellation races and auth failures. Do not load-test or fuzz the live provider, spend until rate limited, or retry in an unbounded loop.
- Existing W01/W02 development waivers do not authorize new vulnerabilities or dependency changes in that lint chain; leave npm dependencies untouched. W03 requires exact new evidence, not another excerpted/mislabeled “final recheck.”

## Commands and evidence contract

Make the following **repository-root invocations** real and document them in `docs/feasibility/SETUP.md`. The orchestrator has not run them and does not assert they already exist.

**Environment and offline development diagnostics:**

- `uv sync --project services/voice`
- `uv run --project services/voice python tools/probes/run.py --help`
- `uv run --project services/voice python tools/probes/run.py preflight`
- `uv run --project services/voice python tools/probes/run.py fixtures --offline`
- `uv run --project services/voice python tools/probes/run.py analysis --offline`

`preflight` prints configured/missing names and intended endpoints/model selection, never secret values; it makes no inference call. Offline analysis must report absent speech fixtures/model assets as missing, not auto-download or call providers. Document explicit model/fixture preparation options and any optional env-file flag in SETUP with no secret-valued example.

**Live commands — only with configured credentials and explicit consent to these bounded synthetic probes:**

- `uv run --project services/voice python tools/probes/run.py fixtures --allow-live`
- `uv run --project services/voice python tools/probes/run.py speech --language en-IN --allow-live --max-requests 8`
- `uv run --project services/voice python tools/probes/run.py chain --language en-IN --allow-live --max-requests 8`
- `uv run --project services/voice python tools/probes/run.py matrix --allow-live --max-requests 40`

Optional audio-review inference is a separate explicit `analysis --allow-live` operation. The `matrix` plan must fit the limits before execution and may return incomplete/NOT RUN cells honestly. Successful offline tests never justify skipping required real probes in the feasibility verdict.

**Author checks for B1** under your test directory: framing/pacing/partial tail handling, concurrent receive and close, duplicate/out-of-order events, cancellation fencing, empty/invalid TTS chunks, malformed/oversized responses, invalid language/voice, missing configuration, timeout/retry bounds, endpoint/key confinement, redaction and prompt-injection behavior without tools. Keep all inference off in the default test suite. Mark live checks explicitly and require opt-in.

Batch entry points remain:

- `uv run --project services/voice python -m pytest services/voice/tests`
- `npm run test:contracts` under the existing LTS runtime.

Run implementation diagnostics as necessary, recording what actually ran. The **formal B1 TEST** remains after Phase 03; do not create a per-phase TEST/VERIFY or self-certify acceptance. Where credentials or labels are missing, finish safe offline work and REPORT **BLOCKED** with the smallest user action. Do not wait indefinitely or substitute a mock success.

For every captured operation: exact command/working directory, runtime versions, UTC timestamps, flags/model selection, exit status, full stdout/stderr and relevant artifact references. Never omit failure output or suppress it with a tail/grep pipeline; keep secrets redacted with a stated redaction policy. Use synthetic payload captures only, separately from content-free default logs. Preserve initial failures alongside later successful attempts.

## Required REPORT.md

Always write **`prompts/phase-02-provider-feasibility/REPORT.md`**, even if blocked. Include:

1. **Status:** `BUILT — AWAITING B1 TEST`, `BLOCKED`, or `BUILT WITH NO-GO FEASIBILITY`; never `✅ VERIFIED`.
2. **Ownership:** exact changed files, generator/cache/model-download side effects, dependencies/locks and any HELP request. No blanket clean-state claim without evidence.
3. **Provider access:** configured vs observed outcomes, exact nonsecret models/voices/protocol details, missing variable names only; no API keys.
4. **Commands/output:** complete new evidence index, failures, NOT RUN/BLOCKED reasons and total provider operations/audio submitted.
5. **Speech chain:** traceable synthetic input → real STT text → real LLM reply → real TTS chunks, or the precise failing stage. Label backend timing, not audible browser latency.
6. **Audio analysis:** fixture/annotation provenance, source hashes, measured boundary/count errors, held-out sample counts, candidate results and uncertainties. Distinguish speech regions, recognized words, inferred observations and confirmed filler events.
7. **Language matrix:** every target language/mode represented; never infer all-ten success from one roundtrip.
8. **Decision and handoff:** links to SETUP/CAPABILITIES/HANDOFF/DECISION; explicit shared-contract issues for Phase 03, including metric denominators and readiness separation.
9. **Limits/help:** real-user data terms, unimplemented call UI/runtime/history, missing credentials/labels/access, and cheapest next option if the audio approach fails.
10. **Process state:** confirm which connections/processes were closed; do not leave the probe running or a live relay exposed.

Stop after REPORT. No next phase, app deployment, code commit/push, shared-contract edit or automatic delegation.
