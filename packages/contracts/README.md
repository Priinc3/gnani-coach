# @gnani/contracts — the frozen shared contracts (v0.1)

Single source of truth for the shapes shared between the web app and the
voice service. **Status: FROZEN v0.1 (Phase 03, 2026-10-20).** The
shapes are fixed; only the capability **data** may change later (Phase
08), and only by flipping a state and recording the evidence behind it.

Nothing here proves runtime capability: documented capability is not
verified capability, and a contract that names a method does not mean the
detector exists.

The human-readable contract documents live in
[`docs/contracts/`](../../docs/contracts/README.md). G1 builders read
[`docs/contracts/seams.md`](../../docs/contracts/seams.md).

## Layout

- `schemas/*.schema.json` — eight JSON Schema **draft 2020-12**
  definitions: `catalog`, `session-settings`, `event-envelope`,
  `analysis-observation`, `durable-metrics`, `recording-metadata`,
  `error-shape`, `capability-state`.
- `data/catalog.json` — the language/scenario catalog the UI reads: the
  ten documented realtime languages, Hinglish as a code-mixed mode
  (`sttCode: en-IN`, `ttsCode: hi-en`), four scenario categories with
  their named presets, the transient Custom Topic scenario, and three
  levels. French is not a member.
- `data/capabilities.json` — the capability-state register. **Phase 08
  owns this file.** It is where the filler capability's `unvalidated`
  state lives.
- `examples/<schema-stem>/valid|invalid/*.json` — compact
  positive/negative fixtures. The expectation comes from the folder name.
- `scripts/test-examples.mjs` — the runner behind `npm run test:contracts`.

## How the two runtimes consume the same files

| Runtime | Configuration |
|---|---|
| Node (Ajv 8.20.0) | `Ajv2020` from `ajv/dist/2020.js`, `{ allErrors: true, strict: true, allowUnionTypes: true }`, plus `ajv-formats` 3.0.1 for `date`, `date-time`, `uri`. Compile failures fail the run. |
| Python (jsonschema 4.26.0) | `Draft202012Validator(schema, format_checker=FormatChecker())` with the `format-nongpl` extra installed, in `services/voice/tests/foundation/test_contract_parity.py`. |

Both runtimes:

- require every schema to declare `$schema` = `https://json-schema.org/draft/2020-12/schema`;
- reject remote or relative `$ref`s — all references are local (`#/...`) and
  no schema is fetched over the network;
- run every fixture in `examples/`, treating `valid/` as must-pass and
  `invalid/` as must-fail;
- assert the fixture inventory in `scripts/test-examples.mjs`
  (`REQUIRED_FIXTURES`) so coverage cannot silently disappear;
- check the catalog invariants (ten language ids, no French, Hinglish
  mapping, capability flags other than `documented` stay `false`);
- check the capability register (no capability claims `validated`, an
  unvalidated capability renders as `insufficient_evidence`, the filler
  goal is preserved, and no durable example writes an available filler
  count).

## The frozen rules

- **Shape vs membership:** schema checks are structural.
  `practiceLanguageId: "french"` is well-formed and intentionally *passes*
  the shape check
  (`examples/session-settings/valid/shape-only-french-id-passes.json`);
  membership in the catalog and staleness of session/connection/turn
  identifiers are runtime identity checks, not schema checks.
- **Transient vs durable:** transcripts, quoted mistakes and model text
  live only in transient events; the durable metrics shape rejects them
  by name (`transcript`, `quotedMistakes`, `modelText`, `audioUrl`,
  `embedding`) and now also rejects `customTopic`, because the
  learner-written topic is never persisted.
- **Durable provenance is controlled vocabulary:** `method` is a closed
  identifier set coupled one-per-metric-key, `denominator` is a closed
  two-value set coupled to the two rate metrics, `recognitionStatus` and
  `audioSourceClassification` are closed sets, and `unavailabilityReason`
  is a closed reason-code set. Display labels are produced by trusted
  application mappings of these identifiers — never copied from learner
  or model text.
- **Zero is not unmeasurable:** `status: available` with `value: 0` is a
  real measured zero; `unavailable`/`insufficient_evidence` always carry
  `null` and a reason code. A **missing transcript is not a measured
  zero**: a turn whose `recognitionStatus` is not `measured` may not
  carry an available rate or filler count, and the schema rejects it.
- **The two rates are different quantities:** `speech.rate_wpm` divides
  recognised words by `learner_span_ms`; `speech.active_rate_wpm` divides
  them by `speech_active_ms`. Neither denominator may ever be connection
  time, session time, network round-trip time or a provider emission
  timestamp.
- **A source label is a declaration, not a proof:** it does not establish
  diarization and it does not establish echo cancellation.
- **Numeric domains and units:** values are nonnegative; `*.count` and
  `*_ms` keys are integers; `*_wpm` keys may be fractional; each metric
  key admits exactly one unit, one method and (for the rates) one
  denominator. Cross-field invariants (e.g. `speakingTimeMs ≤ Σ
  durationMs`, `evidenceSpan.startMs ≤ endMs`) are **not** schema
  expressible and belong to the writer boundary — see
  `docs/contracts/contract-changes.md`.
- **No word timings:** server emission timestamps are not alignments.
  There is deliberately no word-timing field to conjure one from, and
  the `evidenceSpan` description says the spans are estimated regions.
- **No public audio URLs:** recording metadata carries a private opaque
  reference only; deletion is a state with a timestamp.
- **The filler capability is unvalidated:** the reason code
  `filler_detection_unvalidated` exists, and a filler count is
  `insufficient_evidence`, never `0`.

## Run

From the repository root:

```sh
npm run test:contracts
```

or directly:

```sh
npm run test --workspace @gnani/contracts
```
