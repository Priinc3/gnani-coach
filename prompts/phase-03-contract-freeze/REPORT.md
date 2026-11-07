# Phase 03 — contract freeze: REPORT

Status: **BUILT, awaiting B1 test.** Nothing in G1 was started. No
commit, no push, no deploy, no delegation.

**Update (2026-10-20):** the freeze was accepted with two gaps; the
**FIX-1** section at the end of this file closes them (the origin
allowlist and the browser-visible voice URL) and applies the W02 and W01
dispositions. Everything above it is unchanged.

Goal link: `prompts/00-plan.md` §2/§9. Requirements list:
`docs/feasibility/HANDOFF.md` §5, §5.1a, §5.2–5.6, plus the decision of
2026-10-20 (filler = unvalidated, goal preserved).

---

## 1. What was built

| # | Deliverable | Where |
|---|---|---|
| 1 | The contract changes from Phase 02, with valid **and** invalid examples for every one | `packages/contracts/**` |
| 2 | The filler capability frozen as `unvalidated`, with a data field reserved for a later validated state | `packages/contracts/data/capabilities.json`, `packages/contracts/schemas/capability-state.schema.json` |
| 3 | Per-provider readiness, the frozen model id, the TTS selector, the VAD object | `services/voice/src/gnani_coach/settings.py`, `docs/contracts/settings.md` |
| 4 | The service ports, with the Phase 02 adapters satisfying them **without editing the providers** | `services/voice/src/gnani_coach/ports/**` |
| 5 | The frozen seams, exactly as named in the BUILD | `docs/contracts/seams.md` + the stubs |
| 6 | The call transport contract and the event-envelope schema | `docs/contracts/call-transport.md`, `packages/contracts/schemas/event-envelope.schema.json` |
| 7 | The UI seams: presets, the transient Custom Topic, the recording-OFF default, the four honest states, the Speakify token baseline | `packages/contracts/data/catalog.json`, `packages/contracts/schemas/session-settings.schema.json`, `apps/web/src/app/globals.css`, `docs/contracts/seams.md` §6–7 |
| 8 | The integration smoke test (pytest + Playwright) | `tests/integration/**` |

---

## 2. Files changed

### 2.1 `packages/contracts/**` (own)

