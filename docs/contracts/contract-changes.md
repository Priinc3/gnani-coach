# Contract changes — the Phase 02 handoff, answered section by section

Status: **FROZEN, 2026-10-20 (Phase 03).** Source: `docs/feasibility/HANDOFF.md`
§5 and §5.1–5.6, plus the feasibility decision
(`docs/feasibility/DECISION.md`).

Every change below is in `packages/contracts/**`, and every change has a
valid and an invalid fixture. `npm run test:contracts` runs both the
Ajv and (through the Python parity suite) the `jsonschema` check.

---

## §5.1 — the metric denominators must be split

**Change.** The two speaking rates no longer share a method identifier
and no longer share a denominator.

| Metric | Method identifier | Denominator |
|---|---|---|
| `speech.rate_wpm` | `stt_words_over_learner_span` | `learner_span_ms` |
| `speech.active_rate_wpm` | `stt_words_over_speech_active` | `speech_active_ms` |

The method description states that **neither denominator may ever be
total connection time, total session time, network round-trip time or
provider emission time**, and it names the excluded quantities one by
one.

A per-observation `denominator` field was added as well, so the
denominator is a machine-readable value and not only prose.

**Compatibility note (deliberate).** `stt_words_over_speech_regions` is
kept in the closed method set, bound to `speech.rate_wpm` **only**, so a
record written before the freeze still validates. The conflation is gone:
the speech-active rate can no longer be written with that identifier, and
the schema rejects the attempt.

**Fixtures.**
* valid: `durable-metrics/valid/split-rate-denominators.json`,
  `analysis-observation/valid/rate-with-denominator.json`;
* invalid: `durable-metrics/invalid/active-rate-with-overall-method.json`,
  `durable-metrics/invalid/rate-with-wrong-denominator.json`,
  `analysis-observation/invalid/active-rate-with-overall-method.json`,
  `analysis-observation/invalid/rate-with-wrong-denominator.json`.

---

## §5.1a — recognition status and source trust

### (a) A recognition status, so a missing transcript is never a measured zero

**Change.** A new closed vocabulary:

```
measured              a transcript exists and was used
no-analyzable-speech  the recogniser ran and returned nothing analyzable
missing-transcription no transcript was obtained at all
```

The status appears in two places:

* `durable-metrics`: `turn.recognitionStatus` is **required** on every
  turn, and an observation may restate it.
* `analysis-observation`: `observation.recognitionStatus` is optional but
  constrained when present.

The rules the schema now enforces:

* a turn whose recognition status is not `measured` **may not** carry a
  rate or a filler count with the status `available`;
* an observation whose recognition status is `no-analyzable-speech` must
  be `insufficient_evidence` with a null value, and one whose status is
  `missing-transcription` must be `unavailable` with a null value.

So a missing transcription can never validate as a measured `0`.

**Fixtures.** valid: `durable-metrics/valid/missing-transcription-rate.json`,
`analysis-observation/valid/missing-transcription-rate.json`; invalid:
`durable-metrics/invalid/rate-zero-with-missing-transcription.json`,
`analysis-observation/invalid/rate-zero-with-missing-transcription.json`,
`durable-metrics/invalid/turn-without-recognition-status.json`.

### (b) The source of the measured audio, and what a label does not prove

**Change.** A new closed field, `audioSourceClassification`, with the
values `learner-audio` and `synthetic-learner-audio`. Its description
says in terms that **a source label is a declaration, not a proof**: it
does not establish diarization and it does not establish echo
cancellation, and empty, assistant-only, mixed and unknown
classifications are refused before a measurement is produced.

It is required on every durable turn, optional per observation, and
**forbidden** on an `inferred` observation, because an inferred
observation has no measured clip.

**Fixtures.** invalid:
`durable-metrics/invalid/unknown-source-classification.json`,
`analysis-observation/invalid/unknown-source-classification.json`,
`analysis-observation/invalid/inferred-with-source-classification.json`.

### (c) Span contents

**Change.** The `evidenceSpan` description now states both halves: the
span **includes** the source's leading and trailing silence (it is the
elapsed span the learner produced) and **excludes** the end padding. The
durable `turn.durationMs` description says the same.

**Fixtures.** The rule is descriptive (a schema cannot compare two
timestamps), so it is proven by the description text and by the valid
fixtures that carry both a `durationMs` and a `turn.duration_ms`
observation.

---

## §5.2 — `turn.duration_ms` must be sample-clock based

