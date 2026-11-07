# The settings and readiness contract

Status: **FROZEN, 2026-10-20 (Phase 03).** The code is
`services/voice/src/gnani_coach/settings.py`; nothing else reads
environment variables.

**Phase 03 FIX-1 (2026-10-20)** added `SPEAKING_COACH_ALLOWED_ORIGINS`
and §6 (the origin allowlist). Nothing that was frozen before was
renamed or changed.

---

## 1. The environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SPEAKING_COACH_ENVIRONMENT` | `local` | The environment name. |
| `SPEAKING_COACH_ALLOWED_ORIGINS` | `http://localhost:3000` | The browser-origin allowlist. One list, two jobs: the CORS allowlist of the HTTP routes and the allowlist of the WebSocket handshake. A JSON array or a comma-separated list. The wildcard `*` is **refused while the settings parse**. See §6. |
| `GNANI_API_KEY` | *(none)* | The Gnani speech credential. A `SecretStr`; it never appears in a repr or a log. |
| `GNANI_STT_WS_URL` | `wss://api.vachana.ai/stt/v3/stream` | The reviewed STT endpoint. |
| `GNANI_TTS_WS_URL` | `wss://api.vachana.ai/api/v1/tts` | The reviewed TTS endpoint. **See the limit below.** |
| `GNANI_TTS_MODEL` | `timbre-v2.5` | The synthesis model. The voice catalog is model-specific. |
| `GNANI_TTS_VOICE` | `Kaveri` | The synthesis voice. `Kaveri` is the `en-IN` voice used in the Phase 02 live chain. |
| `GNANI_VAD_THRESHOLD` | `0.7` | The documented VAD threshold. |
| `GNANI_VAD_MIN_SILENCE_MS` | `500` | The documented VAD silence window. |
| `GNANI_VAD_MIN_SPEECH_MS` | `100` | The documented VAD minimum speech. |
| `GNANI_VAD_MIN_SEGMENT_MS` | `120` | The documented VAD minimum segment. |
| `GNANI_VAD_MAX_SPEECH_S` | *(none)* | The documented maximum speech length; unset by default. |
| `GEMINI_API_KEY` | *(none)* | The Gemini credential. A `SecretStr`. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | The reasoning model — see §3. |
| `SUPABASE_URL` | *(none)* | Identity and storage, Phase 06. |
| `SUPABASE_SERVICE_ROLE_KEY` | *(none)* | Identity and storage, Phase 06. A `SecretStr`. |

No secret is ever logged, printed or formatted into an error message.

---

## 2. Readiness

Three views, with different jobs.

| Function | Scope | States |
|---|---|---|
| `speech_readiness(settings)` | Gnani only (speech-to-text and speech). **Never depends on Supabase.** | `unconfigured`, `configured`, `verified` |
| `reasoning_readiness(settings)` | Gemini only. **Never depends on Supabase.** | `unconfigured`, `configured`, `verified` |
| `provider_readiness(settings)` | Everything, including Supabase. | `unavailable` |

What each state means:

* **unconfigured** — the credential is absent. Nothing can be called.
* **configured** — the credential name is present. This says nothing
  about whether the provider works, and it is never shown as "healthy" or
  "live".
* **verified** — a live check has actually passed against this
  configuration in this process. The only way to reach it is to pass
  `verified=True` to the function, and the caller may only do that after
  a real successful call. **Credential presence never produces it.**
* **unavailable** — the combined view. It folds in Supabase, so it
  cannot be resolved by a single provider.

`ProviderReadiness.live` is never set from configuration. It means "a
provider session is open right now", and no code path in this phase
opens one.

The combined view keeps its Phase 01 behaviour on purpose: the Phase 01
test `test_loads_with_no_credentials_and_a_missing_env_file` asserts
`provider_readiness(...).state == "unavailable"`, and that test file
belongs to Phase 01.

---

## 3. The frozen reasoning model

```
GEMINI_MODEL_DEFAULT   = "gemini-3.8-flash"
GEMINI_MODEL_CHECKED_ON = "2026-10-20"
GEMINI_MODEL_SOURCE     = "https://ai.google.dev/gemini-api/docs/models"
```