| File | Change |
|---|---|
| `schemas/durable-metrics.schema.json` | Split rate methods and denominators (§5.1); added `denominator`, `recognitionStatus`, `audioSourceClassification`; `turn.duration_ms` on the sample clock (§5.2); `totals.speakingTimeMs` semantics and invariant (§5.3); the filler reason code (§5.4); the turn-level rule that a turn without a measured transcript carries no available rate or filler count. |
| `schemas/analysis-observation.schema.json` | The same four fields, optional per observation and constrained when present; the span-contents and no-word-timing statements; the `inferred` observation may not carry an audio source. |
| `schemas/event-envelope.schema.json` | The frozen transport: `direction`, the 13 event types, the closed per-type payloads, the client `start` payload (audio + settings + the caller's token), the inlined error shape, the turn id required on an audio descriptor. |
| `schemas/session-settings.schema.json` | `scenarioPresetId`, the transient `customTopic` (never persisted), the recording-OFF default, the 10-minute call cap. |
| `schemas/catalog.schema.json` | Scenario `presets` and the transient `customTopic` declaration. |
| `schemas/error-shape.schema.json` | The `not_available` category, never retryable. |
| `schemas/capability-state.schema.json` | **New.** The capability register: state, rendered state, the preserved goal, the acceptance bar, and the rule that a validated state must carry its date and evidence. |
| `data/capabilities.json` | **New.** Six capabilities; the filler capability is `unvalidated` / `insufficient_evidence`, with `validatedAt: null` as the field reserved for a later flip. |
| `data/catalog.json` | The workplace presets (`workplace-team-meeting`, `workplace-office-communication`) and the transient `custom` scenario. |
| `scripts/test-examples.mjs` | The new fixtures are in the required inventory; the capability register is validated and its honesty rules are asserted; the scenario and preset invariants are asserted; the runner fails if any durable example writes an available filler count. |
| `README.md` | The frozen status, the eight schemas, the frozen rules. |
| `examples/**` | 26 valid and 52 invalid fixtures. 42 new files, and 13 updated: nine to the frozen event names and the new turn fields, and ten Phase 01 fixtures given the new required turn fields so that each still fails **for its own reason only** (each was re-checked with Ajv, error by error). |

### 2.2 `services/voice/src/gnani_coach/**`

| File | Change |
|---|---|
| `settings.py` | `speech_readiness()`, `reasoning_readiness()`, `GEMINI_MODEL_DEFAULT` + `resolved_gemini_model()`, the TTS model/voice selector, the VAD settings object, the readiness state vocabulary. |
| `main.py` | Mounts the conversation and persistence routers, exposes `identity_dependency` / `analysis_dependency`, and keeps `/health` byte-identical. |
| `ports/**` | **New:** `types`, `speech_to_text`, `text_to_speech`, `reasoning`, `analysis`, `identity`, `session_store`, `recording_store`, `provider_adapters`, `error_shape`, and the package `__init__`. |

### 2.3 `apps/web/**`

| File | Change |
|---|---|
| `src/app/page.tsx` | Now only renders `CallExperience` with the shared catalog. |
| `src/app/globals.css` | The Speakify baseline and the global design tokens. |
| `src/app/layout.tsx` | Metadata wording only. |
| `src/features/call/index.ts`, `src/features/call/CallExperience.tsx` | **Stub for Phase 04** (§5). |
| `src/lib/auth/index.ts`, `src/proxy.ts` | **Stubs for Phase 06** (§5). |

### 2.4 Root, docs and tests

| File | Change |
|---|---|
| `package.json` | `test:integration`, `test:integration:service`, `test:integration:web`. |
| `playwright.integration.config.ts` | **New.** Boots the web app **and** the voice service. |
| `tests/integration/{conftest,seam_helpers,test_seams}.py`, `tests/integration/call-experience.spec.ts` | **New.** 16 pytest checks + 5 browser checks. |
| `docs/contracts/{README,seams,call-transport,contract-changes,settings,capability-states}.md` | **New.** The human-readable freeze. |
| `prompts/phase-03-contract-freeze/evidence/**` | **New.** The raw command output (§4). |

**Not touched** (verified by hash manifest, §7.4): `services/voice/src/gnani_coach/providers/**`,
`tools/probes/**`, `fixtures/**`, `docs/feasibility/**`, `UI.png`, the CEO files.

---

## 3. The frozen seam table (as frozen)

| Seam | Name / location | Owner after the freeze | Unavailable behaviour |
|---|---|---|---|
| Web mount | `apps/web/src/features/call/index.ts` exports `CallExperience` (React component, no props except `{catalog}`); `page.tsx` renders it | Phase 04 | the stub renders the existing honest starter notice |
| Voice conversation | `gnani_coach/conversation/router.py` exports `router` (FastAPI `APIRouter`) with WebSocket `/ws/call`, mounted in `main.py` | Phase 05 | the stub closes with the error-shape code `not_available` |
| Voice history | `gnani_coach/persistence/router.py` exports `router`: `GET /api/history`, `POST /api/consent`, `GET/DELETE /api/recordings/{id}` | Phase 06 | `503` with error-shape `not_available` |
| Identity | `gnani_coach/identity/__init__.py` exports `get_identity() -> IdentityPort`; injected via FastAPI dependency | Phase 06 | returns the anonymous guest implementation |
| Web auth | `apps/web/src/lib/auth/index.ts` exports `useSession`, `signOut`; `apps/web/src/proxy.ts` placeholder | Phase 06 | guest state |
| Analysis | `gnani_coach/analysis/__init__.py` exports `get_analysis() -> AnalysisPort` | Phase 05 | returns `insufficient_evidence` |

Two documented deviations from the BUILD's table:

1. **The web component lives in `CallExperience.tsx`** and `index.ts`
   re-exports it. The **path and the export name are unchanged**: a `.ts`
   file cannot hold JSX. `apps/web/src/features/call/index.ts` still
   exports `CallExperience`, and `page.tsx` still renders it.
2. **`main.py` also exposes `identity_dependency` and
   `analysis_dependency`** as the single wiring point for the FastAPI
   dependencies. The exported names the BUILD names (`get_identity`,
   `get_analysis`) are unchanged and unchanged in behaviour.

Full detail, including the exact close code and the reason for it, is in
**`docs/contracts/seams.md`** — the only file the G1 builders need.

---

## 4. Commands and raw output

All commands were run from the repository root on 2026-10-20. The full
raw output is in `prompts/phase-03-contract-freeze/evidence/`.

| Command | Result | Evidence file |
|---|---|---|
| `npm run test:contracts` | **PASS** — 8 schemas compiled, 78 examples (26 valid, 52 invalid), 10 languages, 5 scenarios, 6 capabilities; "filler localisation is unvalidated and rendered as insufficient_evidence" | `evidence/test-contracts.txt` |
| `uv run --project services/voice python -m pytest services/voice/tests -v` | **247 passed, 3 skipped** (the 3 skips are the opt-in live provider tests) | `evidence/pytest-services-voice.txt` |
| `npm run lint` | **clean** — 0 errors, 0 warnings | `evidence/web-lint-typecheck-build.txt` |
| `npm run typecheck` | **clean** — `tsc --noEmit` with no output | `evidence/web-lint-typecheck-build.txt` |
| `npm run build` | **PASS** — Next.js 16.4.2 (Turbopack), 3 static pages, the proxy registered | `evidence/web-lint-typecheck-build.txt` |
| `npm run test:integration` | **PASS** — 16 pytest checks + 5 browser checks, with the real web app and the real uvicorn service booted | `evidence/test-integration.txt` |
| `npm run test:e2e` (the Phase 01 foundation suite, unchanged) | **PASS** — 12 passed | `evidence/test-e2e-foundation.txt` |
| `uv run --project services/voice python tools/probes/secret_scan.py` | **0 findings** | `evidence/secret-scan.txt` |
| `npm audit` | 5 high, all in the dev-only lint chain (§7) | `evidence/npm-audit-full.txt`, `evidence/npm-audit-full.json` |
| `npm audit --omit=dev` | **0 vulnerabilities** | `evidence/npm-audit-omit-dev.txt` |

The repository's actual script names are: `dev:web`, `lint`, `typecheck`,
`build`, `test:contracts`, `test:e2e`, `test:integration`,
`test:integration:service`, `test:integration:web`, `check:health`.

The new integration command is:

```sh
npm run test:integration          # pytest seams + Playwright, both processes booted
```

---

## 5. The stubs handed to 04 / 05 / 06

| Owner | Path | What it does now |
|---|---|---|
| Phase 04 | `apps/web/src/features/call/index.ts` | Re-exports `CallExperience`. |
| Phase 04 | `apps/web/src/features/call/CallExperience.tsx` | The honest starter screen: the setup form, the ten catalog languages with honest badges, the **disabled** start action with its plain reason, no microphone request, no fake data — plus the frozen workplace presets and the transient Custom Topic field. |
| Phase 05 | `services/voice/src/gnani_coach/conversation/__init__.py` | Exports `router`. |
| Phase 05 | `services/voice/src/gnani_coach/conversation/router.py` | `/ws/call`: accepts, sends one `error` envelope (`not_available`), closes with **1011**. |
| Phase 05 | `services/voice/src/gnani_coach/analysis/__init__.py` | `get_analysis()` → `insufficient_evidence` for every metric, with the recognition status saying why. |
| Phase 06 | `services/voice/src/gnani_coach/persistence/__init__.py` | Exports `router`. |
| Phase 06 | `services/voice/src/gnani_coach/persistence/router.py` | The four final paths and methods; each answers `503` with the error shape. |
| Phase 06 | `services/voice/src/gnani_coach/identity/__init__.py` | `get_identity()` → the anonymous guest. |
| Phase 06 | `apps/web/src/lib/auth/index.ts` | `useSession()` → the guest state; `signOut()` → a no-op. |
| Phase 06 | `apps/web/src/proxy.ts` | A placeholder that lets every request through. |

The Phase 01/02 test files were **not** edited; the composition root
keeps `/health` byte-identical and the placeholder routes are excluded
from the OpenAPI document, so the Phase 01 invariant
(`openapi()["paths"] == ["/health"]`) still holds and is asserted by the
integration test.

---

## 6. Contract diffs by HANDOFF section number

The full text is in **`docs/contracts/contract-changes.md`**; the summary:

### §5.1 — the denominators are split

| Metric | Method | Denominator |
|---|---|---|
| `speech.rate_wpm` | `stt_words_over_learner_span` | `learner_span_ms` |
| `speech.active_rate_wpm` | `stt_words_over_speech_active` | `speech_active_ms` |

A per-observation `denominator` field was added, and the method
description names the excluded quantities (connection time, session time,
round trips, provider emission times). The pre-freeze identifier
`stt_words_over_speech_regions` is **kept, bound to `speech.rate_wpm`
only**, so a record written before the freeze still validates while the
conflation becomes structurally impossible: the speech-active rate can no
longer be written with it, and the schema rejects the attempt.

*Fixtures:* valid `durable-metrics/valid/split-rate-denominators.json`,
`analysis-observation/valid/rate-with-denominator.json`; invalid
`active-rate-with-overall-method.json` and `rate-with-wrong-denominator.json`
in both schemas.

### §5.1a — recognition status and source trust

* `recognitionStatus` ∈ `measured | no-analyzable-speech |
  missing-transcription`. It is **required on every durable turn** and
  optional-but-constrained per observation.
* **The rate is omitted, not zero**: a turn whose recognition status is
  not `measured` may not carry an available rate or filler count, and an
  observation with a non-measured status may not be `available` and may
  not carry a number. A missing transcription therefore **cannot**
  validate as a measured `0`.
* `audioSourceClassification` ∈ `learner-audio |
  synthetic-learner-audio`, required on every durable turn, forbidden on
  an `inferred` observation, with the description saying in terms that
  **a source label is a declaration, not a proof** — it does not
  establish diarization and it does not establish echo cancellation.
* The span-contents statement: the span **includes** the source's
  leading and trailing silence and **excludes** the end padding.

*Fixtures:* valid `missing-transcription-rate.json` in both schemas and
`analysis-observation/valid/unvalidated-filler.json`; invalid
`rate-zero-with-missing-transcription.json` in both,
`turn-without-recognition-status.json`,
`unknown-source-classification.json` in both, and
`inferred-with-source-classification.json`.

### §5.2 — `turn.duration_ms` is sample-clock based

`turn_connection_timer` is **replaced** by `learner_audio_sample_clock`.
The description states that the value is the elapsed learner audio on the
local sample clock, that the deliberate end padding is excluded, and that
it is never connection time and never session time. A duration may not
carry a rate denominator or a recognition status.

*Fixture:* invalid `turn-duration-with-connection-timer.json`.

### §5.3 — `totals.speakingTimeMs`

Documented as **the sum of detected speech-active time**, explicitly not
the sum of the elapsed turn spans, with the invariant
`speakingTimeMs ≤ Σ turns[].durationMs` stated in the field. The
invariant is a cross-field rule JSON Schema cannot express, so it belongs
to the writer boundary (Phase 05/06); every valid durable fixture keeps
the two consistent. `totals.turnCount` is documented as completed learner
**turns**, never segments.

### §5.4 — identifier and span semantics

* A turn is a conversational turn, not a recogniser segment; the
  provider's `utterance_id` is the closest observed grouping signal, is
  unstable, and is never presented as a turn boundary.
* There is **no word-level timing** in the contract and none is derived;
  the `evidenceSpan` description says the spans are estimated regions.
* A missing or unvalidated filler is `insufficient_evidence` with the
  reason `filler_detection_unvalidated` — **never** `0`.
* `learner_audio_sample_clock` is the controlled provenance id for the
  learner-audio clock, distinct from connection timing.
* The provider's per-segment `latency` is not in the metric-key
  allowlist, so it cannot be written as a metric value.

### §5.5 — settings

`speech_readiness()` (Gnani only) and `reasoning_readiness()` (Gemini
only) exist, never depend on Supabase, and report `unconfigured |
configured | verified`. `configured` means "the credential name is
present"; `verified` is reachable only by passing `verified=True`, which
a caller may do only after a real successful check. `live` is never set
from configuration. `GEMINI_MODEL` is frozen to `gemini-3.8-flash` with
the access date **2026-10-20** and the source
<https://ai.google.dev/gemini-api/docs/models> (the page, last updated
2026-10-19, lists Gemini 3.8 Flash as a stable model with the endpoint
id `gemini-3.8-flash` — it matches the id observed working in Phase 02).
The TTS model/voice selector and the VAD object that survives a
reconnect are in `docs/contracts/settings.md`.

