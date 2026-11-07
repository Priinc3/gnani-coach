# Speaking coach — discovery and brainstorm

Status: **2026-10-23: B2 TEST skipped by user order (W06); B1 and B2 NOT VERIFIED. B3 opened: BUILDs for 07, 08, 09 and `batch-B3-TEST.md` issued; the B3 TEST folds in the B1 and B2 checks and is the first independent test of the whole system. Contest deadline 2026-11-10. Filler = unvalidated; goal preserved. Phase map unchanged; Phase 08 gets a data-only grant on catalog capability flags.**

Read `challenge.md` and checked current public documentation on 2026-10-16, including the live speech endpoints after your answers. Sources: [research.md](research.md). Language findings: [language-support.md](language-support.md). Product choices below are distinguished from recommendations and untested capabilities.

## 1. Your decisions — captured

| Topic | Your answer | Product consequence |
|---|---|---|
| Audience | All the proposed learner groups | One core coach with interview, workplace, everyday, and travel/social scenario presets—not separate apps |
| Languages | Ask the learner; check Gnani support | Separate speaking-language and coaching-language selectors; support follows verified endpoint capabilities |
| Interaction | Call | Continuous hands-free conversation, not tap-to-submit clips |
| Main value | Accept the recommendation | Audio-grounded pause/filler feedback and a useful retry, supported by realistic conversation |
| Corrections | In batches after a few exchanges | Conversation rounds separated by short coaching breaks |
| Recording | Save audio only if the learner agrees; otherwise metrics only | Optional recording retention, with a genuinely content-free metrics-only persistence path |
| Budget | Do not dwell on it now | Postpone detailed costing; retain basic usage limits and clear credit-exhaustion behavior |
| Build team | Solo, using AI agents | You manually run engineer prompts; parallel work only with separate file ownership |

**Language finding:** the reviewed Gnani realtime STT and realtime TTS documentation share **10 named languages**: English, Hindi, Bengali, Gujarati, Kannada, Malayalam, Marathi, Punjabi, Tamil, and Telugu. TTS also documents a Hinglish option; STT describes Hindi–English mixed input under English. French is not listed on these endpoints. This is documented support, not proof that our app or your account has passed tests in all ten. [S11–S13]

Your answers replace the earlier one-language, one-persona, push-to-talk proposal. Your subsequent “start the project” request starts prompt preparation using the conservative defaults in §8; no more budget questions now. The frozen phase and ownership map is in §9.

## 2. My recommended product direction

**“Practice a real conversation. Hear where you got stuck. Try again with one specific improvement.”**

Your important insight is that **what someone said and how they delivered it are different inputs**. The product should preserve that distinction all the way to the report.

Do not position it merely as “chat with an AI in another language.” Our proposed differentiator is an **audio-linked coaching loop**. Competitive uniqueness remains unvalidated.

### Broad audience, shared product

Let the learner choose **what they want to practice today**, rather than forcing them into a demographic category. Interview, meeting, daily conversation, and travel/social presets can share the same call, measurement, and coaching engine. Add a level choice and optional custom topic; avoid collecting a résumé or personal background just to start.

The intended language catalog includes all ten documented STT/TTS languages. Track conversation support and assessment support separately: a language being speakable does not prove that our filler detector or coach is accurate in it. Do not silently shrink the catalog or claim equal assessment quality. Regional/code-mixed practice also matches challenge award categories, without guaranteeing selection. [S1, S11–S13]

### Proposed one-line DONE condition

**A learner chooses a scenario and an enabled language, completes a natural AI voice call with coaching breaks, receives audio-grounded feedback, retries a target skill, and retains metrics—with replayable recordings only on opt-in; every enabled capability passes documented acceptance and privacy checks using genuine Gnani STT/TTS.**

This is a proposed app acceptance condition—not a promise that one session makes someone proficient. Contest completion additionally needs the working public demo, nominated social post, written explanation, technology attribution, contributions, and submission. [S1–S2]

### The session loop

