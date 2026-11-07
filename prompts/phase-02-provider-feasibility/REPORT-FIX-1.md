# Phase 02 — FIX cycle 1 report

Working directory for every command: repository root
(`/Users/princegondaliya/Learning/Projects/temp/gnani`).
Executor: Phase 02 agent (FIX cycle 1). Dates: 2026-10-18 (original
Phase 02 runs) and 2026-10-20 (this cycle). All timestamps in evidence
are UTC.

Docs delivered: [`docs/feasibility/SETUP.md`](../../docs/feasibility/SETUP.md) ·
[`CAPABILITIES.md`](../../docs/feasibility/CAPABILITIES.md) ·
[`HANDOFF.md`](../../docs/feasibility/HANDOFF.md) ·
[`DECISION.md`](../../docs/feasibility/DECISION.md)

> **Link note — checked, not assumed.** The FIX-1 brief asked for the
> document links to be fixed because they were "broken", with the remedy
> given as three levels up. That remedy was **checked against the
> filesystem and it does not resolve**: this file lives at
> `prompts/phase-02-provider-feasibility/REPORT.md`, so the repository
> root is **two** levels up, and `../../../docs/…` points outside the
> repository.
>
> ```
> $ cd prompts/phase-02-provider-feasibility
> $ ls -d ../../docs/feasibility/SETUP.md   -> resolves
> $ ls -d ../../../docs                       -> No such file or directory
> ```
>
> Every document link in this report was therefore **verified to
> resolve**, and the two-level form is used. The instruction's *intent*
> — working links — is satisfied; its *stated remedy* was not, and it was
> not applied blindly. All links are checked by
> `tools/probes/check_report_links.py`.

---

## 1. Status

# `FIX-1 COMPLETE — AWAITING CEO REVIEW`

This cycle repaired findings **P02-01 … P02-07** in the Phase 02
provider-feasibility tree. **Every repair is offline.** No live provider
call was made, because the credential rotation status is unconfirmed and
the owner has not confirmed replacement credentials.

**What this report does not do.** It does not author a `TEST-RESULT` or
`VERIFIED` verdict, and it does not convert a missing rotation status or
a missing reviewer into a success. The Phase 02 feature decision is
unchanged:

| Question (`DECISION.md`) | Verdict | Changed this cycle? |
|---|---|---|
| Can the account support the real speech chain? | **GO** (plumbing) · **INCONCLUSIVE** (reliability) | no — re-verification needs fresh credentials |
| Can delivery measurements be anchored to audio? | **GO** (on signals with known labels) | no |
| **Is filler localisation credible under the stated target?** | **NO-GO** | **no — the NO-GO stands and is preserved** |
| Which languages/capabilities remain unproven? | **INSUFFICIENT EVIDENCE** | wording corrected only |

> **The filler NO-GO is retained.** This cycle repaired the *scaffolding*
> around it. It did not evaluate it, did not create a reviewer, did not
> tune against holdout labels, and did not narrow the product. The
> statement is now precise: **the fillers are absent from recognition;
> the actual rendered filler presence was not reviewed.**

---

## 2. Dispositions — P02-01 … P02-07

### P02-01 — Credential material and the scope/cleanup record — **REPAIRED (record) · ROTATION UNCONFIRMED**

| Item | Before | After |
|---|---|---|
| The four posted values in the repo | never present in the tree (verified again this cycle) | unchanged — and the tree is now **scanned** every cycle |
| In-repo leak check | did not exist | `tools/probes/secret_scan.py`, content-suppressed |
| External temp credential file | described as "outside the repository … deleted it after the probes" | **status UNKNOWN, unverified**; author and authorisation stated separately; no external file visited |
| Credential provisioning | "keep this file outside the repository" | user-controlled only: process environment, or a user-created `tools/probes/.env` (mode `0600`, already ignored) |
| `--env-file` ordering example | duplicated and contradictory | one correct example: `--env-file <path> <subcommand>` |

**Credential exposure record (status only — no values, ever).**

| Question | Answer | Basis |
|---|---|---|
| Who wrote the reported external temporary credential file? | The Phase 02 build agent | the Phase 02 build record is the only account of that session |
| What authorisation existed for it? | **Not specific.** The user authorised *demo use* of credentials; no authorisation for an external write is on record | no grant covering an external file exists |
| Was it actually deleted? | **UNKNOWN — unverified** | the previous "deleted it after the probes" sentence is a **claim, not cleanup evidence**. No receipt, no listing, no existence check |
| Was its content inspected? | **No** | no external credential file was opened, read or revealed in this cycle |
| Have the four posted values been rotated? | **UNKNOWN — awaiting the owner** | only the owner can act on a provider dashboard |

