# @gnani/contracts — shared contract draft v0.1

Single source of truth for the shapes shared between the web app and the voice
service. **Status: DRAFT v0.1 — not frozen.** Contracts are finalized only in
Phase 03, after real provider observations. Nothing here proves runtime
capability: documented capability is not verified capability.

## Layout

- `schemas/*.schema.json` — seven JSON Schema **draft 2020-12** definitions:
  `catalog`, `session-settings`, `event-envelope`, `analysis-observation`,
  `durable-metrics`, `recording-metadata`, `error-shape`.
- `data/catalog.json` — the language/scenario catalog the UI reads. The
  catalog lists exactly the ten documented realtime languages, Hinglish as a
  code-mixed mode (`sttCode: en-IN`, `ttsCode: hi-en`), and four scenario
  presets. French is not a member.
- `examples/<schema-stem>/valid|invalid/*.json` — compact positive/negative
  fixtures. The expectation comes from the folder name.
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
- check the catalog invariants (ten language ids, no French, Hinglish mapping,
  capability flags other than `documented` stay `false`).

## Draft boundary notes (for Phase 03)

- **Shape vs membership:** schema checks are structural. `practiceLanguageId:
  "french"` is well-formed and intentionally *passes* the shape check
  (`examples/session-settings/valid/shape-only-french-id-passes.json`);
  membership in the catalog and staleness of session/connection/turn
  identifiers are runtime identity checks, not schema checks.
- **Transient vs durable:** transcripts, quoted mistakes and model text live
  only in transient events; the durable metrics shape rejects them by name
  (`transcript`, `quotedMistakes`, `modelText`, `audioUrl`, `embedding`).
- **Zero is not unmeasurable:** `status: available` with `value: 0` is a real
  measured zero; `unavailable`/`insufficient_evidence` always carry `null`.
- **No word timings:** server emission timestamps are not alignments. There is
  deliberately no word-timing field to conjure one from.
- **No public audio URLs:** recording metadata carries a private opaque
  reference only; deletion is a state with a timestamp.

## Run

From the repository root:

```sh
npm run test:contracts
```

or directly:

```sh
npm run test --workspace @gnani/contracts
```