1. Choose scenario, level, speaking language, and coaching language.
2. Explain live processing separately from optional recording storage; check the microphone; press “Start call.”
3. **Practice round:** have a natural conversation. Proposed default: four completed learner turns; this number is adjustable, not something you already specified.
4. **Coaching break:** at a natural boundary, announce a short review: one strength, one delivery improvement, and optionally one language improvement. Proposed length: 20–40 seconds; do not read a full report aloud.
5. **Retry:** repeat or reframe one answer, hear specific feedback, then continue the scenario. Offer “Keep talking,” “Coach me now,” and “Skip feedback.”
6. **End:** show a session summary and comparable retry metrics. Saved replay exists only for recordings the learner allowed us to retain.

Count conversational turns, not STT chunks. A learner's sentence can produce multiple transcript segments. If a round contains too little speech, explain that and continue rather than manufacture feedback. Track coached retries separately from ordinary roleplay. An end-session report summarizes existing round results; it should not invent another conflicting evaluation.

Example report wording, **illustrative only**: “There was a long pause before your main point. Listen to this moment, then try opening with your conclusion.” Only insert a time range or measured number when real evidence supports it.

## 3. How we could implement the intelligence

### Two paths from the same audio stream

**Live conversation path:** microphone → our backend → Gnani Prisma realtime STT → external conversation LLM → Gnani Timbre realtime TTS → streamed playback.

**Parallel analysis path:** the learner's own audio stream → quality and speech-region analysis → timing measurements and candidate event verification → round coach/report using both audio evidence and transcript. Runtime parallelism here is separate from any future engineer-agent parallel group.

Keep detailed analysis off the ordinary conversational response path. A session controller decides when to transition between practice, coaching, retry, and end; the LLM does not get to arbitrarily rewrite those rules.

**Important live-call constraints from the actual docs:**

- Gnani realtime STT accepts paced raw PCM frames, not arbitrary browser recording blobs. Its VAD produces completed speech segments; a segment ending does **not** prove the learner has finished their thought. [S11]
- The STT docs require connection headers and explicitly recommend a backend proxy for browsers. Keep provider keys there, never in the client. [S11]
- Plan interruption support: when the learner starts speaking, stop audible coach playback and prevent stale output from playing later. TTS documents one synthesis request at a time and no cancellation message on the reviewed page; cancellation/reconnection behavior must be validated, not invented. [S12]
- Keep a learner-audio sample clock and connection/turn identifiers. Server emission timestamps and segment durations are not word-level alignment. Preserve gaps across chunks; never derive a pause solely from network timing. [S11]
- The documented STT connection cap is 15 minutes. Proposed initial call length: 5–10 minutes, with a warning and clean ending before the cap; longer calls need a validated rollover design. This supersedes the earlier REST clip-limit approach. [S11]

| Component | Candidate responsibility | Boundary |
|---|---|---|
| Gnani Prisma | Realtime speech-to-text, using spoken-form output for analysis | `verbatim` is documented, but filler preservation still needs evidence. Reviewed realtime responses do not document word timings. [S11] |
| Gnani Timbre | Stream roleplay and coaching speech | Verify account-enabled model/voice/language; current realtime docs list v2.5 and v3.0. [S12–S13] |
| External conversation LLM | Roleplay, follow-ups, difficulty, explanations | Gemini is the selected initial provider family; validate the exact model/task before use. Groq is an alternative, not a required second build. [S5–S6] |
| Audio measurement worker | Speech intervals, within-turn silence, duration, quality flags | Silero VAD is selected for speech-region estimates, **not word/filler recognition**. Exact package/runtime and compatibility remain to be verified. [S7; stack-decisions.md] |
| Optional audio reviewer | Listen to selected clips to suggest or check coaching observations | Gemini documents audio understanding; that is not proof of accurate filler counts or pronunciation grading. [S5] |
| Coach/report composer | Combine measured facts, language observations, and a targeted exercise | May explain measurements, never invent or silently replace them |

### “Agents” should have clear jobs, not just extra model calls

Start with a conversation role, a measurement worker, and a coaching/report role, coordinated by the session controller. The coach can generate the retry exercise in the same bounded operation. We do not need autonomous agents debating each turn. AI builder agents are a separate concern: they implement these components from prompts you run manually.

Proposed report evidence contract: observation type, recording/turn reference, start/end time where available, evidence source, measured value and unit where relevant, reliability/limitations, and coaching suggestion. This is a contract sketch, **not yet a frozen schema**. Structured output can constrain shape; it does not establish factual correctness. [S6, S9]