**What this cycle deliberately did not do:** it did not visit, list, open
or delete any file outside the repository; it did not kill any process;
it did not fabricate or re-do the cleanup. Fabricating evidence of a
cleanup that may not have happened would make the record worse.

**In-repo leak check** — `tools/probes/secret_scan.py`. Output contains
**only** repository-relative paths, line numbers, rule identifiers and
counts. The matched text is never printed, never echoed and never
stored, so a finding cannot leak the value it reports. Rules:
`GOOGLE_API_KEY`, `GROQ_API_KEY`, `NVIDIA_API_KEY`, `BEARER_TOKEN`,
`X_API_KEY_ID`, `JWT`, `GENERIC_SECRET`. The user's private
`tools/probes/.env` is **skipped, never read**.

> **A clean scan does not erase the conversation exposure.** It says "no
> leak found in the tree", nothing more.

### P02-02 — One retry authority, one attempt boundary — **REPAIRED**

| Item | Before | After |
|---|---|---|
| Retry authority | SDK retried internally (`attempts=2`, invisible to any counter) **and** the adapter could retry — two authorities | **the adapter boundary is the only authority**; the SDK is configured `HttpRetryOptions(attempts=1)`, the SDK's own documented "no retries" value |
| Attempt accounting | one counter, debited once per logical call | **four distinct counters**: `logical_calls_used`, `wire_attempts_used`, `connections_used`, `retries_used` |
| Attempt admission | none — the budget was debited *after* the fact | `admit_attempt()` is called **immediately before every wire attempt**; a refused attempt never reaches the provider |
| Timed-out attempt | not counted | **counted** — the provider may still be working on it |
| Child allowance | handed out, not reserved | **reserved from the parent at creation**, so two concurrent children can never be handed the same remaining allowance |
| Absorption | clamped, hiding overspend | never clamps; an overrun is **recorded and reported** (`OverrunRecord`) |
| Limit validation | partial | every limit checked **finite and nonnegative**, and against every global maximum **including connections** |
| Chain plan | planned **4** operations while its own evidence recorded **5** | plans **5** (STT connect, STT session, reasoning attempt, TTS connect, TTS synthesise) |
| Audio plan | sized on the clip's duration, ignoring the trailing silence | sized on the **framed submitted** audio, including the trailing silence and the frame pad |
| Over-limit plan | could fail after credit was spent | refused **before any side effect**; `--max-requests` is a caller ceiling that *tightens* the budget |
| Historical wire counts | reported as an approximation | **"unknown"**, never reconstructed as zero (`attempts_measured=False` → `wire_attempts_source: "unknown"`) |

**The SDK's retry semantics were verified, not assumed.** Against the
pinned `google-genai` 2.31.0 source, `HttpRetryOptions.attempts` is
documented as *"Maximum number of attempts, **including the original
request**. If 0 or 1, it means no retries."* Constructing a client
offline yields `stop_after_attempt(1)` with no `retry_options`,
`stop_after_attempt(1)` with a timeout only, `stop_after_attempt(1)` for
`attempts=1` and `stop_after_attempt(2)` for `attempts=2`. The previous
code's label *"SDK-internal retry attempts = 2"* was wrong on two counts:
the value was **total attempts**, not retries, and the SDK's retry was
invisible to the budget in any case.

### P02-03 — Lifecycle, cancellation and timeout honesty — **REPAIRED**

| Item | Before | After |
|---|---|---|
| Transport | a fresh **unbounded daemon thread per call** | the SDK's **documented async surface**: `Client.aio` → `AsyncClient`, `await client.aio.interactions.create(...)` |
| Client cleanup | never closed | closed on **every** exit path — success, error, timeout, cancellation — via `await client.aio.aclose()` **and** `client.close()` |
| Concurrency | unbounded workers | bounded by a semaphore (`max_concurrent_calls`, default 2); a slot is held until the work **actually ends** |
| Closed loop | a late worker could call into a closed event loop | the request is awaited directly, so it is cancellable; a late completion is fenced and never returned |
| Cancelled turn → TTS | not fenced | the turn is **fenced** on cancellation; a late reply is never adopted, so it can never reach the TTS stage |
| Timeout meaning | "the outer wait ended" | distinguishes a **bounded local wait**, a **closed local connection**, and **provider-side cancellation** — the last is never claimed, and **no claim is made about billing** |
| Overall deadline | a fixed **70 s** outer wait | a **documented, configurable** deadline: 15 s per attempt, **45 s** for the whole call (`chain --attempt-timeout`, `chain --call-deadline`) |
| The ≤3 s app target | conflated with the probe bound | kept **distinct**: the 45 s figure is a feasibility-probe diagnostic bound, explicitly *not* the app's voice-turn target, and is asserted to be so in a test |

