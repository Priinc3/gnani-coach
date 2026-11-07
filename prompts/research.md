# Discovery evidence — 2026-10-16

Scope: targeted web searches and public-document reads to inform brainstorming. **Documentation evidence only:** no provider calls, accuracy benchmarks, pricing verification inside an account, or app tests.

## 1. Sources and what they establish

| ID | Source | Finding and boundary |
|---|---|---|
| S1 | [Gnani internship challenge](https://www.gnani.ai/internship) — full page read | Open brief, genuine Gnani use, 5,000 programme credits, deadline November 10, 2026 at 11:59 PM IST, regional/code-mixed categories, working public demo and submission requirements. Not evidence that credits equal dollars. |
| S2 | [Registration participation terms](https://www.gnani.ai/great-indian-ai-internship-registration-form) — full page read | Working application using Gnani models/APIs; 5,000 programme credits; identify technologies/contributions; public video and nominated posts. Does not explicitly confirm this exact external-LLM architecture or settle all recording-policy questions. |
| S3 | [Gnani STT REST reference](https://docs.gnani.ai/api/STT/speech-to-text) — full page read | `format=verbatim` returns spoken-form output; ten listed languages include English and regional Indian languages, not French. Response has transcript and request timestamp, not documented word-level time offsets. Main text says maximum 60 seconds/ideal 30; part of embedded OpenAPI says maximum 30. Treat limit inconsistency as unresolved; propose short turns of no more than 30 seconds until validated. |
| S4 | [Gnani TTS REST reference](https://docs.gnani.ai/api/TTS/tts-inference) — full page read | Lists `timbre-v2.5` and `timbre-v3.0`, model-specific voices, ten supported languages and a Hinglish language option. No French listed. Links to streaming endpoints do not prove this app's latency or account access. |
| S5 | [Gemini audio understanding](https://ai.google.dev/gemini-api/docs/audio) — full page read | Audio input with text responses, segment-oriented questions, transcription, and timestamps are documented. Does not establish calibrated pronunciation scores, accurate filler counts, or millisecond alignment for our task. No model version selected. |
| S6 | [Groq supported models](https://console.groq.com/docs/models) and [structured outputs](https://console.groq.com/docs/structured-outputs) — search results reviewed | Current model availability and model-dependent structured-output modes are documented. Must recheck exact model and input modalities before selection; no speed/quality winner inferred from advertised tokens/second. |
| S7 | [Silero VAD repository](https://github.com/snakers4/silero-vad) — search result reviewed | Documents speech timestamps, including return values in seconds. Candidate for speech-region detection only; local runtime, noise robustness, licensing/version review, and selected-language behavior still need validation. |
| S8 | [Montreal Forced Aligner guide](https://montreal-forced-aligner.readthedocs.io/en/latest/user_guide/index.html) and [forced-alignment comparison](https://arxiv.org/html/2406.19363v1) — search results reviewed | Forced alignment concerns alignment of speech signals with corresponding supplied transcriptions. It is not evidence that omitted fillers will be recovered. No aligner, acoustic model, language coverage, or package version selected. |
| S9 | [OWASP LLM prompt injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) and [file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) — search results reviewed | Security review starting points for untrusted speech-derived text and uploaded audio. Safeguards in the brainstorm are proposed requirements, not a security certification. Detailed auth, secret handling, retention, and deployment decisions require their own source review and tests. |
| S10 | [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) — search result reviewed | Browser microphone access is constrained by secure contexts and permission policy. Capture/playback formats and target-browser behavior remain to be checked. |
| S11 | [Gnani realtime STT](https://docs.gnani.ai/api/STT/stt-websocket) — searched and full page read after user selected calls | Ten-language list; raw mono signed 16-bit PCM, 1,024-byte frames at the actual sample-rate cadence; VAD-segment transcripts; documented 15-minute connection cap. Browser proxy explicitly recommended for custom headers/key protection. Transcript timestamps are emission times, not word boundaries. Language/VAD changes require reconnect; documented exceptions concern substitution/boosting. Billing-record note says original raw transcripts are retained there. |
| S12 | [Gnani realtime TTS](https://docs.gnani.ai/api/TTS/tts-websocket) — reached through searched Gnani API introduction and full page read | Same ten languages plus `hi-en` option; v2.5/v3.0; ordered base64 audio chunks; one synthesis request at a time. No synthesis cancellation message documented on the reviewed page. OGG/Opus is described as a single chunk after synthesis, so it must not be assumed to deliver incremental audio. |
| S13 | [Gnani voice catalog](https://docs.gnani.ai/api/TTS/available-voices) — followed from live TTS docs and full page read | 42 v2.5 voices with preferred languages; 13 v3.0 voices documented for all ten languages. Wrong model/voice pairing rejected. Counts do not prove account access or app quality. |
| S14 | [OWASP WebSocket Security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html) — searched and full page read | WSS, origin validation, authentication and message authorization, expiry handling, resource limits/backpressure, and avoiding sensitive content in logs. Apply limits appropriate to paced audio frames; generic chat message-rate examples are not audio-stream settings. |

## 2. Important corrections to the local challenge summary

`challenge.md` is useful context but is not authoritative API documentation or current legal advice. It was not edited.

1. **Credit amount:** the user mentioned dollars; both public challenge pages say **5,000 programme credits**. Currency equivalence, usage rates, expiry, and enabled services remain unknown.
2. **Language breadth:** the local summary mentions 40+ STT languages and 21+ TTS languages. The reviewed integration references list narrower endpoint support. Do not promise French or “any language” based on marketing totals.
3. **TTS versions:** the local summary centers v2.5. Current REST and realtime TTS docs also list v3.0. Neither newest nor account-enabled should be assumed without checking.
4. **Timing fields:** the STT REST response's `timestamp` is a **server request timestamp**, not where a learner said a word. It cannot power a word-highlight timeline.
5. **Clip duration:** REST prose and embedded schema disagree in places. The user subsequently chose live calls: the current proposal uses realtime STT, whose documented connection cap is 15 minutes. REST clip constraints remain relevant only for separately scoped clip operations, not a reason to force tap-to-submit interaction.
6. **Hybrid eligibility:** the local summary states an external-model hybrid is compliant. Public terms require genuine Gnani use but do not explicitly adjudicate this architecture. Treat hybrid as plausible, not organizer-approved; request confirmation before making eligibility promises.
7. **Synthetic-only statement:** `challenge.md:61` and `challenge.md:181` assert broad restrictions on real personal data/recordings. That exact broad prohibition was not found in the text retrieved from S1/S2. Absence in the retrieved text is **not permission**. Check the accepted terms and ask the organizer whether consented live microphone practice, recordings, and third-party LLM processing are permitted. Until then, propose synthetic fixtures for shared/public material and no collection of third-party recordings.
8. **Schedule:** use the verified closing date, not the local summary's inconsistent “31 days” build-window label.

## 3. Questions for the organizer or account dashboard

- Deferred at the user's request: detailed tariffs, credit denomination, and capacity estimates. Before public operation retain basic usage limits and failure handling; do not assume unlimited credit.
- Which exact speech models, endpoints, languages, and voices can this account access under the programme credits?
- Does any accessible STT endpoint return word times and recognition confidence, and does it preserve filled pauses/repetitions? Which output examples document that?
- May we use Gemini or a Groq-hosted LLM for conversation/coaching while using Gnani for actual STT and TTS?
- Are consented live voice sessions allowed? What may be stored, sent to external providers, or included in a public demo? Do synthetic-data rules apply differently to evaluation and live use?

## 4. Open evidence gaps

- No measured end-to-end latency, learner-audio accuracy, alignment/filler localization, pronunciation assessment, or cost-per-session.
- After the user's start request, framework/persistence/auth/provider-family choices are recorded in `stack-decisions.md`; exact package compatibility, model IDs and deployment host remain unverified. Earlier discovery text is historical, not a reason to invent runtime evidence.
- No reviewed provider data-retention/training terms for the eventual accounts and plans; no data-residency guarantee.
- No evidence yet of learning gains or competitive uniqueness. A synthetic before/after clip is a functional demonstration, not a user-study result.

Before BUILD prompts, revisit the selected technologies' primary docs and convert these gaps into scoped deliverables and batch acceptance checks. Never turn a documented feature into a claim that our implementation has been verified.

## 5. Discovery v2: implications of the user's choices

- “Call” replaces the earlier push-to-talk recommendation; live segmentation, interruption, echo, stale output, and session caps now matter to the core flow.
- “All” covers the proposed audiences/use cases. Initial age eligibility is still a user decision, not inferred authorization to include minors.
- Periodic feedback means completed learner turns must be counted separately from provider transcript chunks and retry exercises.
- “Metrics only” excludes durable transcripts, quoted report content, embeddings, and hidden audio copies in our systems. Optional audio retention is distinct from live processing and provider retention.
- Account-enabled languages and assessment accuracy remain unproven. See [language-support.md](language-support.md) for the actual shared ten-language list and an unresolved broader plugin-language listing.
- No app tests, calls, benchmark evaluations, or auto-delegation occurred during this revision.

## 6. Start request: stack research and prompt issuance

See [stack-decisions.md](stack-decisions.md) for newly searched primary sources covering Next.js, FastAPI, uv, Node LTS, npm workspaces, AudioWorklet, Supabase SSR/RLS/private storage, shared-schema validators, pytest and Playwright. Several searches briefly returned 429; required validator/test/runtime lookups subsequently succeeded. Package versions and compatibility still require builder evidence.

At initial issuance, Phase 01 was ready, not executed. It was subsequently built and corrected by the user's engineer; see its current REPORT/VERIFY and tracker. No service, account, inference job, database, recording, test run or public deployment was created by the orchestrator.

## 7. Phase 02 prompt preparation — 2026-10-18

Fresh speech/SDK/model/VAD/data-terms searches and primary Gnani/Silero reads are summarized in [phase-02-provider-feasibility/SOURCES.md](phase-02-provider-feasibility/SOURCES.md). Current local settings were inspected: the foundation's aggregate readiness includes Supabase, but individual speech/LLM settings are available and are the proper inputs for Phase 02. No Supabase setup or modification of shared settings is needed for these probes.

The user's `next` authorized preparation of Phase 02's manual BUILD inside B1. No inference or probe was executed by the CEO; account access, audio feasibility and language quality remain to be established by reported evidence.