### §5.6 — observed behaviour that must not be encoded

None of it is encoded: the provider's segment index, the absent
`audio_duration_ms`, the lowercased output, the segment/turn split, the
probe-budget arithmetic, the STT-only language row, and the `en-IN`
ambiguity. Each is recorded in `docs/contracts/contract-changes.md` so
nobody "fixes" it later.

---

## 7. The filler state, the audit, and the limits

### 7.1 The filler capability

**State: `unvalidated`. Rendered as: `insufficient_evidence`.**

* `packages/contracts/data/capabilities.json` →
  `capabilities["filler-localization"]`: `state: "unvalidated"`,
  `renderedState: "insufficient_evidence"`,
  `unavailabilityReason: "filler_detection_unvalidated"`,
  `validatedAt: null`, `validatedBy: null`.
* **The goal is preserved and not narrowed:** `goalPreserved: true`,
  `scopeChangeApproved: false`. Narrowing the feature is a scope change
  that needs the owner's explicit approval; this phase did not make one.
* The acceptance bar is recorded and does not move: precision ≥ 90 %,
  recall ≥ 80 %, matched-event boundary p95 error ≤ 300 ms, ≥ 20
  positive and ≥ 20 negative examples per enabled mode.
* **No filler flag is true anywhere.** The catalog's per-language
  capability flags stay `documented`-only, and both the contract runner
  and the integration test assert it. The runner also fails the build if
  any durable example writes an available filler count, and if any
  capability claims `validated`.