**The async surface was read from the installed SDK, not from memory.**
`google/genai/_api_client.py` and the `AsyncClient` in
`google/genai/_gaos/google_genai.py` provide `.aio`, `.aio.interactions`
(with an async `create`), `aclose()`, `__aenter__`/`__aexit__`;
`Client.close()` is sync-only.

**One real defect was found by the new tests while fixing this item:** a
cached `asyncio.Semaphore` stayed bound to a dead event loop, so a coach
reused across loops would fail. The semaphore is now rebuilt whenever
the running loop changes.

### P02-04 — Matrix aggregation and catalog-resolved languages — **REPAIRED**

| Item | Before | After |
|---|---|---|
| Row success | derived from **STT alone** | derived from **every requested stage** — `sttNativeFixture`, `ttsNativeText`, `geminiLanguage` |
| A failed TTS/reasoning stage | masked by a successful STT | makes the row **FAILED** and the aggregate exit **nonzero** |
| An empty model reply | not distinguished | `NO MODEL TEXT` — **not** a pass |
| Parameter acceptance | mixed into the coverage columns | separate `sttParameterAccepted` / `ttsParameterAccepted` columns, **never** coverage |
| A missing native fixture | English audio was substituted | the row is **NOT RUN** with the missing fixture named; English audio is never substituted |
| Language ids / codes | a literal `"English"` → `"en-IN"` mapping; other names unresolved | resolved **through the shared catalog** by id, display name, native name, STT code or TTS code; the catalog is read, never edited |
| Ambiguous codes | silently settled by list order | refused as **ambiguous** with both ids named (`en-IN` is the STT code of both English and Hinglish) |
| Hinglish | risk of being conflated with English | keeps its **separate** mapping — STT `en-IN`, TTS `hi-en` — and neither is presented as the other |

**Verification is offline** and covers all-stage combinations, the
captured Tamil-shaped failure (STT answered, reasoning timed out →
FAILED, nonzero exit), native-fixture-missing versus parameter-only,
display-name/code inputs, and invalid mappings.

### P02-05 — Preserve the no-go truth — **REPAIRED (wording) · GOAL DECISION STILL BLOCKED ON USER**

| Claim the previous wording made | Now |
|---|---|
| "the recogniser did not preserve the fillers" | **"the fillers are absent from recognition"** |
| implied the rendered audio was checked | **"the actual rendered filler presence was not reviewed"** |
| "a speaker who hesitated twice" | removed — no claim is made about how many hesitations were spoken |
| "the recogniser dropped it" / permanent incapability | removed — the two causes remain undistinguished, and **no permanent-incapability claim** is made |
| "the only route that could satisfy the target" | **"a route that could satisfy the target"** — Option D is one candidate among several, and real audio analysis is also under investigation |
| the heuristic | still an **unvalidated candidate**; not tuned against holdout labels; **no reviewer was invented** |
| "zero fillers" | **"zero reviewed examples means the target is not evaluable — not a measured zero-filler success"** |

**The clip under review is now easy to find:**

| Property | Value |
|---|---|
| Fixture id | `spoken-filled-hesitation` |
| Path | `fixtures/synthetic/audio/spoken-filled-hesitation.wav` |
| Duration | **3,680 ms** |
| sha256 | `82900f998131e7f512a2bee278e16f5bc849a5475510272ac5d321b53018ab56` |
| Review state | **NOT REVIEWED** — `verified_by: null`, `filler_labels_verified: false`, `review_state: UNVERIFIED-FILLER-LABEL` |

Recording the user's annotation later does not alter the original audio.
**One reviewed clip is one clip:** it resolves this fixture's ambiguity
and does not create the ≥20 positive / ≥20 negative labelled examples
the target requires.

**This item remains BLOCKED ON USER** — see §8.

### P02-06 — Reproducible, immutable evidence — **REPAIRED**

| Item | Before | After |
|---|---|---|
| Result files | fixed names, **overwritten** | **immutable run-ID directories** under `evidence/fix-1/<run-id>/`; a prior success, failure or cancellation is never overwritten |
| What a run records | lengths and timings only | exact argv, working directory, runtime, exit code, overall state, full **redacted** stdout/stderr, and the attempt accounting |
| The index | successes only | the append-only `evidence/fix-1/run-index.jsonl` indexes **failures and cancellations too** |
| Chain evidence | no fixture hash, no recognised text, no raw-frame reference | fixture id + sha256 + language code, the **actual** recognised text and model reply, per-stage status and wire attempts, bytes/chunks/timings, and the per-attempt outcomes |
| Documentation samples | mixed with captures | **labelled separately**: `req_abc123` and the `2024-01-15T10:30:00.000Z` timestamp are **DOC SAMPLE**, not captures |
| REPORT document links | the brief's stated remedy was "go up three levels" | **checked against the filesystem**: the report lives at `prompts/phase-02-provider-feasibility/`, so the root is **two** levels up and `../../../docs/…` does not resolve. The two-level form is used and every link is **verified to resolve** by `tools/probes/check_report_links.py` |
| Totals | "~110 operations", "retries: 0" | reconciled against the immutable ledger; historical wire counts are labelled **UNKNOWN** |
| Evidence redaction | one blunt policy that masked every long identifier | `redact_evidence()` — credential **shapes** and secret-ish **assignments** are masked, opaque blobs are masked, and test node ids stay readable so the evidence remains evidence |

