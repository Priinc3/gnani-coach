# Provider access — agent handoff without embedded secrets

Updated: **2026-10-18**. Applies to all later BUILD/FIX prompts.

## Immediate action

The user supplied Gnani, Gemini, Groq and NVIDIA credentials in conversation and authorized demo use. **Treat those values as exposed. Rotate/revoke them now rather than waiting for project completion.** This document deliberately does not repeat the values, prefixes, suffixes or fingerprints. No supplied credential was sent to a search engine or used by the CEO.

Agents receive **environment-variable names**, not literal keys in prompts. This still lets them use the user's accounts while avoiding more copies in prompt files, commits, reports and session logs. Reverting a file later does not revoke an API credential or remove historical copies.

The user should configure replacement credentials through the runner's private process environment or a user-created local secret file. For this repository, `tools/probes/.env` is an explicit, already-ignored local option; keep it mode `0600`, out of staging, archives and screenshots. Do not print it or put secret-valued exports on a captured command line. Agents must not create or modify global shell profiles or arbitrary outside-repository credential files.

No live probe resumes until the user confirms replacement/rotation and supplies the new environment privately. The agent can continue scoped **offline** repairs with dummy credentials. CEO does not create/revoke provider keys and does not write a secret file.

## Names and integration state

| Provider | Secret variable | Nonsecret selector | Role / state |
|---|---|---|---|
| Gnani | `GNANI_API_KEY` | TTS model/voice and language | Remains required primary STT/TTS. Existing adapter, with builder-reported successful synthetic calls |
| Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL` | Existing reasoning adapter; one reported chain succeeded, later calls timed out. Not reliability-verified |
| Groq | `GROQ_API_KEY` | Proposed `GROQ_MODEL` | User-authorized candidate for a bounded text-reasoning comparison; not wired into the app yet |
| NVIDIA hosted NIM | Proposed local name `NVIDIA_API_KEY` | Proposed `NIM_MODEL` | User-authorized candidate for hosted text reasoning; not wired into the app, not a self-hosting/GPU deployment request |

Proposed names are local configuration conventions, not a claim the existing settings factory or every SDK already reads them. Only the selected provider's credentials may be required for its own probe. Supabase remains unnecessary for Phase 02.

Never infer a key is valid, unlimited, supported by a particular model, or tied to free credits merely from its format. No provider is declared faster/smarter without a controlled comparison. Gnani remains in the actual speech path even if the reasoning provider changes.

## Official documentation found online

| Provider/topic | Primary documentation | Safe planning conclusion |
|---|---|---|
| Gnani speech | https://docs.gnani.ai/api/STT/stt-websocket · https://docs.gnani.ai/api/TTS/tts-websocket · https://docs.gnani.ai/api/TTS/available-voices | Use the specific endpoint/model contract, not a marketing language total; compare observed divergences with the docs |
| Gemini keys | https://ai.google.dev/gemini-api/docs/api-key | Explicit environment-variable guidance and leak-response steps; keep keys confidential and out of source/client bundles |
| Gemini SDK/models | https://github.com/googleapis/python-genai · https://googleapis.github.io/python-genai/index.html · https://ai.google.dev/gemini-api/docs/models | Verify the installed SDK's async/lifecycle/retry surface and exact available model; do not assume daemon-thread abandonment cancels a request |
| Groq | https://console.groq.com/docs/quickstart · https://console.groq.com/docs/models · https://console.groq.com/docs/openai | Quickstart recommends `GROQ_API_KEY`; API compatibility does not make all models/features interchangeable |
| NVIDIA hosted NIM | https://docs.api.nvidia.com/nim/docs/api-quickstart · https://docs.api.nvidia.com/nim/docs/models · https://build.nvidia.com/settings/api-keys | Hosted API access is documented; obtain exact endpoint/request/model requirements from the chosen model's page. Do not assume a hosted key authorizes a self-hosted container |
| Python lifecycle | https://docs.python.org/3.12/library/threading.html | Daemon threads stop abruptly at interpreter shutdown; being able to exit is not proof that work/resources were canceled safely |

Key-management entry points: Gnani console https://app.gnani.ai · Gemini https://aistudio.google.com/apikey · Groq https://console.groq.com/keys · NVIDIA https://build.nvidia.com/settings/api-keys. The owner must use the applicable account controls; no dashboard action was taken here.

Research method: Google search pages were inaccessible and a Bing result was irrelevant. DuckDuckGo HTML searches located the official sources; Gemini key guidance, Groq quickstart, NVIDIA hosted quickstart and Python 3.12 threading documentation were read directly. Gnani's realtime sources were re-found and are also documented in Phase 02 SOURCES. No key validity, account quota or model performance was tested by CEO. Do not turn these documentation lookups into a claim of working Groq/NIM integration.

## Reporting and cleanup boundary

- Report only whether each required variable is configured, whether rotation was confirmed by the user, and the observed redacted outcome. No replacement value, partial key or key hash belongs in REPORT.
- If a secret scan is performed locally, its output must be **file path, line number, rule and count only**, not the matching text. Never paste the conversation's keys into search commands or generated test fixtures.
- If an existing external credential file was created by a builder, identify who created it, under what authorization, and what cleanup evidence exists. Do not claim it was deleted just because a setup document says so, and do not blindly revisit/delete unrelated temp paths.
- Demo status does not waive least privilege, rate/spend limits, origin/endpoint confinement, private data handling or the no-secrets-in-prompts rule.