The initial stack is now selected: **Next.js/TypeScript web app, Python/FastAPI voice service, Gnani realtime STT/TTS, Gemini as the initial external LLM, Silero VAD for speech-region estimates, and Supabase for later identity/metrics/private recordings**. See [stack-decisions.md](stack-decisions.md) for researched rationale, version policy, validators, tests, and boundaries. Exact package pins are a Phase 01 deliverable; actual speech/model access and filler assessment feasibility are Phase 02 deliverables. No runtime success is implied by selection.

### Gemini or Groq?

- **Gemini candidate:** useful if we want a secondary audio-aware review in addition to text reasoning. Keep Gnani as the actual primary STT/TTS path. [S3–S5]
- **Groq-hosted model candidate:** evaluate for text conversation and reports from supplied measurements. Groq is the hosting platform; Qwen is a model family. Do not assume any chosen model accepts raw audio. Availability and structured-output support are model-specific. [S6]
- Start with Gemini behind a provider interface; verify the current account-accessible model during Phase 02 rather than hardcoding an untested model ID. Groq remains a replacement candidate, not a second implementation to build immediately. If Gemini fails the task evaluation, report the evidence before changing providers. Detailed cost optimization is deferred as requested.
- Do not claim an entirely sovereign/India-only pipeline if audio or text goes to an external provider. Provider data terms and processing locations need a separate review before real-user use.

## 4. What audio can—and cannot—justify

| Feedback | Proposed evidence | Honesty rule |
|---|---|---|
| Pauses and speaking duration | Speech/non-speech intervals from audio | Estimated boundaries; exclude assistant audio and leading/trailing waiting time. A pause is not automatically a mistake. [S7] |
| Speaking rate | Recognized word count ÷ learner turn span, expressed per minute | Hybrid text+audio estimate; wrong transcription changes the result. Never use total session time. |
| Speech-active rate | Recognized words ÷ detected speech-active duration | Show separately from overall rate; do not compare languages using one universal “ideal” band. |
| Filled pauses, such as “um” | Disfluency-preserving recognition plus audio checking and validated timing | VAD alone cannot identify an “um.” Never call missing transcript fillers “zero fillers.” [S3, S7–S8] |
| “Like,” “so,” “you know” | Context review plus audio-linked candidate occurrences | Not every occurrence is a filler; uncertainty should remain visible. |
| Grammar and answer structure | Recognized/corrected text plus scenario | Do not punish recognition errors or enforce formal writing rules on every spoken sentence. |
| Pronunciation | Language-specific audio assessment with a validated rubric | Defer phoneme-level scores until proven; successful transcription is not pronunciation assessment. |

**The hardest technical risk is reliable filler localization.** Forced alignment maps supplied text to audio; it is not a replacement for recognizing omitted words. If recognition drops a hesitation, merely aligning the cleaned transcript does not establish where that missing hesitation occurred. [S8]

For the first capability check, use permitted, annotated clips with known silences, repetitions, and filled pauses. Compare speech boundaries, event precision/recall, and timestamp error against the annotations. Test clips where recognition omits fillers. Synthetic fixtures help test mechanics but cannot establish accuracy on natural learners.

If filler evidence fails, either validate a dedicated disfluency component or explicitly narrow the feature with your approval. **Do not quietly ship transcript-only filler analysis as audio analysis.** Exact tolerances and required coverage will be agreed before the engineer's batch test.

Avoid “confidence,” intelligence, personality, accent-quality, or clinical scores inferred from voice. Offer descriptive practice feedback, allow disputed observations, and compare a learner with their own earlier attempts—not an unexplained leaderboard.

## 5. Important edge cases

These are proposed product requirements and future test cases, not claims that safeguards already exist.