**Reconciliation with the ledger.** The Phase 02 ledger
(`evidence/run-index.jsonl`, preserved untouched) holds **38
invocations**, of which **20 were live** (`allow_live: true`) and **18
were offline**. Of the 20 live invocations, 5 exited non-zero. The
earlier "~110 operations" figure was an **estimate of visible stages**,
not a measurement of wire attempts; the true wire-attempt counts for
those runs are **UNKNOWN** and are reported as such.

### P02-07 — Measurement source checks — **REPAIRED**

| Item | Before | After |
|---|---|---|
| Source set | rejected only when two *distinct labels* were present; an **empty** set and an **assistant-only** set were accepted | `assert_trusted_learner_source()` requires an **explicitly trusted** learner / synthetic-learner source and refuses **empty**, **assistant-only**, **mixed** and **unknown** classifications, each with its own stated reason |
| Identity claim | implied a label proves speaker identity | a source label is a **declaration**: the module states in terms that it does **not** establish diarization and does **not** establish echo cancellation |
| Missing recognition | indistinguishable from a measured zero | `recognition_status` distinguishes `measured`, `no-analyzable-speech` and `missing-transcription`; only `measured` yields a rate |
| Denominators | overall and active could be conflated | kept separate, and the span now **states** whether the source's leading/trailing silence is included (it is) and that **end padding is excluded** (it is) |
| Shared schemas | — | **not edited.** The required DTO change is written up for Phase 03 in `HANDOFF.md` §5.1a: a per-observation status with the rate **omitted** rather than zero for the two non-measured states, the clip's source classification, and an explicit span-contents statement |

A transcript that exists but holds no word tokens is a **genuine
measured zero** (`0.0`); a transcript that does not exist is **not**.

---

## 3. Changed files — this cycle only

**Modified**

| Path | Change |
|---|---|
| `services/voice/src/gnani_coach/providers/limits.py` | rewritten: four distinct counters, `begin_call`/`admit_attempt` with call tokens, immediate child reservation, honest absorption, full limit validation, `"unknown"` history |
| `services/voice/src/gnani_coach/providers/gemini.py` | rewritten: documented async SDK surface, `attempts=1`, adapter-level budgeted retries, bounded concurrency, guaranteed client close, fencing, configurable deadline |
| `services/voice/src/gnani_coach/providers/stt.py` | budget call sites migrated to `begin_call`/`admit_attempt`; the plan is sized on the framed submitted audio |
| `services/voice/src/gnani_coach/providers/tts.py` | budget call sites migrated |
| `services/voice/src/gnani_coach/providers/redaction.py` | added `redact_evidence()` — a credential-shape policy that keeps test node ids readable |
| `services/voice/tests/providers/test_safety_boundaries.py` | migrated to the new budget API; async fakes; new retry/token and "two calls are not a retry" tests |
| `services/voice/tests/providers/test_stt_protocol.py` | one assertion updated to the new counter name |
| `services/voice/tests/providers/test_tts_protocol.py` | one assertion updated to the new counter name |
| `tools/probes/run.py` | `plan_budget` reworked (requirement vs ceiling, padded audio); immutable evidence written for every invocation; catalog selectors; `--attempt-timeout` / `--call-deadline` |
| `tools/probes/live/probes.py` | matrix rewritten: all-stage aggregation, parameter-acceptance columns, non-zero exit on any requested-stage failure, immutable evidence, catalog-resolved codes |
| `tools/probes/capabilities.py` | carries the parameter-acceptance / historical-attempt caveats into `capabilities.json` |
| `tools/probes/analysis/metrics.py` | rewritten: trusted-source guard, recognition status, span-contents statements |
| `tools/probes/offline.py` | the threshold finding is now scoped to *this* candidate detector |
| `docs/feasibility/SETUP.md` | credential record, user-controlled provisioning, corrected `--env-file` ordering, leak check, new limits and evidence sections |
| `docs/feasibility/HANDOFF.md` | DOC SAMPLE vs LIVE CAPTURE separation, the new timeout/lifecycle table, the budget semantics, the **§5.1a DTO request for Phase 03** |
| `docs/feasibility/DECISION.md` | P02-05 wording repaired; Option A made findable; the "only route" claim removed |
| `docs/feasibility/CAPABILITIES.md` | the historical totals are qualified (parameter acceptance, STT-derived aggregation, unknown attempts) |
| `prompts/phase-02-provider-feasibility/REPORT.md` | this file |