* A later validated detector flips **data only** — `state`,
  `renderedState`, `validatedAt`, `validatedBy`, `evidenceRefs` — and the
  schema enforces that a validated state carries its date and evidence.
  The contract shape does not change.

### 7.2 `npm audit` (2026-10-20) — W01 and W02

`npm audit` → **5 high**, all in the same dev-only chain as the Phase 01
evidence:

```
eslint-config-next@16.4.2 → @next/eslint-plugin-next@16.4.2
  → fast-glob@3.3.1 → micromatch@4.0.8 → braces@3.0.3
```

`npm audit --omit=dev` → **0 vulnerabilities**. The production
dependency tree is clean; the advisory is confined to development lint
tooling.

The advisory was re-checked today:
<https://github.com/advisories/GHSA-vfj7-8cjw-p6xm> (CVE-2026-93687,
updated 2026-10-02) still lists **"Affected versions: <= 3.0.3"** and
**"Patched versions: None"**. `eslint-config-next`'s latest published
version is still 16.4.2 — the version we pin — and no 16.x release drops
the `fast-glob` dependency.

**Recommendation (the CEO decides):**

* **W01 — renew, with the same conditions.** The exposure is unchanged
  and dev-only, the production tree is clean, and the only "fix" npm
  offers is `npm audit fix --force`, which **downgrades**
  `eslint-config-next` to 14.2.35 (a semver-major move that would break
  the Next 16 lint configuration) and is therefore not a verified remedy.
  There is no patched `braces` to upgrade to, and an `overrides` entry
  cannot invent one. Suggested wording: renew until the release
  packaging (Phase 09) has proved the lint tooling is not shipped, then
  let the waiver expire rather than renewing it again.