| Situation | Expected behavior |
|---|---|
| Silence, empty audio, or too little speech across a round | Explain that there is not enough evidence and continue/retry; no fabricated score or divide-by-zero. A valid one-word “yes” can still advance the conversation |
| Background noise, clipping, whispering, or another speaker | Flag weak evidence; ask for a retry rather than confidently grading |
| Long thinking pause | Use a learner-friendly end-of-turn policy; STT segmentation alone must not make the coach interrupt every pause. Include a “Give me a moment” control |
| Assistant audio re-enters the microphone | Keep speaker tracks/turns distinct; never score the coach as the learner |
| Hinglish, regional accent, unfamiliar name | Preserve intended code-switching; let the learner correct recognition before language feedback |
| Stutter or other speech difference | Optional delivery coaching; no diagnosis, shame, or automatic “bad speaker” label |
| Filler omitted by STT | Report unavailable/uncertain evidence, not a clean bill of fluency |
| Denied microphone, unsupported capture format, mobile interruption | Plain-word recovery and retry; browser microphone access requires a secure context and permission. [S10] |
| Slow/offline connection, rate limit, expired credits | Visible status promptly; bounded retry/cancel; no duplicate turns or uncontrolled spend |
| Duplicate segments or delayed result from an old turn | Deduplicate within connection/session identity; attach analysis to the correct round; suppress cancelled speech |
| Long uninterrupted speech or connection cap | Segment without truncating the learner's thought; warn/end or perform validated rollover before the realtime cap. [S11] |
| Malformed/oversized audio or malicious transcript | Validate upload type/size/duration; treat transcript as untrusted data; validate model output. [S9] |
| Another user requests a recording/report | Enforce access isolation before returning data; test this if persistence/accounts are included. [S9] |
| Learner wants to discard an attempt | Confirm discard where needed, provide undo before final purge, and accurately state retention limits |
| Noise triggers an interruption | Distinguish short noises from speech; prevent repeated stop/start loops; offer a headset/microphone check |
| User speaks during feedback | Stop coach playback, preserve round state, and respond; do not count an acknowledgement as an entire new practice round |
| Language changes during the call | Apply deliberately at a round boundary, confirm the selection, and reconnect STT where required; do not discard the previous round. [S11] |
| Declines storage, withdraws consent, or disconnects during saving | Stop disallowed writes; cancel/fence pending jobs so late results cannot recreate deleted content |

UX targets to validate: obvious next action, local feedback within one second, and no dead-end error screens. **That is not a promise of a sub-second AI voice reply.** Report actual end-of-turn-to-first-audio latency separately.

## 6. Recording consent and metrics-only storage

Your storage choice works, but **processing audio now is different from saving it for later**. Proposed consent UX: explain which providers process speech, then separately ask “Save my recording so I can replay it later?” Leave optional recording storage off by default.

| Data | Recording OFF | Recording ON |
|---|---|---|
| Learner audio | Bounded temporary processing only; no durable recording | Private retained recording under an explicit retention/deletion policy |
| Full transcript, quoted mistakes, personalized report text | Temporary for the call/coaching; not quietly saved as “metrics” | Still not automatically retained: permission to save audio is not blanket permission to retain every derived artifact |
| Numeric metrics and necessary metadata | Save duration, estimated rates, pause/event counts where supported, language/scenario, and method/reliability metadata | Same metrics, plus authorized recording references |
| Replay | Temporary during the active session, if disclosed; unavailable once buffers are cleared | Available while the retained recording exists |

Metrics-only mode must cover logs, tracing, caches, background jobs, and crash paths—not just an “audio upload” switch. Do not persist arbitrary LLM-generated text or embeddings as metrics. User-linked metrics are not automatically anonymous. Enforce access isolation and content-free operational logging. [S9, S14]

**Provider boundary:** Gnani's STT page says its billing records carry the original raw transcript. Our toggle cannot promise zero provider retention. Before real-user launch, verify the selected providers' processing/retention terms and disclose the actual behavior; do not claim “your data is never stored anywhere.” [S11]

Record the consent state/version at ingestion and at durable write time. Later opt-in is not retroactive permission to recover already-discarded audio. Withdrawal stops future retention; make deletion of previous recordings a clear action. Temporary cleanup, saved-recording lifetime, backups, and deletion timing need explicit acceptance criteria before implementation.

**Budget:** detailed costing is parked, as requested. Keep connection/session limits, bounded retries, basic usage monitoring, and a clear exhausted-credit state. No claim that programme credits equal US dollars. [S1–S2, S14]

## 7. Scope to keep and scope to defer