**Change.** The method identifier `turn_connection_timer` is **replaced**
by `learner_audio_sample_clock`, and the description states that the
value is the elapsed learner audio on the local sample clock, with the
deliberate end padding excluded, and that it is **never** connection
time and **never** session time. The observation is also forbidden from
carrying a `denominator` (a duration is not a rate) and from carrying a
`recognitionStatus` (the transcript says nothing about a duration).

**Fixtures.** valid:
`durable-metrics/valid/missing-transcription-rate.json` (a turn whose
duration is recorded while its transcript is missing); invalid:
`durable-metrics/invalid/turn-duration-with-connection-timer.json`.

---

## §5.3 — `totals.speakingTimeMs` is ambiguous

**Change.** `totals.speakingTimeMs` is documented as **the sum of
detected speech-active time** across the session's turns, explicitly not
the sum of the elapsed turn spans (which also contain silence), and the
invariant `speakingTimeMs ≤ Σ turns[].durationMs` is stated in the
field description. `totals.turnCount` is documented as **completed
learner turns**, never speech-to-text segments.

The invariant itself is a cross-field rule that JSON Schema 2020-12
cannot express; it belongs to the writer boundary and is checked there
(Phase 05/06). The rule is stated here and in the schema description;
`docs/architecture.md` still carries the Phase 01 list of invariants that
a schema cannot express, and this entry is the Phase 03 answer to it.

**Fixtures.** Every valid durable fixture carries a `totals` block whose
`speakingTimeMs` is at most the turn duration, so the shape and the
documented rule agree.

---

## §5.4 — missing identifier and span semantics

| Need | What the contract now says |
|---|---|
| Turn grouping | A turn is a conversational turn, not a recogniser segment. The `turnId` description in both schemas says so, and the transport document repeats it. The provider's `utterance_id` is the closest observed grouping signal, is unstable, and is never presented as a turn boundary. |
| Word positions | There is **no word-level timing** in the contract and none is derived. The `evidenceSpan` description says the spans are estimated regions, not word timings, and there is deliberately no word-timing field to fill by inference. |
| Event spans for a filler | A missing or unvalidated filler is `insufficient_evidence` with a null value and the reason `filler_detection_unvalidated` — **never** `0`. The reason code is in the closed `unavailabilityReason` set. |
| Frame/clock provenance | The method identifier `learner_audio_sample_clock` is the controlled provenance id for "learner audio sample clock", distinct from connection timing. |
| Provider latency | The provider's per-segment `latency` is metadata, not a metric value: it is not in the metric-key allowlist, so it cannot be written as one. |

**Fixtures.** valid: `analysis-observation/valid/unvalidated-filler.json`
(the honest filler rendering); invalid:
`durable-metrics/invalid/pause-with-denominator.json` (a duration metric
may not carry a rate denominator).

---

## §5.5 — settings

Handled in [settings.md](settings.md). Summary: `speech_readiness()` and
`reasoning_readiness()` exist and never depend on Supabase; the states
are `unconfigured | configured | verified`; the model id is frozen with
an access date and a citation; a TTS model/voice selector and a VAD
settings object that survives a reconnect were added.

---

## §5.6 — observed behaviour a contract must not encode by accident

None of these are encoded as a contract fact. They are recorded here so
nobody "fixes" them later:

| Observation | How the contract handles it |
|---|---|
| `segment_index` began at 1, not 0 | The contract never uses the provider's index as a turn or segment ordinal. The transport orders by the provider's chunk index for TTS and by the application's own counter for events. |
| `audio_duration_ms` was absent from live frames | There is no field for it in any contract shape. |
| Output was lowercased under `verbatim` | No contract rule depends on the case of recognised text. A future filler detector must normalise knowingly. |
| A 1,200 ms gap split one sentence into two segments | The "a segment is not a turn" rule, stated in both the schemas and the transport document. |
| A full eleven-language matrix does not fit one probe run | Nothing about it is encoded; it was a probe-budget fact. |
| A language row is not covered by an STT-only success | The catalog's four capability flags stay independent, and the runner asserts that only `documented` is true. |
| `en-IN` is ambiguous between English and Hinglish | The catalog keeps the code-mixed mode as a separate entry with its own ids, exactly as Phase 01 left it. |

---

## The filler capability (Phase 02 decision of 2026-10-20)

See [capability-states.md](capability-states.md). Summary: the filler
localisation capability is `unvalidated`, the UI and the coach render
`insufficient_evidence`, no filler flag is true anywhere, and the goal is
preserved rather than narrowed.
