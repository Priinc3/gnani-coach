# Phase 02 — feasibility decision

Four questions, each answered **GO / NO-GO / INSUFFICIENT EVIDENCE** with
evidence links. This is an engineering feasibility verdict, **not a CEO
`✅ VERIFIED` verdict** and not batch acceptance.

Evidence root: `prompts/phase-02-provider-feasibility/evidence/`
Raw probe output: `evidence/analysis-offline.txt`, `evidence/run-index.jsonl`
Machine-readable results: [`capabilities.json`](capabilities.json)

---

## Q1 — Can the account support the real speech chain?

### **GO** (for plumbing) · **INCONCLUSIVE** (for reliability)

A complete turn ran end to end with all three real providers:

```text
synthetic fixture (our own TTS, 16 kHz mono, sha256 274ae51f…)
  → Gnani realtime STT   'i have been working on this project for about two years'
  → Gemini gemini-3.8-flash (store=False, tools=none)  'That is a long time. What kind of project is it?'
  → Gnani Timbre v2.5 / Kaveri  52 chunks, 81,920 bytes, 2,560 ms
```

Evidence: `evidence/live-chain-result.json`.
All eleven catalog entries completed a live STT stage and a live TTS stage
(`evidence/live-matrix-result*.json`, summarised in
[CAPABILITIES.md](CAPABILITIES.md)).

**What this does not prove.** Gemini was the weak link: it succeeded once in
the chain and 10/11 times across matrix runs, then returned a bounded
timeout for Tamil and, later, network-category failures from the same
environment. One defect was found and fixed in our own adapter (the SDK's
internal retry defeated the timeout — see
[HANDOFF §4](HANDOFF.md)), but **underlying Gemini reliability is unsettled
and needs a short soak** before Phase 05 depends on it in a live call.

Backends first-byte timings here are **backend** measurements. A chained
fixture turn is not a hands-free app: no browser, no AudioWorklet, no
playback buffer, no interruption handling.

---

## Q2 — Can delivery measurements be anchored to audio?

### **GO**

The measurement path is real and runs entirely on the learner's own audio
sample clock.

Against **exact synthetic manipulation labels** (silence inserted at known
sample indices), Silero VAD over ONNX Runtime produced:

| Fixture | Labelled | Detected | Matched | Worst boundary error |
|---|---|---|---|---|
| `clear-utterance` | 1 | 1 | 1 | **44 ms** |
| `one-word` | 1 | 1 | 1 | **16 ms** |
| `known-internal-gap` | 2 | 2 | 2 | **44 ms** |

Well inside the plan's 300 ms target — **on synthetic signals**, which is
the only kind of signal with exact boundary labels.

The four denominators are kept separate end to end and never conflate
connection or session time with learner span; genuine audio, end padding and
submitted audio are three distinct figures
([HANDOFF §3](HANDOFF.md)).

**Two limits on that GO.** First, these are generated signals: they prove
the pipeline and the framing, not behaviour on natural speech. Second, the
provider itself anchors nothing — `audio_duration_ms` was **absent** from
live frames and no word-level timing exists, so every span remains an
estimate on our clock, never an alignment.

---

## Q3 — Is filler localisation credible under the stated target?

### **NO-GO** on the current approach

Target: ≥90 % precision, ≥80 % recall, p95 matched-event boundary error
≤300 ms, with ≥20 positive and ≥20 negative examples **per enabled filler
mode**.

**Both halves of that are unmet, and the first is a correctness failure
of the measurement — not a missing-evidence problem.**

**1. The fillers are absent from the recognition output.**
`spoken-filled-hesitation` was synthesised from *"So um I think the
timeline is, uh, probably next month."* and recognised as:

```text
'so i think the timeline is probably next month'
```

Both `um` and `uh` are gone from what the recogniser returned.

> **Updated 2026-10-20 (Phase 02 FIX cycle 2).** The ambiguity this
> section used to carry is now resolved by a **human reviewer**: the
> project owner listened to
> `fixtures/synthetic/audio/spoken-filled-hesitation.wav` and **hears
> both "um" and "uh"**. The annotation is recorded in the sidecar
> `fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json`
> (reviewer `project owner (user)`, date `2026-10-20`, `um_present:
> true`, `uh_present: true`; **no positions were provided, so none are
> recorded**).
>
> So the two causes are no longer equally open: on **this** sample the
> fillers **were** in the rendered audio and the recogniser **omitted**
> them. That is a fact about **one sample**, not a demonstration that
> the recogniser is permanently incapable of preserving a filler, and it
> is not a precision/recall result.

The clip under review is easy to find:

