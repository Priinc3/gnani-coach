# Phase 02 — cheapest decisions before more feature work

The original speaking-coach goal is blocked on **trustworthy audio filler evidence**, not lack of API keys. One reported speech chain succeeded; reliable live calls and filler localization have not been established. We will not freeze Phase 03 or start the UI group as though that were solved.

## First: rotate the posted keys

Use the private setup in [`../provider-access.md`](../provider-access.md). Do not paste replacement values into chat. Reply with configuration/rotation status only. The values already posted will not be embedded in prompts.

## A. Review one existing clip — recommended, no new inference spend

Open the local synthetic file:

**[`../../fixtures/synthetic/audio/spoken-filled-hesitation.wav`](../../fixtures/synthetic/audio/spoken-filled-hesitation.wav)**

The intended text was “So um I think the timeline is, uh, probably next month.” The recognized text omitted “um” and “uh.” The file has not been independently listened to by CEO or a human reviewer in the supplied report.

Please answer: **Do you actually hear “um” and/or “uh”?**

- **Both / one present:** that sample's recognition omitted an audible event. This does not prove permanent inability across all Gnani configurations; it motivates testing a disfluency-preserving/audio-aware path on verified examples.
- **Neither present:** the fixture does not establish the claimed recognizer failure. Repair the fixture before evaluating filler recognition.
- **Unclear / file unavailable:** leave labels unverified and arrange a valid clip; do not guess.

Record approximate event positions if convenient. A builder must tie any accepted annotation to this file's hash, reviewer and date, without overwriting the original asset. One reviewed clip is **not** the required held-out evaluation set and does not meet the accuracy target by itself.

## B. After that fact, choose the product/research direction

| Choice | Outcome | Trade-off |
|---|---|---|
| **Preserve original goal — recommended** | Authorize one bounded, source-verified disfluency/audio-review experiment after clip review | Needs credible labels and language-specific evidence; no promise of success |
| Narrow initial release explicitly | Conversation plus pause/pace estimates; disable unvalidated filler localization | A user-approved scope change and revised acceptance plan, **not** fulfillment of the original goal |
| Pause assessment work | Keep the prototype and wait for suitable data/access/reviewer | Honest stop; do not spend through repeated guesses |

No new detector, training project or narrowed acceptance is assumed until you choose. The concrete offline repairs in FIX-1 are independent of this choice.

## C. Reasoning provider comparison — separate from audio assessment

Your supplied provider list permits us to prepare a **small optional comparison** of corrected Gemini, one documented Groq model and one hosted NVIDIA NIM model. After fresh keys and fixed accounting, use the same short synthetic text turns, output limits and timeout budget; keep Gnani STT/TTS unchanged. Record latency, failures, reply relevance and selected-language behavior. No tools, automatic failover or production-provider change.

Reply **“compare reasoning providers”** to authorize that live comparison, or **“keep Gemini for now.”** New text models do not, by themselves, create ground-truth filler labels or word-level audio timing.

Suggested concise reply: **“Keys rotated/configured privately; A: both/one/neither/unclear; B: preserve/narrow/pause; C: compare/keep.”**

No phase-type or parallel-map change has been made. No benchmark, audio playback or agent execution was performed by CEO.
