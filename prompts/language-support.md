# Gnani language support for our live speaking coach

Checked public documentation on **2026-10-16**. This answers the language question for the **realtime STT → external LLM → realtime TTS** path, not the maximum advertised language count across all Gnani products.

## Practical answer: 10 named languages in common

| Language | Realtime STT language code | Realtime TTS language code |
|---|---|---|
| English (India) | `en-IN` | `en-IN` |
| Hindi | `hi-IN` | `hi-IN` |
| Bengali | `bn-IN` | `bn-IN` |
| Gujarati | `gu-IN` | `gu-IN` |
| Kannada | `kn-IN` | `kn-IN` |
| Malayalam | `ml-IN` | `ml-IN` |
| Marathi | `mr-IN` | `mr-IN` |
| Punjabi | `pa-IN` | `pa-IN` |
| Tamil | `ta-IN` | `ta-IN` |
| Telugu | `te-IN` | `te-IN` |

Sources: [Gnani realtime STT — Supported Languages](https://docs.gnani.ai/api/STT/stt-websocket#supported-languages), [Gnani realtime TTS — Models and language parameters](https://docs.gnani.ai/api/TTS/tts-websocket).

**Hinglish:** TTS documents `hi-en`; the STT English entry describes accepting English–Hindi mixed audio with Latin-script output. Do not send the TTS code `hi-en` to STT unless the selected STT endpoint explicitly supports it. Treat Hinglish as an additional code-mixed mode, not an eleventh independent language or a proven mixed-language scoring system.

**French:** not listed on these reviewed live endpoints. Keep it unavailable unless another account-accessible, documented Gnani path is verified. Other marketing claims do not establish working STT and TTS for French here.

## Voice choices

- **Timbre v2.5:** catalog lists 42 voices with preferred languages, including a Hinglish voice.
- **Timbre v3.0:** catalog lists 13 voices, each documented for all ten languages.
- Voices are model-specific; the catalog warns that using a voice with the wrong model is rejected.

Source: [Gnani voice catalog](https://docs.gnani.ai/api/TTS/available-voices). These are documented counts, not tested account entitlements. We have not selected a model or voice yet.

## How the app should present languages — proposal

1. Ask **“What language do you want to practice?”**
2. Separately ask **“What language should the coach explain in?”** Default to the practice language; the learner can change it.
3. Offer a separate code-switching preference where validated, rather than penalizing a learner for intentional mixing.
4. Track distinct capability states: documented, account-enabled, conversation-tested, and assessment-validated. Do not turn on an unsupported option just because it appears in a dropdown.
5. Distinguish pause/rate estimates from language-specific filler/grammar feedback. An LLM generating that language is not proof that its teaching is correct.

**Acceptance implication:** the catalog target is all ten, but no app capability has been tested yet. Each enabled language needs call/coaching checks; cross-language coaching pairs need coverage too. If a pair is unreliable, label/disable it explicitly and ask for scope approval rather than silently claiming full support.

## Documentation discrepancy

A search result from [Pipecat's Gnani STT integration](https://docs.pipecat.ai/api-reference/server/services/stt/gnani) lists Assamese and Odia as well, while the directly read Gnani realtime endpoint table lists the ten above. That difference is unresolved. Do not expand the shared live STT/TTS catalog based on a plugin listing alone; neither Assamese nor Odia appears in the reviewed Gnani realtime TTS list.

No API calls were made, no keys were requested, and no language quality or latency has been verified by this research.