**Created**

| Path | Purpose |
|---|---|
| `services/voice/tests/providers/test_budget_attempts.py` | P02-02 verification, including fake-client wire-attempt counts |
| `services/voice/tests/providers/test_gemini_lifecycle.py` | P02-03 verification in one long-lived event loop |
| `services/voice/tests/providers/test_measurement_sources.py` | P02-07 negative cases and recognition-status cases |
| `services/voice/tests/providers/test_probe_contracts.py` | P02-01 / P02-04 / P02-06 verification |
| `tools/probes/evidence.py` | immutable run evidence and the append-only ledger |
| `tools/probes/secret_scan.py` | the content-suppressed in-repo leak check |
| `tools/probes/live/languages.py` | catalog-driven language resolution, including ambiguity refusal |
| `tools/probes/capture_fix1_evidence.py` | captures the verification commands as immutable evidence |
| `tools/probes/check_report_links.py` | verifies that every relative link in this report resolves |
| `tools/probes/patch_report_placeholders.py` | fills this report's run ids and totals from the immutable ledger, so no number in it is typed by hand |
| `prompts/phase-02-provider-feasibility/evidence/fix-1/**` | 75 immutable run directories + `run-index.jsonl` |

**Not touched:** `settings.py`, `main.py`, `packages/contracts/**`,
foundation tests, root npm/runtime/ignore files, `apps/web/**`,
`UI.png`, Supabase, other phases' files, CEO-owned prompts, tracker,
waivers and `SOURCES.md`. The Phase 01 uncommitted work in the tree was
left exactly as found. Nothing was staged, committed, pushed or
deployed; no delegation and no model training.

---

## 4. Commands and raw output

All four commands the brief names, plus the leak scan and the report-link
check, were captured as immutable evidence by
`tools/probes/capture_fix1_evidence.py`.

| # | Command | Exit | Evidence |
|---|---|---|---|
| 1 | `uv run --project services/voice python -m pytest services/voice/tests/providers -v` | **0** | `evidence/fix-1/20261020T075602Z-pytest-providers-cde246a94b-1dec16/` |
| 2 | `uv run --project services/voice python -m pytest services/voice/tests -v` | **0** | `evidence/fix-1/20261020T075607Z-pytest-services-004797f835-3332b5/` |
| 3 | `npm run test:contracts` (Node **24.22.0** LTS, no reinstall) | **0** | `evidence/fix-1/20261020T075613Z-test-contracts-51c2c4cae7-14f677/` |
| 4 | `uv run --project services/voice python tools/probes/run.py preflight` | **0** | `evidence/fix-1/20261020T075613Z-preflight-428e90440a-6f0020/` |
| 5 | `uv run --project services/voice python tools/probes/secret_scan.py` | **0** | `evidence/fix-1/20261020T075613Z-secret-scan-ed172a5c4d-c75594/` |
| 6 | `uv run --project services/voice python tools/probes/check_report_links.py` | **0** | `evidence/fix-1/20261020T075614Z-report-links-ae50cfd9b3-2c186d/` |

Each directory holds `run.json` (argv, cwd, runtime, exit code, overall
state, notes), `stdout.txt`, `stderr.txt` — all redacted. The full
ledger is `evidence/fix-1/run-index.jsonl`.

### 4.1 `pytest services/voice/tests/providers -v` — tail

```text
services/voice/tests/providers/test_tts_protocol.py::test_a_second_synthesis_is_rejected_while_one_is_in_flight PASSED [ 99%]
services/voice/tests/providers/test_tts_protocol.py::test_the_synthesis_request_is_charged_to_the_budget PASSED [100%]

======================== 224 passed, 3 skipped in 5.19s ========================
```

### 4.2 `pytest services/voice/tests -v` — tail

```text
services/voice/tests/providers/test_tts_protocol.py::test_a_second_synthesis_is_rejected_while_one_is_in_flight PASSED [ 99%]
services/voice/tests/providers/test_tts_protocol.py::test_the_synthesis_request_is_charged_to_the_budget PASSED [100%]

======================== 247 passed, 3 skipped in 5.75s ========================
```

### 4.3 `npm run test:contracts` — full output