**Visual direction update:** the user supplied root `UI.png` and asked that the UI builder use it. See [Phase 04 UI reference](phase-04-call-ui/UI-REFERENCE.md): Speakify's illustrated, soft white/teal, bold sans-serif desktop/mobile design supersedes the Phase 01 starter look. Phase 03 must account for it before freezing shared UI seams; Phase 04 must open the actual image. This changes visual requirements, not phase types/ownership or privacy/scoring rules. Do not copy mock scores, retention-ON, or push-to-talk behavior as product requirements.

**Launch direction:** call-first coach; all requested scenario categories through presets; user-selectable language catalog based on the ten documented languages; periodic coaching; audio evidence; retry comparison; opt-in recording and metrics-only history. Each enabled language/capability needs its own validation status, including coaching-language pairs. A failed language or detector requires a disclosed limitation and your scope decision—not a fabricated pass.

**Proposed deferrals:** native apps if web-first is approved, unsupported languages, voice cloning, teacher dashboards, social feeds, subscription billing, fine-tuning, and certified pronunciation/proficiency scores. **Interruptible live calls are now part of the proposed core experience**, not silently deferred in favor of push-to-talk.

The memorable demo is not a dashboard full of percentages. It is: **speak → see a real moment you can replay → understand one change → try it again.**

## 8. Starting defaults and authorization boundary

To honor “start the project,” proceed without another questionnaire. These are **implementation assumptions**, not a claim that you explicitly answered the remaining A–C questions:

- Mobile-friendly website with an **in-browser audio call**, not PSTN/phone-number calling or a native app.
- Guest preview; sign-in for cross-device saved metrics and opt-in recordings. Guest preview does not silently create a persistent personal-data account.
- **18+ pilot**; “all” covers scenario categories, not automatic inclusion of children.
- Four completed learner turns per coaching round, a 5–10-minute call, short skippable feedback, and learner interruption support.
- Recording retention defaults off. With opt-in, propose a visible 30-day recording lifetime and earlier user deletion; exact provider/backups behavior must be disclosed before enabling retention.

You can change these assumptions. A phase-type or parallel-map change requires your approval. Foundation work needs no credentials. Before live evaluation, the builder will report required environment-variable names, never request secrets in chat or reports. Missing credentials or recording-policy approval block live verification, not local scaffolding.

“Start” authorizes preparation of the first engineer prompt. You run it manually. It does not authorize this orchestrator to code, launch agents, deploy publicly, incur purchases, post a demo, or declare success.

## 9. Frozen execution plan v1

### DONE

The §2 goal is met **and** all three batches and the final cross-batch acceptance pass with evidence. No 🔴/🟠 findings remain; 🟡 findings are fixed or explicitly `WAIVED: reason`. Core live-call, privacy, and audio-evidence requirements cannot be waived into a success claim. Publication/submission remains a separately user-authorized action.

### Phase list and ownership

Paths are relative to the repository root. The table assigns exclusive write ownership while a phase is active. Later sequential ownership handoffs listed here are intentional; they do not allow concurrent edits. Each builder may also write only its own `prompts/phase-NN-<slug>/REPORT.md` and evidence subfolder. Planning, BUILD/FIX/VERIFY files, and the tracker stay CEO-owned.

