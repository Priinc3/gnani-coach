# Frozen contracts — Phase 03 (2026-10-20)

Status: **FROZEN for batch B1.** The shapes below are fixed. Phase 08 may
change capability **data** only; a shape change needs a contract review.

| Document | What it freezes | Who reads it |
|---|---|---|
| [seams.md](seams.md) | The exact names, locations and unavailable behaviour of every seam — and, since the Phase 03 FIX-1, the origin allowlist (§8) and the browser-visible voice URL (§6.1) | **G1 builders read this file** |
| [call-transport.md](call-transport.md) | The browser↔voice WebSocket: events, ids, heartbeat, stale-turn suppression, caps, authentication | Phase 04, Phase 05, Phase 07 |
| [contract-changes.md](contract-changes.md) | Every Phase 02 handoff request, the change that answers it, and the fixtures that prove it | B1 tester, Phase 05 |
| [settings.md](settings.md) | The configuration boundary: readiness states, the frozen model id, the TTS selector, the VAD object, the origin allowlist | Phase 05, Phase 09 |
| [capability-states.md](capability-states.md) | The capability register, the unvalidated filler state, and how a later validated state is recorded | Phase 08, Phase 04, Phase 05 |

The machine-readable contracts live in
[`packages/contracts/`](../../packages/contracts/README.md):

* `schemas/*.schema.json` — eight JSON Schema 2020-12 definitions;
* `data/catalog.json` — the ten documented languages, the code-mixed mode,
  the scenario categories with their presets and the levels;
* `data/capabilities.json` — the capability states (this is the file
  Phase 08 changes, and the only file Phase 08 may change).

Both runtimes consume the same files: Ajv in Node
(`npm run test:contracts`) and `jsonschema` in Python
(`uv run --project services/voice python -m pytest services/voice/tests`).

The frozen seams have their own smoke test, which boots the real web app
and the real voice service:

```sh
npm run test:integration
```

See [`tests/integration/README.md`](../../tests/integration/README.md).

## The three rules that carry the most weight

1. **A missing measurement is never a zero.** A turn states its
   recognition status; if the transcript is missing or unanalyzable, the
   rate is absent, not `0`, and the schema rejects the combination.
2. **The two rates are different quantities.** They have different
   method identifiers and different denominators, and the schema refuses
   to let one be written as the other.
3. **A source label is a declaration, not a proof.** It does not
   establish diarization and it does not establish echo cancellation, and
   the contract says so in the field description.