| Property | Value |
|---|---|
| Fixture id | `spoken-filled-hesitation` |
| Path | `fixtures/synthetic/audio/spoken-filled-hesitation.wav` |
| Duration | 3.7 s |
| sha256 | `82900f998131e7f512a2bee278e16f5bc849a5475510272ac5d321b53018ab56` |
| Review state | **REVIEWED** — `project owner (user)`, 2026-10-20: both "um" and "uh" audible. Annotation: `fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json` |

**2. Therefore transcript-based filler counting cannot be audio
analysis.** The moment a hesitation is omitted, counting marker strings
in the cleaned transcript silently reports the wrong number *and* cannot
locate the event. The build prompt forbids presenting transcript-only
output as audio analysis, and this result is exactly why. A "zero
fillers" reading from this transcript would be a clean bill of fluency
for a speaker whose hesitation — if it was ever spoken — was not
recognised.

**3. Precision/recall are NOT EVALUABLE.** No human-reviewed filler labels
exist with **positions**. The owner reviewed one clip for **presence** and
gave no start/end times, so there is still no label a detector can be
scored against. Zero positive examples have a verified *position*. A forced
aligner is not a workaround: it maps *supplied text* onto audio, and the word
it would need to place is the one missing from the text. The candidate
detector's own predictions are never accepted as ground truth.

**Zero reviewed examples means the target is not evaluable — not a
measured zero-filler success.** The distinction matters: "we did not
measure" and "we measured zero" are different claims, and only the first
is supported.

**4. The audio-aware candidate is threshold-dependent.** Localising short
bursts between VAD regions — the only genuinely audio-grounded approach
tried — is dominated by the VAD merge threshold:

```text
min_silence_ms=120 → 2 candidate events
min_silence_ms=200 → 1 candidate event
min_silence_ms=300 → 0 candidate events   (probe default)
```

At the default, bursts shorter than the merge window are absorbed into the
surrounding speech region and can never become candidates. Even at the
tuned setting, every event is a **candidate** — a breath, a lip click and a
short word are acoustically indistinguishable from a filled pause at this
level of analysis. This heuristic stays an **unvalidated candidate**; it
has not been tuned against holdout labels and no reviewer was invented
for it.

**5. The bounded experiment of 2026-10-20 did not move this verdict.**
Phase 02 FIX cycle 2 ran one bounded experiment on this clip through three
routes (the Gnani STT with `verbatim`/`transcribe`, a lower
`x-min-silence-ms` and word boosting of `um`/`uh`; a Gemini audio review;
and an offline acoustic scan that looks *inside* the VAD speech regions).
**No route passed.** The two live routes were **BLOCKED — no credentials
were configured**, and the offline route reported **one** inside-region
candidate event on the hesitation clip (155 ms, 2260–2415 ms) and **none**
on the clean-speech clip: one event is not both fillers, and without
positions the event cannot even be matched to "um" or "uh". Details and
raw output: `prompts/phase-02-provider-feasibility/REPORT.md`. The
verdict below is therefore **unchanged** by that experiment.

**The target is neither met nor refuted by a labelled pilot; it is
unsupported on the mechanism that currently exists.** That is a NO-GO on
the approach, not a soft failure.

**What this NO-GO does and does not say.** It says: *the approach as
built cannot currently support the target, and the evidence needed to
evaluate it does not exist.* It does **not** say that filler localisation
is impossible, that no other research route exists, or that the recogniser
is permanently incapable. Those are different claims and none of them is
supported by the current evidence.

---

## Q4 — Which languages / capabilities remain unproven?

### **INSUFFICIENT EVIDENCE**

| Claim | State |
|---|---|
| All ten languages speakable end to end | **API plumbing only.** 11/11 STT and TTS responded. Accuracy on real speakers is untested. |
| Hinglish as a mode | API plumbing only. `hi-en` is TTS-only; STT took `en-IN`. No code-mixed scoring was tested. |
| Language-code correctness | **Contradicted.** English audio with `ta-IN` returned English transcribed into Tamil script. The endpoint does not validate language match. |
| Human intelligibility of TTS | **NOT RUN.** Nobody listened to any output. |
| Coaching quality in any language | **NOT RUN.** No reply was scored. |
| Cross-language coaching pairs | **NOT RUN.** |
| Filler preservation | **NO-GO** (Q3). |
| Audio localisation on natural speech | **NOT RUN.** Only synthetic boundaries were measured. |
| Recognition accuracy | **NOT RUN.** No word-error measurement was run. |
| Gemini reliability | **INCONCLUSIVE** — intermittent. |
| Browser path, interruption, cancellation in a real call | **NOT RUN** — Phase 04/05. |
| Persistence, identity, metrics-only mode | **NOT RUN** — Phase 06. |