| Phase | Type | Batch | Goal and OWN files |
|---|---|---|---|
| **01 foundation** | `NORMAL` | B1 | Reproducible web/service skeleton and draft shared contracts. Root manifests/locks/ignore/runtime files and README; `apps/web/` scaffold only; `packages/contracts/**`; `services/voice/{pyproject.toml,uv.lock,.python-version}`; `services/voice/src/gnani_coach/{__init__.py,main.py,settings.py}`; `services/voice/tests/foundation/**`; `docs/{architecture.md,toolchain.md,design-direction.md}`. Exact allowlist in BUILD. |
| **02 provider-feasibility** | `NORMAL` | B1 | Real provider adapters and bounded speech/analysis probes, no finished product UI. `services/voice/src/gnani_coach/providers/**`; `services/voice/tests/providers/**`; `tools/probes/**`; `fixtures/synthetic/**`; `docs/feasibility/**`. Temporary ownership of voice dependency manifest/lock for researched provider/audio additions. |
| **03 contract-freeze** | `NORMAL` | B1 | Turn measured capabilities into frozen contracts, module ports, fixtures and mounted integration seams. `packages/contracts/**`; `services/voice/src/gnani_coach/{main.py,settings.py,ports/**}`; `apps/web/src/app/{layout.tsx,page.tsx,globals.css}`; root/workspace manifests, locks, configs and scripts; `tests/integration/**`; `docs/contracts/**`. May create initial stubs in Phase 04–06 directories, with explicit handoff at completion. |
| **04 call-ui** | `PARALLEL:G1` | B2 | Responsive onboarding/call/round-coaching/evidence/history UI and real audio transport. `apps/web/src/features/**`; `apps/web/src/lib/{audio,transport,session-ui}/**`; `apps/web/tests/**`. |
| **05 coaching-runtime** | `PARALLEL:G1` | B2 | Turn controller, interruptible conversation, audio metrics, validated filler evidence, round feedback and retry. `services/voice/src/gnani_coach/{conversation,analysis}/**`; `services/voice/tests/{conversation,analysis}/**`. |
| **06 private-history** | `PARALLEL:G1` | B2 | Identity, metrics-only persistence, optional recording lifecycle and private access. `services/voice/src/gnani_coach/{identity,persistence}/**`; `services/voice/tests/{identity,persistence}/**`; `supabase/**`; `apps/web/src/lib/auth/**`; `apps/web/src/app/auth/**`; `apps/web/src/proxy.ts`. |
| **07 resilience** | `NORMAL` | B3 | Complete call/privacy/failure hardening and integration cleanup after G1 has already passed its integration gate. Explicit exclusive successor ownership of `apps/web/**`, `services/voice/**`, `supabase/**`, `tests/integration/**`, root dependency/config files, `docs/operations/**`; no siblings active. |
| **08 language-acceptance** | `NORMAL` | B3 | Validate ten-language catalog, selected coaching pairs, evidence accuracy, accessibility and release capability states. `tests/acceptance/**`; `fixtures/evaluation/**`; `packages/contracts/data/capabilities.json`; `docs/evaluation/**`. Contract shape remains frozen; only capability data changes. |
| **09 release-package** | `NORMAL` | B3 | Deployment configuration, reproducible release and honest contest handoff materials. `deploy/**`; `.github/**`; root `README.md`, `CHANGELOG.md`, `.env.example`; `docs/release/**`; `tests/release/**`; `scripts/release/**`. Do not publish, provision paid services, or post socially without user approval. |

Phase 01 corrections remain reviewed with the scoped [waivers](waivers.md). Phase 02's [report review](phase-02-provider-feasibility/VERIFY.md) now preserves one chain milestone but identifies budget/lifecycle/matrix/evidence defects and a blocked filler-localization goal. [FIX-1](phase-02-provider-feasibility/FIX-1.md) is prepared for manual offline repairs; the [user decision](phase-02-provider-feasibility/DECISION-NEEDED.md) and [private provider-access handoff](provider-access.md) govern the next live/assessment work. Groq and hosted NIM are documented optional reasoning-comparison candidates following the user's provider list, not silent replacements or a new self-hosting phase. No Phase 03/G1 release, production model freeze or scope reduction occurs on this report alone.

### Batch schedule

| Batch | Members | Type | Required acceptance scope |
|---|---|---|---|
| B1 | 01 → 02 → 03 | `NORMAL` | Foundation, actual Gnani/Gemini probes, audio evidence feasibility, cross-language schema agreement, integration seams, credential/privacy boundaries |
| B2 | 04 + 05 + 06 | `PARALLEL:G1` | End-to-end browser call through real providers, round coaching/retry, interruptions, identity and both retention modes; prove siblings compose correctly |
| B3 | 07 → 08 → 09 | `NORMAL` | Resilience/security, all enabled language capabilities, mobile/accessibility, release configuration and full regression |

One formal `batch-Bx-TEST.md` is issued after each three-phase build batch or complete G1 group; each orders `batch-Bx-TEST-RESULT.md` with raw output. Do not create per-phase TEST files or describe compilation as completed batch acceptance. Ordered construction inside an admitted batch is tracked as **BUILT / AWAITING BATCH TEST**, not VERIFIED advancement. Each manual handoff needs its REPORT; nobody runs a successor automatically. No next batch is admitted until `✅ VERIFIED` and your `next`.