**Verification.** Google's published models page was checked on
2026-10-20 (<https://ai.google.dev/gemini-api/docs/models>, page last
updated 2026-10-19). It lists **Gemini 3.8 Flash** with the endpoint id
`gemini-3.8-flash` under "Gemini 3 → Stable". The id matches the one
observed working in the Phase 02 live chain, so the observed id and the
documented id agree.

**How the default is applied.** `resolved_gemini_model(settings)` returns
the configured `GEMINI_MODEL` when it is set and the frozen default
otherwise. The default is a module constant rather than a pydantic
default on purpose: the Phase 01 test
`test_defaults_use_only_reviewed_documentation_endpoints` asserts
`settings.gemini.model is None` when nothing is configured, and that
test file is Phase 01's. The *effective* default is the frozen value
either way, and there is exactly one place that applies it.

---

## 4. The TTS model and voice selector

The voice catalog is model-specific and a mismatched pair is a hard
error from the provider, so the model and the voice are configuration
rather than constants buried in a call site:

* `GNANI_TTS_MODEL` — `timbre-v2.5` (the starting model family; v3.0 is
  an explicit capability alternative, never an automatic upgrade);
* `GNANI_TTS_VOICE` — `Kaveri` (the `en-IN` voice).

Each v2.5 voice has one preferred language, so the runtime must choose a
voice that matches the practice language. The provider's own validation
rejects a mismatch before a credential is spent.

**Known limit (Phase 02 adapter, not editable here).** The Phase 02 TTS
client connects to its own documented default endpoint and does not read
a URL from the configuration, so `GNANI_TTS_WS_URL` currently affects
only the configuration boundary, not the socket. Phase 05 either uses
the documented default or the provider client has to change — which is a
Phase 02 file and therefore outside Phase 03's write set.

---

## 5. The VAD settings object

The provider's VAD headers are **fixed for the life of a connection**: a
change needs a reconnect with new headers. The settings therefore build
**one** object:

```python
settings.voice.vad_settings() -> VadSettings
```

The object is immutable, it is handed to every connection, and the
*current* values are carried across a reconnect after a round-boundary
change. The provider's own bounds are checked when the object is built,
not at import time, so a bad value cannot crash startup.

---

## 6. The origin allowlist (Phase 03 FIX-1)

`SPEAKING_COACH_ALLOWED_ORIGINS` is the only list of browser origins in
the service, and it is used in two places: the CORS middleware of the
HTTP routes and the check that `gnani_coach/ports/origins.py` performs
before the `/ws/call` handshake is accepted.

| | |
|---|---|
| Default | the **local web origin only** — `http://localhost:3000` |
| Accepted forms | a JSON array (`["https://a.example"]`) or a comma-separated list (`https://a.example,https://b.example`) |
| Normalisation | lower-cased scheme and host, the default port for the scheme dropped, no trailing `/`; a path, a query, a fragment or a non-`http(s)` scheme is refused |
| The wildcard `*` | **refused while the settings parse** — `load_settings()` raises and the service does not start |
| An empty list | refused as well |

The refusal happens in the settings boundary, so a wildcard can never
reach the middleware or the handshake check. The OWASP WebSocket
Security Cheat Sheet asks for "an explicit allowlist of trusted origins"
and warns against wildcards
(<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
checked 2026-10-20); the FastAPI CORS documentation says the same
(<https://fastapi.tiangolo.com/tutorial/cors/>, checked 2026-10-20).

The **rule** that uses this list — including what a missing `Origin`
header means — is in
[`seams.md` §8](seams.md#8-the-origin-allowlist-the-cors-middleware-and-the-handshake-check).

---

## 7. The rules that survive into every later phase

1. A missing credential is `unconfigured`, never an error at startup.
2. A present credential is `configured`, never `live`.
3. `verified` requires a real, recorded check.
4. Secrets are `SecretStr` and are never logged.
5. The speech and reasoning views never depend on Supabase, so a probe or
   a call path can ask about them without an identity configuration.
6. The origin allowlist is explicit: the wildcard `*` never reaches the
   middleware and never reaches the handshake check.