```text
> speaking-coach@0.1.0 test:contracts
> npm run test --workspace @gnani/contracts

> @gnani/contracts@0.1.0 test
> node scripts/test-examples.mjs

Contract draft example runner (draft v0.1, JSON Schema 2020-12, Ajv strict + ajv-formats)
schemas compiled: 7 (analysis-observation, catalog, durable-metrics, error-shape, event-envelope, recording-metadata, session-settings)
examples checked: 46 (15 valid, 31 invalid)
catalog: 10 languages, 1 code-mixed mode(s), 4 scenarios, 3 levels
note: shape-only fixture: session-settings/valid/shape-only-french-id-passes.json documents that a structurally well-formed id is not catalog membership; membership and staleness are runtime checks.
note: format fixtures: invalid/space-separated-emitted-at.json proves date-time format checking is active in Ajv.
PASS — all contract examples and catalog invariants hold
```

### 4.4 `run.py preflight` — full output

```text
== probe run ==
  run_id       : 20261020T075613Z-preflight-428e90440a-6f0020
  started_utc  : 2026-10-20T07:56:13Z
  python       : 3.12.12
  cwd          : /Users/princegondaliya/Learning/Projects/temp/gnani
  command      : run.py preflight
  exact argv   : ['preflight']
  inference calls are made only by an explicit --allow-live command

== configuration (names only, no values) ==
[missing     ] GNANI_API_KEY — value never printed
[missing     ] GEMINI_API_KEY — value never printed
[missing     ] GEMINI_MODEL — no model id is defaulted by design
[PASSED      ] SUPABASE_* — not required for any speech or reasoning probe
[NOT RUN     ] provider_readiness() — deliberately unavailable; unused by probes
[NOT RUN     ] env file — process environment only

== intended endpoints and model selection ==
  STT websocket : wss://api.vachana.ai/stt/v3/stream
  TTS websocket : wss://api.vachana.ai/api/v1/tts
  Gemini model  : (unset)
  documented Gemini candidates: gemini-3.8-flash, gemini-3.5-flash-lite, gemini-3.6-flash
  inference calls made by preflight: 0
  missing names : GNANI_API_KEY, GEMINI_API_KEY, GEMINI_MODEL

== summary ==
  overall     : INCONCLUSIVE
  exit_code   : 0
  elapsed_s   : 0.069
  run id      : 20261020T075613Z-preflight-428e90440a-6f0020
  evidence    : prompts/phase-02-provider-feasibility/evidence/fix-1/20261020T075613Z-preflight-428e90440a-6f0020
  run index   : 56 invocations recorded
  index file  : tools/probes/.cache/runs.jsonl
```

Preflight stayed **non-inference and value-free**: exit 0, overall
`INCONCLUSIVE`, every credential name missing, **0 inference calls**.

### 4.5 `secret_scan.py` — full output

```text
credential scan: 0 findings
  scope: repository working tree, structural rules only
  note: a clean scan does NOT erase any earlier exposure
```

---

## 5. Attempt accounting

### 5.1 This cycle (measured)

| Run class | Runs | Wire attempts | Note |
|---|---|---|---|
| `pytest-providers` | 11 | **0** | offline; no socket, no inference |
| `pytest-services` | 11 | **0** | offline |
| `test-contracts` | 11 | **0** | offline |
| `preflight` | 26 | **0** | explicitly non-inference |
| `secret-scan` | 11 | **0** | offline |
| `report-links` | 4 | **0** | offline; verifies every relative link in this report resolves |
| `analysis --offline` | 1 | **0** | offline; exercises the filler/metrics path |
| **Total** | **75** | **0** | every run exited 0 |

The fix-1 ledger (`evidence/fix-1/run-index.jsonl`) reports
`measured_wire_attempts: 0` and `unmeasured_wire_attempts: []` — every
run in this cycle is a measured zero because no run made a provider
call. All 75 runs exited 0; **no run failed and none was
cancelled**, and the ledger is structured to count failures and
cancellations (there are none this cycle).

### 5.2 The Phase 02 live runs (historical)

| Quantity | Value |
|---|---|
| Invocations in the Phase 02 ledger | **38** (preserved untouched at `evidence/run-index.jsonl`) |
| Live invocations (`allow_live: true`) | **20** |
| Offline invocations | **18** |
| Live invocations that exited non-zero | **5** |
| **Actual wire attempts** | **UNKNOWN** |
| **Logical calls** | **UNKNOWN** |
| **Connections** | **UNKNOWN** |
| **Retries** | **UNKNOWN** |

**These four counters are unknown, not zero.** Attempt accounting was
introduced in this cycle; the earlier runs recorded visible stages and
budget debits, not wire attempts, and the SDK's own internal retry was
invisible to every counter in use at the time. The previous report's
*"~110 operations"* was an **estimate of visible stages**, and its
*"Retries: 0"* was an **unsupported claim about wire attempts** — both
are corrected here. `ProbeBudget(attempts_measured=False)` renders them
as the string `"unknown"`, and `ledger_totals()` lists any such run
under `unmeasured_wire_attempts`.