* **W02 — remove by upgrading ESLint, and this is now verified.** ESLint
  v9 has been EOL since 2026-08-06
  (<https://eslint.org/version-support/>, checked 2026-10-20); the current
  line is **v10.x** (`eslint@10.13.0` is `latest`; `9.39.5` is only the
  `maintenance` tag). `eslint-config-next@16.4.2` declares
  `peerDependencies: { eslint: ">=9.0.0" }`, so 10.13.0 is inside the
  supported range. **Verified in this phase:** with `eslint@10.13.0`
  installed and the *unchanged* `apps/web/eslint.config.mjs`,
  `npm run lint` passes with **0 errors and 0 warnings**
  (`evidence/w02-eslint-10-lint-check.txt`; the experiment used
  `--no-save`, so `package.json` and `package-lock.json` were
  byte-identical afterwards and the tree was restored to 9.39.5).
  The exact change, if the CEO approves it, is one line in
  `apps/web/package.json` (`"eslint": "10.13.0"`) plus a lockfile
  refresh, and then W02 lapses instead of being renewed.
* If the CEO prefers not to change the dependency before G1, renew both
  waivers with the same conditions and a hard expiry at the Phase 09
  release packaging. **The code is unchanged either way: nothing in this
  phase altered the pinned versions.**

### 7.3 Limits — what this phase does **not** prove

1. **No provider call was made.** Nothing here proves the live speech
   path works. The Phase 02 verdict stands: Gemini reliability is
   unsettled, no language has been shown intelligible or coachable, and
   no filler detector has passed.
2. **The transport is a contract, not an implementation.** The sequence,
   the heartbeat, the stale-turn suppression and the caps are specified
   and schema-checked, but no browser has yet streamed PCM through them.
   B2 proves that.
3. **The measurements are still synthetic-only.** The pause and rate
   capabilities are `validated_synthetic_only`: the mechanism is proven,
   natural-learner behaviour is not.
4. **The Phase 02 provider package is untracked in git.** The Phase 02
   deliverables were never committed, so `git diff --stat
   services/voice/src/gnani_coach/providers tools` is empty *vacuously*.
   The real evidence that Phase 03 left them alone is the SHA-256
   manifest in `evidence/provider-package-manifest.sha256`; Phase 03
   edited no file in either tree.
5. **The TTS endpoint in the configuration is not the endpoint the
   Phase 02 client dials.** `GNANI_TTS_WS_URL` affects the configuration
   boundary only, because the Phase 02 TTS client connects to its own
   documented default. The provider package is Phase 02's and outside
   this phase's write set; Phase 05 either uses the default or the
   client has to change.
6. **The contract version string stayed at `0.1`.** The schemas are
   frozen, but the `$id` still ends in `/0.1.0`, because the Phase 01
   test `test_schema_inventory_is_draft_2020_12_with_local_refs_only`
   asserts that suffix and that test file is Phase 01's. The freeze is
   recorded in the schema descriptions, in `docs/contracts/` and in the
   contract README.
7. **Two Phase 01 settings assertions are honoured by construction
   rather than by changing the settings:** `settings.gemini.model` stays
   `None` when nothing is configured (the frozen default is a module
   constant applied by `resolved_gemini_model()`), and
   `provider_readiness().state` stays `unavailable` (the combined view
   still folds in Supabase). Both are documented in
   `docs/contracts/settings.md`.
8. **The `customTopic` text is transient by contract, not by
   enforcement.** The schema rejects it in the durable record and pins
   `persisted: false`; whether the runtime also keeps it out of the logs
   and the caches is Phase 05/06's writer-boundary work.
9. **The web design tokens are a baseline, not a finished design.** The
   Speakify palette and type scale are applied once, from the reference
   image, with no web font introduced. Phase 04 still owns the screens,
   the responsive layouts and the illustration assets (which are not in
   the repository).

---

## 8. Help needed

Nothing is blocking. Two items the CEO may want to rule on before G1:

1. **W01/W02** — renew, or remove W02 with the verified ESLint 10.13.0
   upgrade (§7.2). The code is unchanged either way; the decision is a
   disposition, not a build input.
2. **The untracked working tree.** Phases 01 and 02 are in the working
   tree but only Phase 01 is committed. The B1 checker's
   `git diff --stat` ownership check is therefore weaker than it looks;
   the SHA-256 manifest is the honest substitute for the provider
   package, and a commit of the tree before B1 would make the check
   meaningful again. Committing is the CEO's action, not this phase's.

One contract question for G1, raised early rather than as a surprise:
the event payloads are **closed** (an unknown payload key is rejected).
If Phase 04 or Phase 05 needs a field that is not in
`event-envelope.schema.json`, that is a contract change and it needs a
Phase 03 FIX — `HELP:` in `prompts/parallel-G1/`, not a local edit.

---

## 9. Evidence index

`prompts/phase-03-contract-freeze/evidence/`

| File | Content |
|---|---|
| `test-contracts.txt` | `npm run test:contracts` — full output. |
| `pytest-services-voice.txt` | `uv run --project services/voice python -m pytest services/voice/tests -v` — full output. |
| `web-lint-typecheck-build.txt` | `npm run lint`, `npm run typecheck`, `npm run build` — full output. |
| `test-integration.txt` | `npm run test:integration` — full output (16 pytest + 5 browser checks). |
| `test-e2e-foundation.txt` | `npm run test:e2e` — the Phase 01 suite, unchanged, still green. |
| `secret-scan.txt` | `tools/probes/secret_scan.py` — 0 findings. |
| `npm-audit-full.txt`, `npm-audit-full.json`, `npm-audit-omit-dev.txt` | The audit evidence. |
| `w02-eslint-10-lint-check.txt` | The verified W02 removal experiment. |
| `provider-package-manifest.sha256` | The SHA-256 manifest proving the Phase 02 provider package and the probe tools were not edited. |

---

**PHASE 03 BUILT — AWAITING B1 TEST**

---

## FIX-1

Phase 03 FIX-1 — the two seam gaps the review named, plus the two waiver
dispositions.

Status: **BUILT, awaiting B1 test.** G1 was not started. Nothing was
committed, pushed or deployed. The freeze from the section above stands;
this fix only closes the two gaps the review named, plus the two waiver
dispositions.

### FIX-1.1 — Files changed

#### The origin allowlist and the voice-service URL

| File | Change |
|---|---|
| `services/voice/src/gnani_coach/settings.py` | `SPEAKING_COACH_ALLOWED_ORIGINS` (a list, default the local web origin only), `normalize_origin()`, `parse_allowed_origins()`, and the `*` rejection **in the settings parse**. The wildcard raises a `ValidationError`, so the service never starts with one. |
| `services/voice/src/gnani_coach/ports/origins.py` | **New.** The reusable check `origin_allowed(origin: str | None) -> bool` and the helper `allowed_origins()`. The rule is written down in the module docstring. |
| `services/voice/src/gnani_coach/ports/__init__.py` | Re-exports `origin_allowed` and `allowed_origins`. |
| `services/voice/src/gnani_coach/main.py` | The `CORSMiddleware` with exactly the configured list; the settings are parsed once at import (the middleware needs the list before the app starts) and the lifespan publishes the same object on `app.state.settings`; `origin_allowed` is re-exported. |
| `services/voice/src/gnani_coach/conversation/router.py` | The stub checks the `Origin` header **before** `accept()`: a disallowed origin is closed with **1008** (`origin_not_allowed`), so the handshake never completes. An allowed origin keeps today's `not_available`/1011 behaviour byte for byte. |
| `apps/web/src/lib/voice.ts` | **New.** `VOICE_WS_URL` — the browser-visible voice service URL, from `NEXT_PUBLIC_VOICE_WS_URL`, with the development default `ws://localhost:8000/ws/call`. |
| `apps/web/.env.example`, `.env.example`, `services/voice/.env.example` | The new variables are documented. The service example gained `SPEAKING_COACH_ALLOWED_ORIGINS`; the web example gained `NEXT_PUBLIC_VOICE_WS_URL` (and its old "planned name: VOICE_SERVICE_ORIGIN" note is replaced by the frozen name). |
| `docs/contracts/seams.md` | **§6.1** (the browser-visible voice URL), **§8** (the allowlist, the CORS middleware, the handshake check, the missing-`Origin` decision and the citations), one row each in the §1 seam table, and the §2 stub row now names the origin check. |
| `docs/contracts/settings.md` | The `SPEAKING_COACH_ALLOWED_ORIGINS` row and a new §6 with the parsing rules. |
| `docs/contracts/call-transport.md` | §7 rule 6 now points at `seams.md` §8 for the allowlist, the refusal and the missing-`Origin` case. |
| `docs/contracts/README.md`, `tests/integration/README.md` | The index rows and the "what it checks today" list mention the new checks. |
| `playwright.integration.config.ts` | The integration run tells the booted service which web origin to expect (`SPEAKING_COACH_ALLOWED_ORIGINS`), so the browser test works whatever `PLAYWRIGHT_BASE_URL` is. |
| `tests/integration/test_origins.py` | **New.** 18 checks: the setting, the wildcard refusal, the CORS preflight, the handshake, the missing-`Origin` case. |
| `tests/integration/test_voice_url.py` | **New.** 8 checks: the frozen module, the development default, the `.env.example` files, and that **no secret uses the `NEXT_PUBLIC_` prefix**. |

#### The waiver dispositions

| File | Change |
|---|---|
| `apps/web/package.json` | `"eslint": "10.13.0"` — the exact pin the CEO approved. |
| `package-lock.json` | Refreshed with `npm install --package-lock-only` (npm 11.19.1, node v24.22.0). The ESLint 9 dependency tree is replaced by the ESLint 10 tree. |

**Not touched:** `services/voice/src/gnani_coach/providers/**`,
`tools/probes/**`, `fixtures/**`, `docs/feasibility/**`, `UI.png`, the CEO
files, and every UI file. The provider package and the probe tools are
proved unchanged by
`evidence/fix-1/provider-package-manifest.sha256`, which is
**byte-identical** to the Phase 03 manifest.

### FIX-1.2 — The origin rules, as built

**One list, two jobs.** `SPEAKING_COACH_ALLOWED_ORIGINS` is the CORS
allowlist of the HTTP routes *and* the allowlist of the WebSocket
handshake, so the origin that may call `GET /api/history` is exactly the
origin that may open `/ws/call`.

| | |
|---|---|
| The setting | `SPEAKING_COACH_ALLOWED_ORIGINS` |
| The default | **the local web origin only** — `http://localhost:3000` |
| The accepted forms | a JSON array (`["https://a.example"]`) or a comma-separated list (`https://a.example,https://b.example`) |
| The wildcard `*` | **refused while the settings parse** — `load_settings()` raises a `ValidationError` and the service does not start. A wildcard can therefore never reach the middleware or the handshake. |
| A malformed entry | refused in the same place (a path, a query, a fragment, a non-`http(s)` scheme or an empty list). |
| The normalisation | lower-cased scheme and host, the default port for the scheme dropped, no trailing `/`. Both sides of the comparison are normalised, so the match is exact. |

**The one reusable check** — `origin_allowed(origin: str | None) -> bool`,
in `gnani_coach/ports/origins.py`, re-exported as
`gnani_coach.ports.origin_allowed` and `gnani_coach.main.origin_allowed`.
Phase 05's `/ws/call` router calls it **before** `accept()`.

| The `Origin` header | What happens |
|---|---|
| on the allowlist | **allowed** — the stub then sends the frozen `not_available` envelope and closes with **1011**, exactly as before. |
| not on the allowlist | **refused** — the socket is closed with **1008** ("policy violation", reason `origin_not_allowed`) *before* the handshake completes. A real client therefore sees **HTTP 403** (uvicorn answers a close-before-accept with `403`); the ASGI-level test asserts the close code **1008**. |
| malformed | **refused** — the same 1008. |
| **absent (or empty)** | **allowed.** |

**The missing-`Origin` decision, in writing.** A browser *always* sends
`Origin` on a WebSocket handshake and JavaScript cannot remove or
override it — OWASP: "Validate the Origin header on every handshake.
Always use an explicit allowlist of trusted origins. **Browsers include
this header and malicious JavaScript cannot override it.**" So a
handshake **without** an `Origin` header cannot have come from a browser:
it identifies a **non-browser client** (a server-side probe, a native
client, a test client). Such a client has no ambient cookie and no
ambient credential to hijack, and the caller's own token still travels in
the first `start` event, so allowing it does not weaken the browser
threat model, which is cross-site WebSocket hijacking. A missing header
is therefore allowed, and it is **not** a way around the allowlist for a
browser. The rule is in `docs/contracts/seams.md` §8.2.

**The CORS middleware** (`fastapi.middleware.cors.CORSMiddleware`, in
`main.py`):

| Argument | Value | Why |
|---|---|---|
| `allow_origins` | the configured allowlist | never a wildcard — the wildcard is refused at parse time |
| `allow_methods` | `GET`, `POST`, `DELETE`, `OPTIONS` | only the methods the mounted routes use (`GET /health`, `GET /api/history`, `POST /api/consent`, `GET`/`DELETE /api/recordings/{id}`) plus the preflight itself. `PUT`/`PATCH` are not allowed. |
| `allow_headers` | `Authorization`, `Content-Type` | the caller's own bearer token and a JSON body |
| `allow_credentials` | **off** | **the history routes do not need credentials.** They authenticate with a **bearer token in the `Authorization` header, never with a cookie**, so credentialed CORS would widen the attack surface for nothing. With credentials off the middleware echoes the exact allowed origin instead of the wildcard. |
| `max_age` | `600` | the preflight cache |

**Sources, cited in `seams.md` §8:** the OWASP WebSocket Security Cheat
Sheet (<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
checked 2026-10-20) and the FastAPI CORS documentation
(<https://fastapi.tiangolo.com/tutorial/cors/>, checked 2026-10-20).

### FIX-1.3 — The voice-service URL setting

| | |
|---|---|
| The variable | `NEXT_PUBLIC_VOICE_WS_URL` |
| The default | `ws://localhost:8000/ws/call` (the voice service on the developer machine) |
| Read by | `apps/web/src/lib/voice.ts`, which exports `VOICE_WS_URL` |
| Inlined | yes — Next.js inlines a `NEXT_PUBLIC_*` value into the browser bundle **at build time** |
| A secret? | **No.** It is the URL of a service the browser is allowed to call. |

* It is documented in `docs/contracts/seams.md` **§6.1** and in
  `apps/web/.env.example` (the root `.env.example` points at it).
* **No secret uses the `NEXT_PUBLIC_` prefix.** `NEXT_PUBLIC_VOICE_WS_URL`
  is the only `NEXT_PUBLIC_` value in the repository, and
  `tests/integration/test_voice_url.py` proves it: it scans every
  `.env.example` and every `.ts` file of the web app, and it fails if
  another public variable appears or if a public name looks like a
  secret (`KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `CREDENTIAL`, `PRIVATE`).
  The service-side example must not contain a public variable at all.
* The URL carries no credential: the caller's own token travels in the
  first `start` event, never in the URL.

### FIX-1.4 — Commands and raw output

All commands were run from the repository root on **2026-10-20**, with
node **v24.22.0** (the version in `.nvmrc`) and npm **11.19.1**. The
raw output is in `prompts/phase-03-contract-freeze/evidence/fix-1/`.

| Command | Result | Evidence file |
|---|---|---|
| `npm run lint` | **PASS** — 0 errors, 0 warnings, with **eslint 10.13.0** | `evidence/fix-1/01-npm-lint.txt` |
| `npm run typecheck` | **PASS** — `tsc --noEmit`, no output | `evidence/fix-1/02-npm-typecheck.txt` |
| `npm run build` | **PASS** — Next.js 16.4.2 (Turbopack), 3 static pages, the proxy registered | `evidence/fix-1/03-npm-build.txt` |
| `npm run test:contracts` | **PASS** — 8 schemas, 78 examples (26 valid, 52 invalid), 10 languages, 6 capabilities | `evidence/fix-1/04-npm-test-contracts.txt` |
| `npm run test:integration` | **PASS** — **42 pytest checks** (16 old + 18 new origin checks + 8 new voice-URL checks) and **5 browser checks** | `evidence/fix-1/05-npm-test-integration.txt` |
| `npm run test:e2e` | **PASS** — 12 passed (the Phase 01 foundation suite, unchanged) | `evidence/fix-1/06-npm-test-e2e.txt` |
| `uv run --project services/voice python -m pytest services/voice/tests -v` | **PASS** — 247 passed, 3 skipped (the 3 skips are the opt-in live provider tests) | `evidence/fix-1/07-pytest-services-voice.txt` |
| `uv run --project services/voice python tools/probes/secret_scan.py` | **0 findings** | `evidence/fix-1/08-secret-scan.txt` |
| the ESLint tree after the W02 pin | `npm ls eslint`, `npm ls --all` (exit 0), both `eslint --version` calls, and the lint run | `evidence/fix-1/09-w02-eslint-10-tree.txt` |
| `npm audit` | 5 high — the **same** dev-only `braces` chain (W01) | `evidence/fix-1/10-npm-audit-full.txt` |
| `npm audit --omit=dev` | **0 vulnerabilities** | `evidence/fix-1/11-npm-audit-omit-dev.txt` |
| the files this fix touched, with their SHA-256 | — | `evidence/fix-1/12-files-changed.txt` |
| the provider package and the probe tools | unchanged — the manifest is byte-identical to the Phase 03 one | `evidence/fix-1/provider-package-manifest.sha256` |
| the handshake against the **real** uvicorn server | an allowed origin is accepted and closes with **1011**; `https://evil.example` is **rejected with HTTP 403** | `evidence/fix-1/13-ws-handshake-real-server.txt` |
| the CORS middleware against the **real** uvicorn server | the allowed origin gets `200` + `access-control-allow-origin`; `https://evil.example` gets `400 Disallowed CORS origin`, and a simple request from it carries no CORS header | `evidence/fix-1/14-cors-preflight-real-server.txt` |

**Nothing failed, so nothing was reverted.** The `--force` flag was never
used.

### FIX-1.5 — The waiver dispositions

#### W02 — removed, as ordered

`apps/web/package.json` now pins `"eslint": "10.13.0"` exactly, and the
lockfile was refreshed with `npm install --package-lock-only` (then
`npm install` to materialise it). The ESLint 9 dependency tree is
replaced by the ESLint 10 tree in `package-lock.json`.

* `npm run lint` passes with **0 errors and 0 warnings** on
  **eslint 10.13.0** (`evidence/fix-1/01-npm-lint.txt`,
  `evidence/fix-1/09-w02-eslint-10-tree.txt`).
* `npm ls --all` exits **0** — no missing or invalid peer dependency in
  the tree.
* **One honest detail.** npm's resolution keeps a copy of **eslint
  9.39.5 hoisted at the repository root**, because
  `eslint-config-next@16.4.2` declares `peerDependencies: { eslint:
  ">=9.0.0" }` and npm keeps that peer instance where the old lockfile
  had it. The copy is **never executed by a repository script** —
  `npm run lint` resolves `apps/web/node_modules/.bin/eslint`, which is
  **10.13.0** (both versions are printed in the evidence file). Removing
  the hoisted copy entirely would need a root `overrides` block, which
  the disposition did not authorise, so it was not added. The waiver is
  therefore removed **for the pinned, running ESLint**, and the leftover
  transitive copy is reported here rather than hidden.

#### W01 — renewed, as ordered

Renewed until the **Phase 09 release packaging**, with the same
conditions. **No code change** was made for W01. The audit is unchanged:
5 high, all in the same dev-only chain
(`eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch →
braces`), and `npm audit --omit=dev` is **0 vulnerabilities**.

### FIX-1.6 — Limits of this fix

1. **The origin check is not authentication.** It stops a browser on
   another origin from opening the socket; the caller's own token in the
   first `start` event is still the authentication control.
2. **A missing `Origin` header is allowed.** That is the decision above,
   and it is deliberate and documented — a browser cannot produce it.
3. **The settings are parsed at import.** The CORS middleware needs the
   allowlist before the application starts, and a middleware cannot be
   added after startup. A bad value therefore fails at import, not at the
   first request — and it fails *loudly*, which is the point.
4. **The allowlist is compared by normalised string.** There is no
   wildcard, no suffix matching and no regular expression, so a
   subdomain of an allowed origin is **not** allowed.
5. **The browser-visible URL is a build-time value.** Next.js inlines it,
   so changing it needs a rebuild, not a restart.
6. **The `NEXT_PUBLIC_` rule is enforced by a test, not by a linter.**
   The test scans the `.env.example` files and the web app's TypeScript
   sources; a `NEXT_PUBLIC_` value introduced in a file outside those
   paths would not be caught by it.
7. **The CORS credentials question is answered for today's routes.**
   `allow_credentials` is off because the history routes use a bearer
   token. If Phase 06 ever moves to a cookie, that decision has to be
   revisited — and the wildcard may never be used to "make it work".

---

**PHASE 03 FIX-1 BUILT — AWAITING B1 TEST**

---

## FIX-2

Phase 03 FIX-2 brings the frozen integration assertions in line with the
three real seams G1 shipped. No schema, name, route or port was changed.

### Changed files

| File | Change |
|---|---|
| `tests/integration/seam_helpers.py` | `assert_error_shape` now takes the expected `code`, `category` and `retryable`, so a guest `401` is asserted field by field instead of only being JSON. |
| `tests/integration/test_seams.py` | History, consent and recording routes assert `401` + `unauthenticated`; a new guest `DELETE /api/recordings/x` check; the recording route still never returns audio; the socket's first message is `status connecting`; the analysis check asserts the three rules (`turn.duration_ms` available, both rates `unavailable`/`stt_unavailable`, filler `insufficient_evidence`/`filler_detection_unvalidated`). |
| `tests/integration/test_origins.py` | The foreign-origin simple request is `401`; the allowed and missing-origin sockets assert `status connecting`; two new real-service checks: an allowed origin with an invalid `start` closes `1008`, and a wrong sample rate answers `unsupported_audio_format`. |
| `tests/integration/call-experience.spec.ts` | The real landing heading is asserted, Start is enabled and leads to the scenario picker, the guest history is `401 unauthenticated`, and the socket's first message is `status connecting`. |
| `tests/integration/README.md` | What the suite checks today now describes the real guest/analysis/socket behaviour. |
| `tests/foundation/starter-screen.spec.ts` | The ten Phase 01 stub-screen tests are retired (mapping below); the two catalog checks stay and still run against the real landing screen. |
| `.env.example`, `services/voice/.env.example` | Added `SUPABASE_PUBLISHABLE_KEY=` with a server-side-only comment. |
| `apps/web/.env.example` | Added `SUPABASE_URL=` and `SUPABASE_PUBLISHABLE_KEY=` as **server-side** values, with a comment stating plainly that they are not `NEXT_PUBLIC_`. |
| `docs/contracts/seams.md` | §2 no longer says the real routes join OpenAPI; §3 records the `save_metrics` owner; §8.4 and the new §9 record the four CEO decisions of 2026-10-22 (OpenAPI exclusion, request-context owner, `status connecting`, real 16 kHz mono 16-bit WAV). |

### Verification (full output in `evidence/fix-2/`)

| Command | Result | Output |
|---|---|---|
| `npm run test:contracts` | **PASS** — 8 schemas, 78 examples (26 valid, 52 invalid), 10 languages, 6 capabilities | `evidence/fix-2/01-test-contracts.txt` |
| `npm run test:integration` | **PASS** — **45 pytest checks** and **5 browser checks** (real service + real Next.js app booted) | `evidence/fix-2/02-test-integration.txt` |
| `npm run test:e2e` | **PASS** — 2 passed (the two retained catalog checks) | `evidence/fix-2/03-test-e2e.txt` |
| `npm run lint` | **PASS** — 0 errors, 0 warnings | `evidence/fix-2/04-lint.txt` |
| `npm run typecheck` | **PASS** — `tsc --noEmit`, no output | `evidence/fix-2/05-typecheck.txt` |
| `npm run build` | **PASS** — Next.js build, 3 static pages, proxy registered | `evidence/fix-2/06-build.txt` |
| `uv run --project services/voice python -m pytest services/voice/tests -v` | **PASS** — 500 passed, 4 skipped (opt-in live provider tests) | `evidence/fix-2/07-pytest-services-voice.txt` |
| `uv run --project services/voice python tools/probes/secret_scan.py` | **0 findings** | `evidence/fix-2/08-secret-scan.txt` |

### Retired `tests/foundation` tests and their Phase 04 successors

| Retired Phase 01 test | Covered by |
|---|---|
| `shows the honest headline and no fake data visuals` | `apps/web/tests/flow/call-flow.spec.ts` — the landing heading and the summary's no-score/no-confidence/no-pronunciation rules |
| `start call is visibly unavailable with a plain reason` | `apps/web/tests/flow/call-flow.spec.ts` (Start is enabled and opens the scenario picker) + `apps/web/tests/flow/a11y.spec.ts` (keyboard flow) |
| `requests no microphone access on load, even after interaction` | `apps/web/tests/flow/privacy.spec.ts` — `the microphone is opened only after the learner asks for the call` |
| `recording retention is off by default, explained, and keyboard-toggleable` | `apps/web/tests/flow/call-flow.spec.ts` — checkbox unchecked, then `recording kept for replay`; keyboard path in `a11y.spec.ts` |
| `practice language select is focusable, labeled, and updates the plan` | `apps/web/tests/flow/call-flow.spec.ts` — the Speaking language select; focus/keyboard in `a11y.spec.ts` |
| `coaching language follows practice until changed manually` | `apps/web/tests/flow/call-flow.spec.ts` — Tamil follows, then the manual English choice |
| `scenario radios are keyboard operable` | `apps/web/tests/flow/a11y.spec.ts` (keyboard flow) + `call-flow.spec.ts` (scenario radio selection) |
| `sample preview is optional and clearly labeled` | No successor: the sample preview was a Phase 01 stub element that Phase 04 removed; the test is obsolete, not weakened |
| `layout does not overflow a 360px-wide screen` | `apps/web/tests/flow/a11y.spec.ts` — `no screen overflows horizontally`, whose viewports include 360×740 |
| `honours reduced-motion preference` | `apps/web/tests/flow/a11y.spec.ts` — `the reduced-motion preference is honoured` |

**Kept, re-pointed to the real landing screen:** `lists all ten catalog
languages with honest verification badges` and `does not offer French or
any french language code`.

**Nothing failed, so no assertion was weakened and no service file was
edited around a failure.**

**PHASE 03 FIX-2 BUILT — AWAITING B2 TEST**