### Parallel group G1 — frozen map

- **Goal:** complete call UI, coaching runtime, and private history concurrently against B1's proven contract.
- **Members:** Phase 04, Phase 05, Phase 06. There are no overlapping application OWN paths.
- **Shared read-only:** `packages/contracts/**` except later Phase 08 data handoff; provider adapters and fixtures from Phase 02; `services/voice/src/gnani_coach/ports/**`; composition roots; all dependency manifests/locks; `docs/contracts/**`.
- **Integration points:** `apps/web/src/app/page.tsx` mounts the documented feature entry point; `services/voice/src/gnani_coach/main.py` mounts the documented conversation and persistence routes and injects identity/storage ports. Phase 03 must define actual export names, routes, and unavailable behavior before freeze. No sibling guesses another sibling's API.
- **Communication folder:** `prompts/parallel-G1/`. Not created now; the first G1 builder creates `COMM.md` and `STATUS.md` from its BUILD stubs, and others update only their own presence rows.
- **Safe because:** disjoint write sets, no shared manifests during G1, frozen language/event/persistence/auth boundaries, and pre-mounted composition roots. Every parallel BUILD will repeat all sibling paths, OWN/DO NOT TOUCH lists and read-only contract.
- **Coordination exception:** short shared COMM/STATUS updates are allowed by the per-author/row rules only; they do not permit shared application-file writes. `HELP:` on a shared change, then wait for CEO FIX; no silent edits.
- **Integration TEST:** B2 runs the assembled browser + voice + identity/storage system, not three isolated green suites. Authenticated recording OFF/ON, interrupted TTS, four-turn coaching, retry comparison, and incorrect/expired identity all cross module boundaries.
- **Failure handling:** ownership clash is 🔴 and freezes G1. Contract/integration failure is coordinated through a FIX on contract-owner Phase 03, with other members waiting; any reassignments must be explicit. No same bug patched independently in multiple modules.

### Acceptance targets, not measured claims

- All ten catalog languages need genuine STT/TTS checks and intelligible coaching before claiming all-ten coverage. Coaching pairs and Hinglish carry separate evidence states; failed core coverage requires user-approved scope change.
- Healthy-network call baseline: at least 30 measured learner turns; proposed p95 end-of-turn-to-first-audible-response ≤3 seconds, with endpointing and provider latency broken out. UI feedback <1 second. Interruption-to-playback-stop target p95 ≤300 ms over 20 trials. No stale audio after cancel/end.
- Four completed learner turns trigger one natural coaching break, not four STT segments. Retry must use the same metric definition and a comparable prompt; no guaranteed improvement claim.
- For every enabled filler mode: separate held-out annotated positives/negatives, at least 20 of each; proposed event precision ≥90%, recall ≥80%, matched-event boundary p95 error ≤300 ms. Synthetic-only evaluation must be labeled and cannot prove natural-learner accuracy. Phase 02 must assess practicality before freeze; do not relax targets silently.
- Pause fixtures must preserve known gaps across stream chunks and exclude coach audio; no score for insufficient/noisy evidence. Report actual measurement error against annotations, never provider emission time as word timing.
- Metrics-only persistence inspection must find no recordings, transcripts, quoted feedback, embeddings, or content-bearing logs/cache/jobs in our durable systems. Opt-in recordings require owner-only access, expiry, and deletion tests, including late-job resurrection prevention.
- Test happy path + top three edges + security probe + cross-phase integration in every batch. Prioritize silence/noise, long pause/interruption, disconnect/duplicate events, and unauthorized access; final regression additionally covers expired auth and 10× bounded load.
- Final gate: all batch evidence/VERIFY files exist, 0 🔴/🟠, every 🟡 fixed or explicitly waived, all enabled claims trace to evidence, and `prompts/final-TEST.md` plus its result prove the DONE condition. CEO updates tracker and records a changelog note; never call the prototype done just because scaffolding compiles.

The orchestrator has only read/researched and edited prompt documents. No app code, shell command, test, provider inference call, or engineer launch was performed.