A successful request in one language proves nothing about the other nine,
and an API roundtrip proves nothing about a human hearing the result.

---

## Cheapest next decision

The plan is explicit that the hardest technical risk is filler
localisation, and that if the evidence fails the right move is to bring the
user the cheapest options rather than to quietly narrow the feature. Sorted
by cost:

### Option A — listen, then decide (recommended; minutes, no new spend)

> **ANSWERED 2026-10-20 (Phase 02 FIX cycle 2).** The project owner
> listened to the clip and **hears both "um" and "uh"**. The annotation is
> recorded in
> `fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json`. The
> *first* branch below is therefore the one that applies: the hesitation
> **was** spoken and did not survive recognition, on this sample. The
> bounded experiment that followed (three routes, one clip) is reported
> in `prompts/phase-02-provider-feasibility/REPORT.md`: **no route
> passed**, and the Q3 verdict is unchanged. Option A is closed as a
> *fact*; it was never a substitute for the labelled set.

The single most valuable missing fact is whether *"So um … uh …"* was ever
**spoken** in `spoken-filled-hesitation`
(`fixtures/synthetic/audio/spoken-filled-hesitation.wav`, 3.7 s). One
person plays that one clip and answers one question.

- **If the hesitation was spoken** → it did not survive recognition, and
  Q3's NO-GO is confirmed as a limit of the current recognition path.
  Real audio analysis (or a dedicated disfluency component) becomes the
  path to investigate, and the user gets a real decision. This still does
  not establish that the recogniser is *permanently* incapable.
- **If it was never spoken** → the fixture is invalid rather than the
  feature, and the test must be re-made with a source that genuinely
  voices fillers.

Until this is answered, every downstream filler decision is speculation.
This is the cheapest action available and it blocks the most.

**One reviewed clip is one clip.** It resolves this fixture's ambiguity.
It does not validate all languages, it does not create the ≥20 positive /
≥20 negative labelled examples the target requires, and it is not a
precision/recall evaluation. Recording the annotation does not alter the
original audio.

### Option B — re-synthesise the hesitation with a source that preserves it

Timbre v3.0 documents audio tags (`<pauses>`, `<coughs>`, `<exhales>`) and is
explicitly rejected on v2.5. Rendering *"So um I think…"* on
`timbre-v3.0` would test whether the fillers survive synthesis at all.
Cost: a few TTS operations. Limit: still TTS, not a human — it cannot
validate natural learner speech, and v3.0's "every voice speaks all ten"
remains untested here.

### Option C — accept a narrowed feature, explicitly

Drop "audio-grounded filler localisation" from the enabled capability set
and keep only what Q2 actually supports: **pause detection and
speech-active time**, anchored to the learner's own sample clock and
labelled as estimates. This is defensible today and is the cheapest
*product* outcome — but it is a **scope change requiring explicit user
approval**, and it does **not** meet the original goal. Pauses alone are not
the feature that was asked for.

### Option D — evaluate a dedicated disfluency component

A route that could satisfy the ≥90/≥80 target. Requires its own
research: language coverage for ten languages, licence, model size, CPU
feasibility in the voice service, and a labelled evaluation set (≥20
positive + ≥20 negative per enabled mode) that **does not exist yet**.
This is the expensive option and it should not be started before A.

This option is **one candidate among several**, not a demonstrated
singular route: real audio analysis of the rendered signal (§Q3.4) is
also under investigation, and other approaches may exist. Option D is
listed because it has a clear evaluation story, not because it is the
only way forward.

**Recommendation:** do **A** first. It costs minutes and it converts the
central blocker from speculation into a fact. Do not start D, and do not
quietly ship C.

---

## Bottom line

The **plumbing is real**: adapters, framing, clocks, budgets, redaction,
endpoint confinement and a full STT → Gemini → TTS chain all work against
live providers, and audio-anchored measurement works on signals with known
labels.

The **feature at the centre of the product is not yet real**: filler
localisation is NO-GO on the current mechanism, and no language has been
shown intelligible, coachable or filler-safe. Phase 03 should freeze
contracts that keep the denominators honest and the readiness separated, but
it must not freeze a filler capability as if it were validated.

**B1 has not been accepted.** This phase produced evidence for it, not a
pass for it.

**The Q3 goal decision remains open and belongs to the user.** Option A is
now **answered** (2026-10-20: the hesitations were spoken; the recogniser
omitted them on that sample), and the bounded experiment that followed
found **no passing route**. What is still missing is the ≥20 positive /
≥20 negative **position-labelled** set per enabled filler mode, and a
decision on the feature itself: continue towards that set, narrow
explicitly, or pause. The answer to Option A does not by itself satisfy
the target's labelled-example requirement.
