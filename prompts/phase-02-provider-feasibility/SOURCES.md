# Phase 02 research inputs

Checked **2026-10-18** through web searches and primary-page reads. This is documentation evidence only: the CEO made no inference call, installed no dependency and ran no app command. Builders must record their actual current release/API decisions separately in `docs/feasibility/` and REPORT; this file is CEO-owned.

| ID | Primary source | What it establishes / boundary |
|---|---|---|
| P1 | [Gnani realtime STT](https://docs.gnani.ai/api/STT/stt-websocket) — full page read | WebSocket endpoint/header contract; paced 1,024-byte raw PCM frames; speech-segment events; sample-rate and VAD settings; 15-minute connection cap. Docs explicitly say the Python SDK does not expose VAD tuning and recommend a backend proxy for browsers. Emission timestamps are not word alignment. Billing records carry the raw transcript. |
| P2 | [Gnani realtime TTS](https://docs.gnani.ai/api/TTS/tts-websocket) — searched/full page read; [voice catalog](https://docs.gnani.ai/api/TTS/available-voices) — linked, also documented in earlier research | Model/voice pairing, audio configuration, base64 chunks, one synthesis request at a time, start/complete/error lifecycle. OGG/Opus may be delivered in one final chunk. No cancellation control message is specified on the reviewed realtime page; implementation must not invent one. |
| P3 | [Gemini getting started](https://ai.google.dev/gemini-api/docs/get-started), [model catalog](https://ai.google.dev/gemini-api/docs/models) — fresh search results; [audio understanding](https://ai.google.dev/gemini-api/docs/audio) and [structured output](https://ai.google.dev/gemini-api/docs/structured-output) — earlier primary reads | Current SDK/API examples and discoverable models. Examples do not prove this account has access or that a model can grade speech accurately. Choose a model only after checking current docs/access; no specific model ID is silently frozen by this prompt. Audio review is optional evidence research, not replacement speech I/O. |
| P4 | [Silero VAD](https://github.com/snakers4/silero-vad) — searched/full README read | Speech-region estimation, 8/16 kHz support, PyTorch/ONNX paths and MIT license indicated. Exact downloaded package/weights/license/runtime must still be verified. README performance/accuracy claims are vendor results, not measurements of this app or a disfluency detector. |
| P5 | [Gemini API additional terms](https://ai.google.dev/gemini-api/terms) — fresh search result reviewed | Distinguishes paid/unpaid data handling; the unpaid section warns against personal/confidential/sensitive input and describes improvement/review use. Applicable account/region/service terms need full review before real users. Synthetic-only probes avoid treating unresolved privacy claims as solved. |
| P6 | [OWASP prompt-injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) — fresh search; [WebSocket security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html) — previously read | Untrusted inputs, least privilege, bounded resources and avoiding sensitive-content logs. Provider fakes are appropriate for failure/race probes; the selected stack is not automatically secure. |
| P7 | [Montreal Forced Aligner guide](https://montreal-forced-aligner.readthedocs.io/en/latest/user_guide/index.html) and [forced-alignment comparison](https://arxiv.org/html/2406.19363v1) — previously searched, recorded in `prompts/research.md` | Alignment depends on a supplied transcription. Missing-filler recognition and validated timing remain separate problems. No aligner/model/language compatibility has been selected or proven here. |

## Search caveats

- The fresh STT search returned a Pipecat integration page rather than the requested endpoint page. The CEO therefore read the **Gnani primary realtime reference directly**; plugin language lists are not treated as overriding Gnani's actual endpoint contract.
- Both reviewed primary speech endpoints list the same ten named languages. TTS also lists `hi-en`; the STT English entry describes mixed Hindi–English input. Do not assume identical parameter codes on the two endpoints.
- Current model/SDK pages may change. The engineer must use primary documentation and record version/date, not copy an example as a guarantee of compatibility or access.

## Local code observations to preserve

- `services/voice/src/gnani_coach/settings.py:89–106` exposes `load_settings(env_file=...)`.
- Its `provider_readiness()` at lines 109–132 intentionally reports the foundation unavailable and includes Supabase in a combined configured flag. Phase 02 must use the individual speech/LLM settings; **Supabase setup is not required**.
- `providers/` did not exist when this prompt was prepared. The planned ownership grants Phase 02 that subtree, not `main.py`, `settings.py`, shared schemas or production `analysis/`.
- Root `.gitignore` already ignores `.cache/` and audio extensions. Generated synthetic probe audio can remain an ignored local artifact with hashes/recipes in manifests; do not silently weaken the ignore policy or force-add recordings.
- The accepted FIX-1 review carries forward distinct overall-vs-active-rate denominators and sample-clock duration semantics. Prove the proposed meanings in probes; Phase 03 owns any schema correction before contract freeze.

Missing credentials, labeled speech, model assets or provider approval are **not** evidence of success. Preserve that boundary in every feasibility conclusion.
