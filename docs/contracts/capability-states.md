# Capability states — and the unvalidated filler

Status: **FROZEN, 2026-10-20 (Phase 03).** The machine-readable register
is `packages/contracts/data/capabilities.json`, described by
`packages/contracts/schemas/capability-state.schema.json`.

**Phase 08 changes this data file and nothing else.** The shape is
frozen; a state may be flipped, with the evidence that justified it, and
a new field may be filled in.

---

## 1. The register

| Capability | State | Rendered as | Meaning |
|---|---|---|---|
| `filler-localization` | **unvalidated** | `insufficient_evidence` | No route passed. The feature is not real yet. |
| `pause-detection` | `validated_synthetic_only` | `available` | The mechanism passed against exact synthetic labels; natural-learner behaviour is untested. |
| `speech-rate` | `validated_synthetic_only` | `available` | Same limitation. |
| `speech-active-rate` | `validated_synthetic_only` | `available` | Same limitation. |
| `turn-duration` | `validated_synthetic_only` | `available` | Same limitation. |
| `conversation-coach` | `unvalidated` | `insufficient_evidence` | One live chain turn succeeded, but nobody listened to the audio and no reply was scored. |

The states mean:

* `unvalidated` — no passing check exists;
* `validated_synthetic_only` — the check passed only on generated
  signals, which proves the mechanism and not natural-learner behaviour;
* `validated` — a genuine check against real audio with held-out labels
  met the recorded acceptance thresholds.

**No capability may claim `validated` in this freeze.** The contract
runner fails the build if one does.

---

## 2. The filler decision (2026-10-20)

No filler route passed. The bounded experiment of 2026-10-20 ran three
routes — the Gnani recogniser with `verbatim`/`transcribe` and a lower
silence window, a Gemini audio review, and an offline acoustic scan
inside the VAD regions — and **none** of them passed. The verdict in
`docs/feasibility/DECISION.md` (Q3, NO-GO) is unchanged.

What that means in the product:

1. **The UI and the coach render `insufficient_evidence`** for a filler
   count. They never show `0` fillers, and they never say the learner
   spoke fluently.
2. **A missing or unvalidated filler is never `0`.** The reason code is
   `filler_detection_unvalidated`, and the value is `null`.
3. **No filler flag is true.** The catalog's per-language capability
   flags stay `documented`-only, and the contract runner asserts it.
4. **The goal is preserved, not narrowed.** The register records
   `goalPreserved: true` and `scopeChangeApproved: false`. Narrowing the
   feature is a scope change that needs the owner's explicit approval —
   it is not a data edit, and this phase did not make one.

### Why "0 fillers" would be a lie

On the reviewed clip the recogniser returned
`'so i think the timeline is probably next month'` while the project
owner confirmed hearing **both** "um" and "uh" in the rendered audio
(`fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json`).
The hesitations were spoken and did not survive recognition. Counting
marker strings in the cleaned transcript would report the wrong number
*and* could not locate the event. "Zero fillers" from that transcript is
a clean bill of fluency for a speaker whose hesitation was never
recognised — so the contract refuses to express it.

---

## 3. How a later validated state is recorded

A detector that passes the recorded acceptance thresholds flips **data
only**:

```jsonc
"filler-localization": {
  "state": "validated",              // was "unvalidated"
  "renderedState": "available",      // was "insufficient_evidence"
  "validatedAt": "2026-11-04",       // was null
  "validatedBy": "held-out labelled set, 24 positives / 24 negatives",
  "evidenceRefs": ["tests/acceptance/filler/..."],
  "acceptance": {                    // unchanged: the bar does not move
    "precisionMin": 0.9,
    "recallMin": 0.8,
    "boundaryP95ErrorMsMax": 300,
    "minPositiveExamples": 20,
    "minNegativeExamples": 20
  }
}
```

The schema enforces that a validated state carries a validation date and
a plain-word account of who validated it, so a flip cannot be silent.

The acceptance bar comes from the plan: precision ≥ 90 %, recall ≥ 80 %,
matched-event boundary p95 error ≤ 300 ms, with at least 20 positive and
20 negative examples **per enabled filler mode**. A synthetic-only
evaluation must be labelled as such and cannot prove natural-learner
accuracy.

---

## 4. Where the states are read

| Reader | What it does with a state |
|---|---|
| The web app | `renderedState` decides whether a metric may be shown or whether the honest "not enough evidence" state is shown. Phase 04 reads the catalog and the register. |
| The coach | An unvalidated capability produces the `insufficient_evidence` wording, never a number. Phase 05. |
| The contract runner | Asserts that no capability claims `validated`, that an unvalidated capability renders as `insufficient_evidence`, that the filler goal is preserved, and that no durable example writes an available filler count. |
| The integration test | Asserts the same three rules from `tests/integration/test_seams.py`. |