---

## 6. Measured cleanup and bounds

| Item | Measured value |
|---|---|
| Credential values in the working tree | **0** (structural scan, 7 rules, content-suppressed) |
| Credential values printed by any command this cycle | **0** (the CLI prints names only) |
| External files visited, opened, read or deleted | **0** |
| Processes started and left running | **0** |
| Open Gemini clients after the cycle | **0** (`client.lifecycle.created == closed` is asserted) |
| Threads spawned per call | **0** (the daemon-per-call workaround is gone) |
| Concurrent reasoning calls permitted | **2** (`max_concurrent_calls`) |
| Reasoning attempt bound / call deadline | **15 s / 45 s**, both configurable and printed |
| SDK-internal retries | **0** (`HttpRetryOptions(attempts=1)`) |
| Chain plan size | **5 wire attempts**, refused before any side effect if it does not fit |
| Submitted-audio plan size | the **framed submitted** audio, including trailing silence |
| Contract example checks | **46** (15 valid, 31 invalid), all hold |
| Provider test suite | **224 passed, 3 skipped** |
| Full voice suite | **247 passed, 3 skipped** |

**Cleanup status of the reported external temporary credential file:
UNKNOWN — unverified.** See §2, P02-01.

---

## 7. Missing evidence — what is still not known

| Missing | Why it is missing | Can this cycle fix it? |
|---|---|---|
| **Rotation status** of the four posted credentials | only the owner can act on a provider dashboard | **no — awaiting the owner** |
| **Fresh live provider evidence** under the repaired budget and lifecycle | no confirmed replacement credentials; live probes are on hold | **no — awaiting the owner** |
| **Native per-language spoken fixtures** | only the English fixture exists; the other nine languages have no matching-language audio | **no** — needs a live TTS render, which needs credentials |
| **Whether `spoken-filled-hesitation` actually contains audible fillers** | no human listener has reviewed the rendered clip | **no — awaiting the owner's annotation** |
| **Filler precision/recall** | 0 verified positives, 0 verified negatives; the target needs ≥20 + ≥20 per mode | **no — awaiting the owner** |
| **Measured wire attempts for the 20 Phase 02 live invocations** | attempt accounting did not exist then | **no** — the counts are lost, not missing from a file |
| **Raw captured frames / full stdout for the Phase 02 live runs** | only summaries were kept; the raw output is not on disk | **no** — a re-run would create *new* evidence, not a replacement history |
| **Human intelligibility of any synthesised speech** | nobody listened to any output | **no** |
| **Coaching quality in any language** | no reply was scored | **no** |
| **Cross-language coaching pairs** | not run | **no** |
| **Browser path, interruption, cancellation in a real call** | Phase 04/05 | out of scope |
| **Persistence, identity, metrics-only mode** | Phase 06 | out of scope |

---

## 8. Live successes and failures

**No live call was made in this cycle.** Everything below is the
Phase 02 record from 2026-10-18, preserved, with the corrections this
cycle requires.

### 8.1 Successes (historical, preserved)

| Observation | Detail |
|---|---|
| One complete chain | STT → Gemini → TTS, `evidence/live-chain-result.json`: fixture `spoken-clear-sentence`, sha256 `274ae51f…`, 2,400 ms; recognised *"i have been working on this project for about two years"*; reply *"That is a long time. What kind of project is it?"*; TTS 81,920 bytes, 52 chunks, 2,560 ms. Backend timings: STT 6,496.1 ms · Gemini 3,541.3 ms · TTS 2,325.8 ms |
| STT responses | 11/11 language rows responded (this is **parameter acceptance** for the non-English rows — see §2, P02-04) |
| TTS responses | 11/11 language rows returned audio |
| Reasoning replies | 10/11 language rows returned text |

> The chain timings are **backend timings measured inside the process**.
> They are **not** end-of-turn-to-first-audible latency for a browser:
> no browser, no AudioWorklet, no playback buffer, no device network
> path. A chained fixture turn is not a hands-free app.

### 8.2 Failures (historical, preserved — not hidden)

1. **Live STT returned zero transcripts on the first attempt** — no
   trailing silence, so the server's VAD never closed the final
   segment. Fixed by appending 800 ms of padding, charged to the budget
   and recorded as padding.
2. **`unknown STT message type 'speech_start'`** — a genuine
   undocumented frame. Recorded as an observation rather than raised or
   ignored.
3. **The send/receive drain truncated audio mid-utterance** — the drain
   idle-timer cancelled the sender. Fixed by awaiting the sender first.
4. **The first matrix run marked all 11 languages `FAILED`** while
   printing `11/11 languages probed`. Two defects: child budgets ignored
   trailing silence, and the summary counted attempted rows as probed.
5. **Gemini hung past 150 s** and the process hung at exit — the SDK
   retried internally on a blocking path. This cycle replaces the
   daemon-thread workaround with the documented async surface; **Gemini
   reliability itself remains INCONCLUSIVE**.
6. **TTS "no audio" in the first chain run** — the session was used
   without entering its async context manager.
7. **`fixtures --offline` destroyed the prepared spoken fixtures** — the
   rebuild reset every spoken entry. Fixed with merge semantics.
8. **Gemini stopped responding near the end of the session** — a re-run
   reached stage 1 and timed out at stage 2. The earlier successful chain
   evidence was preserved and not overwritten.
9. **The Tamil matrix row's reasoning call failed with a bounded
   timeout** (`live-matrix-result{,-b,-c,-d}.json`). Under the previous
   STT-derived aggregation this row was still counted as a success. Under
   the repaired aggregation it is a **FAILED** row with a nonzero exit.

---

## 9. Blocked user decisions

These are the questions only the owner can answer. They are recorded in
`prompts/phase-02-provider-feasibility/DECISION-NEEDED.md`.

| # | Decision | State | What this cycle did |
|---|---|---|---|
| 1 | **Credential rotation status** for the four posted values | **BLOCKED ON USER** | requested as *status only*; no replacement values were sought, received, stored or requested |
| 2 | **Does `spoken-filled-hesitation` contain audible "um"/"uh"?** — play `fixtures/synthetic/audio/spoken-filled-hesitation.wav` (3,680 ms, sha256 `82900f99…`) and answer one question | **BLOCKED ON USER** | the clip's path, hash and duration are now recorded in `DECISION.md` and here; **no reviewer was invented** and the annotation was not fabricated |
| 3 | **Product direction for the filler feature** — preserve the goal, narrow it explicitly, or pause it | **BLOCKED ON USER** | the NO-GO is preserved and the wording repaired; the product was **not** silently narrowed |
| 4 | **Optional reasoning-provider comparison** (Gemini vs Groq vs NVIDIA NIM) | **PREPARED, NOT RUN — awaiting an explicit decision** | no comparison was run and no model was selected |
| 5 | **External temp credential file** — does it still exist, and should it be deleted? | **UNKNOWN, awaiting the owner** | no external file was visited or deleted |

> A narrowed product needs explicit approval and a revised plan.
> Repairing the scaffolding does not resolve the goal-level block.

---

## 10. Phase 03 handoff raised by this cycle

The shared contract was **not** edited — Phase 03 owns it. The required
DTO change is written up in `HANDOFF.md` §5.1a and summarised here:

1. A per-observation **recognition status** (`measured`,
   `no-analyzable-speech`, `missing-transcription`) with `rate_wpm` and
   `active_rate_wpm` **omitted**, not zero, for the two non-measured
   states.
2. The measured clip's **source classification**, with a description
   that says in terms that a source label is a declaration and does not
   establish diarization or echo cancellation.
3. A **span-contents** statement: the span includes the source's leading
   and trailing silence and excludes the end padding.

Phase 03 is paused and was not started.

---

## 11. Process state

- Every session, client and probe invocation was closed. The Gemini
  client is closed on every exit path, and `created == closed` is
  asserted by the lifecycle tests.
- No probe process was left running. No process was killed by broad
  name; only processes this session started were considered.
- The daemon-per-call thread is gone; the adapter awaits the SDK's async
  surface directly, so a cancelled turn cancels its request.
- **No relay is exposed.** No server was started; nothing listens on a
  port. Nothing was staged, committed or pushed; `git diff --cached` is
  empty. No deployment, no delegation, no model training.
- The Phase 01 uncommitted work in the tree was left exactly as found,
  and the Phase 02 evidence from 2026-10-18 was preserved, not
  overwritten.

---

## 12. Bottom line

The **code and evidence scaffolding** behind the Phase 02 findings is
repaired and verified offline. The **decisions** are not mine to make and
remain with the owner:

- **The filler-localisation NO-GO stands.** The fillers are absent from
  recognition; the rendered audio was not reviewed; the target is not
  evaluable; the heuristic stays an unvalidated candidate.
- **Rotation status is unconfirmed**, so no live provider call was made
  and no live claim is made in this report.
- **The Phase 02 live evidence is preserved and labelled** for what it
  is, with its wire-attempt counts recorded as **UNKNOWN**.

---

**FIX-1 COMPLETE — AWAITING CEO REVIEW**
